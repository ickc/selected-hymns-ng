"""Stream hymns between one YAML sequence and numbered Markdown files."""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from itertools import repeat
from pathlib import Path

import yaml

from .environment import PRODUCTION, build_mode, physical_cpu_count
from .model import Hymn
from .slides import (
    LINES_PER_SLIDE,
    chorus_report_markdown,
    to_markdown as slide_markdown,
)


def hymns_from_yaml(path: Path) -> Iterator[Hymn]:
    """Yield validated hymns from a YAML sequence."""

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a list")
    for number, value in enumerate(data, start=1):
        try:
            yield Hymn.from_dict(value)
        except ValueError as error:
            raise ValueError(f"{path}: hymn {number}: {error}") from error


def write_yaml(hymns: Iterable[Hymn], path: Path) -> None:
    """Write hymns as the canonical YAML sequence."""

    data = [hymn.to_dict() for hymn in hymns]
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def numbered_markdown_files(directory: Path) -> list[Path]:
    """Return N.md files in order, rejecting non-numeric names and gaps."""

    files = list(directory.glob("*.md"))
    if not files:
        # Every caller goes on to describe the collection as a whole -- its
        # range, its choruses -- and would otherwise fail somewhere further in,
        # naming anything but the directory that was empty.
        raise ValueError(f"no N.md files in {directory}")
    if any(not path.stem.isdecimal() for path in files):
        raise ValueError(f"all Markdown files in {directory} must be named N.md")
    files.sort(key=lambda path: int(path.stem))
    numbers = [int(path.stem) for path in files]
    if numbers != list(range(1, len(files) + 1)):
        raise ValueError(f"Markdown file numbering in {directory} must start at 1 without gaps")
    return files


def hymns_from_markdown(directory: Path) -> Iterator[Hymn]:
    """Yield validated hymns from a numbered Markdown directory."""

    for path in numbered_markdown_files(directory):
        try:
            yield Hymn.from_markdown(path.read_text(encoding="utf-8"))
        except ValueError as error:
            raise ValueError(f"{path}: {error}") from error


def yaml_to_markdown(source: Path, destination: Path) -> None:
    """Write a YAML sequence as numbered Markdown documents."""

    destination.mkdir(parents=True, exist_ok=True)
    for number, hymn in enumerate(hymns_from_yaml(source), start=1):
        (destination / f"{number}.md").write_text(hymn.to_markdown(), encoding="utf-8")


def markdown_to_yaml(source: Path, destination: Path) -> None:
    """Rebuild a YAML sequence from numbered Markdown documents."""

    write_yaml(hymns_from_markdown(source), destination)


def _slide_projection(path: Path, limit: int) -> tuple[int, Hymn, str]:
    """Read and project one hymn independently of the collection."""

    number = int(path.stem)
    try:
        hymn = Hymn.from_markdown(path.read_text(encoding="utf-8"))
        slides = slide_markdown(hymn, number, limit)
    except ValueError as error:
        raise ValueError(f"{path}: {error}") from error
    return number, hymn, slides


def markdown_to_slides(
    source: Path,
    destination: Path,
    limit: int = LINES_PER_SLIDE,
    jobs: int | None = None,
) -> None:
    """Write each hymn's slide projection, and the report beside it."""

    mode = build_mode()
    destination.mkdir(parents=True, exist_ok=True)
    files = numbered_markdown_files(source)
    if jobs is not None and jobs < 1:
        raise ValueError("jobs must be at least 1")
    workers = min(jobs or physical_cpu_count(), len(files))
    hymn_noun = "hymn" if len(files) == 1 else "hymns"
    worker_noun = "worker" if workers == 1 else "workers"
    print(
        f"Projecting {len(files)} {hymn_noun} with {workers} concurrent Pandoc {worker_noun}",
        flush=True,
    )
    with ThreadPoolExecutor(max_workers=workers) as executor:
        projections = list(executor.map(_slide_projection, files, repeat(limit)))

    entries: list[tuple[int, Hymn]] = []
    for number, hymn, slides in projections:
        (destination / f"{number}.md").write_text(slides, encoding="utf-8")
        entries.append((number, hymn))
    # A hymn that leaves `data/` must leave here too. The render globs this
    # directory, so a deck left behind would go on being published while the
    # index, which knows the collection's range, refused to link to it.
    written = {f"{number}.md" for number, _ in entries}
    for stale in destination.glob("*.md"):
        if stale.name not in written:
            stale.unlink()
    # This developer report sits beside `slide/`, not inside it. Production
    # omits both its source and anything a stopped render may have left beside
    # that source; other modes write it with the slides so it cannot drift
    # from what they sing.
    report = destination.parent / "chorus.md"
    if mode == PRODUCTION:
        report.unlink(missing_ok=True)
        report.with_suffix(".html").unlink(missing_ok=True)
    else:
        report.write_text(chorus_report_markdown(entries), encoding="utf-8")


def main() -> None:
    """Run one conversion direction from the command line."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "direction",
        choices=("yaml-to-markdown", "markdown-to-yaml", "markdown-to-slides"),
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument(
        "--lines-per-slide",
        type=int,
        default=LINES_PER_SLIDE,
        help="lyric lines a slide holds before a stanza is divided",
    )
    parser.add_argument(
        "-j",
        "--jobs",
        type=int,
        default=physical_cpu_count(),
        help="concurrent Pandoc workers (default: all physical CPU cores)",
    )
    arguments = parser.parse_args()
    if arguments.jobs < 1:
        parser.error("--jobs must be at least 1")

    if arguments.direction == "yaml-to-markdown":
        yaml_to_markdown(arguments.source, arguments.destination)
    elif arguments.direction == "markdown-to-yaml":
        markdown_to_yaml(arguments.source, arguments.destination)
    else:
        markdown_to_slides(
            arguments.source,
            arguments.destination,
            arguments.lines_per_slide,
            arguments.jobs,
        )


if __name__ == "__main__":
    main()
