#!/usr/bin/env python3
"""Render the hymn decks in parallel without sharing Quarto project state.

Quarto can render one file or directory at a time, but a website render also
writes project-wide files such as ``search.json``, ``index.html`` and
``site_libs``. Concurrent renders in the source project therefore race even
when their input documents are disjoint.

Each worker here gets an isolated copy of the project containing only its
share of ``slide/*.md``. The resulting sites are combined after every Quarto
process succeeds, including one merged search index.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import filecmp
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Sequence

import yaml

from hymn_projection.environment import DEVELOP, PRODUCTION, build_mode


IGNORED_PROJECT_ENTRIES = {
    ".quarto",
    "_site",
    "site_libs",
    "slide",
    # A stopped Quarto render can leave these generated pages beside their
    # Markdown sources. They must not become input resources in a later build.
    "index.html",
    "chorus.html",
}


def _positive_integer(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def _linux_physical_cores(cpuinfo: str, allowed: set[int] | None = None) -> int | None:
    cores: set[tuple[str, str]] = set()
    for block in cpuinfo.split("\n\n"):
        fields = {}
        for line in block.splitlines():
            name, separator, value = line.partition(":")
            if separator:
                fields[name.strip()] = value.strip()
        try:
            processor = int(fields["processor"])
            core = (fields["physical id"], fields["core id"])
        except (KeyError, ValueError):
            continue
        if allowed is None or processor in allowed:
            cores.add(core)
    return len(cores) or None


def _physical_cpu_count() -> int:
    if sys.platform.startswith("linux"):
        try:
            allowed = set(os.sched_getaffinity(0))
        except AttributeError:
            allowed = None
        try:
            count = _linux_physical_cores(
                Path("/proc/cpuinfo").read_text(encoding="utf-8"), allowed
            )
        except OSError:
            count = None
        if count is not None:
            return count
        if allowed:
            return len(allowed)
    elif sys.platform == "darwin":
        result = subprocess.run(
            ["sysctl", "-n", "hw.physicalcpu"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip().isdecimal():
            return int(result.stdout)
    return os.cpu_count() or 1


def _partition(paths: Sequence[Path], jobs: int) -> list[list[Path]]:
    workers = min(jobs, len(paths))
    return [list(paths[index::workers]) for index in range(workers)]


def _copy_project(
    source: Path,
    destination: Path,
    slides: Sequence[Path],
    first: bool,
    mode: str,
) -> None:
    def ignore(_directory: str, names: list[str]) -> set[str]:
        ignored = set(names) & IGNORED_PROJECT_ENTRIES
        if mode == PRODUCTION:
            ignored.add("chorus.md")
        return ignored

    shutil.copytree(source, destination, ignore=ignore)
    slide_directory = destination / "slide"
    slide_directory.mkdir()
    for path in slides:
        shutil.copy2(path, slide_directory / path.name)

    config_path = destination / "_quarto.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    targets = ["slide/*.md"]
    if first:
        targets.insert(0, "index.md")
        if mode == DEVELOP:
            targets.insert(1, "chorus.md")
    config["project"]["render"] = targets
    config_path.write_text(
        yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )


def _render(worker: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["quarto", "render", str(worker), "--quiet"],
        capture_output=True,
        text=True,
        check=False,
    )


def _read_search(path: Path) -> list[dict[str, Any]]:
    entries = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise ValueError(f"{path} does not contain a JSON array")
    return entries


def _copy_without_project_files(source: Path, destination: Path) -> None:
    for path in source.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(source)
        if relative in {Path("index.html"), Path("search.json")}:
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if not filecmp.cmp(path, target, shallow=False):
                raise RuntimeError(f"workers produced different versions of {relative}")
        else:
            shutil.copy2(path, target)


def _merge(worker_outputs: Sequence[Path], destination: Path) -> int:
    shutil.copytree(worker_outputs[0], destination)
    search_entries = _read_search(worker_outputs[0] / "search.json")

    for output in worker_outputs[1:]:
        search_entries.extend(_read_search(output / "search.json"))
        _copy_without_project_files(output, destination)

    # Workers own disjoint documents, so duplicate IDs indicate a bad
    # partition or an unexpected Quarto output rather than something to hide.
    object_ids = [entry.get("objectID") for entry in search_entries]
    if not all(isinstance(object_id, str) for object_id in object_ids):
        raise RuntimeError("worker search index contains an invalid object ID")
    if len(object_ids) != len(set(object_ids)):
        raise RuntimeError("worker search indexes contain duplicate object IDs")
    if any(str(entry.get("href", "")).startswith("chorus.html") for entry in search_entries):
        raise RuntimeError("the developer-only chorus report entered the search index")

    # Make the merge deterministic: documents follow the lexical expansion of
    # slide/*.md, while entries within a document remain in slide order.
    by_document: dict[str, list[dict[str, Any]]] = {}
    for entry in search_entries:
        document = str(entry.get("href", "")).split("#", 1)[0]
        by_document.setdefault(document, []).append(entry)
    search_entries = [
        entry for document in sorted(by_document) for entry in by_document[document]
    ]
    (destination / "search.json").write_text(
        json.dumps(search_entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return len(search_entries)


def build(project: Path, jobs: int) -> None:
    project = project.resolve()
    mode = build_mode()
    slides = sorted(
        (project / "slide").glob("*.md"),
        key=lambda path: int(path.stem),
    )
    if not slides:
        raise RuntimeError(f"no hymn Markdown found in {project / 'slide'}")

    partitions = _partition(slides, jobs)
    started = time.monotonic()
    process_count = len(partitions)
    noun = "process" if process_count == 1 else "processes"
    physical_cores = _physical_cpu_count()
    print(f"Build mode: {mode}")
    print(f"Detected {physical_cores} physical CPU cores")
    print(f"Rendering {len(slides)} hymn decks with {process_count} Quarto {noun}")

    with tempfile.TemporaryDirectory(prefix=".quarto-build-", dir=project.parent) as temporary:
        temporary_path = Path(temporary)
        workers: list[Path] = []
        for index, partition in enumerate(partitions):
            worker = temporary_path / f"worker-{index + 1}"
            _copy_project(project, worker, partition, first=index == 0, mode=mode)
            workers.append(worker)

        failures: list[tuple[int, subprocess.CompletedProcess[str]]] = []
        with ThreadPoolExecutor(max_workers=len(workers)) as executor:
            futures = {
                executor.submit(_render, worker): index
                for index, worker in enumerate(workers)
            }
            for future in as_completed(futures):
                index = futures[future]
                result = future.result()
                if result.returncode:
                    failures.append((index, result))
                else:
                    print(f"  worker {index + 1}/{len(workers)} finished")
                    if result.stdout or result.stderr:
                        print(result.stdout, end="")
                        print(result.stderr, end="")

        if failures:
            for index, result in sorted(failures):
                print(f"\nworker {index + 1} failed:")
                print(result.stdout, end="")
                print(result.stderr, end="")
            raise RuntimeError(f"{len(failures)} Quarto worker(s) failed")

        combined = temporary_path / "combined"
        search_count = _merge([worker / "_site" for worker in workers], combined)
        rendered = len(list((combined / "slide").glob("*.html")))
        if rendered != len(slides):
            raise RuntimeError(f"rendered {rendered} of {len(slides)} hymn decks")
        chorus_exists = (combined / "chorus.html").exists()
        if chorus_exists != (mode == DEVELOP):
            raise RuntimeError(f"chorus.html does not match {mode} build mode")

        output = project / "_site"
        if output.exists():
            shutil.rmtree(output)
        combined.replace(output)

    elapsed = time.monotonic() - started
    print(f"Built {len(slides)} decks and {search_count} search entries in {elapsed:.1f}s")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", nargs="?", type=Path, default=Path("site"))
    parser.add_argument(
        "-j",
        "--jobs",
        type=_positive_integer,
        default=_physical_cpu_count(),
        help="parallel Quarto processes (default: all physical CPU cores)",
    )
    arguments = parser.parse_args()
    build(arguments.project, arguments.jobs)


if __name__ == "__main__":
    main()
