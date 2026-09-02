"""Stream hymns between one YAML sequence and numbered Markdown files."""

from __future__ import annotations

import argparse
from collections.abc import Iterable, Iterator
from pathlib import Path

import yaml

from .model import Hymn


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


def main() -> None:
    """Run one conversion direction from the command line."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "direction",
        choices=("yaml-to-markdown", "markdown-to-yaml"),
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    arguments = parser.parse_args()

    if arguments.direction == "yaml-to-markdown":
        yaml_to_markdown(arguments.source, arguments.destination)
    else:
        markdown_to_yaml(arguments.source, arguments.destination)


if __name__ == "__main__":
    main()
