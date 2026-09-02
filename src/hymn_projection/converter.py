"""Convert the hymn collection between YAML and Pandoc Markdown.

Each YAML list item becomes ``N.md``.  Hymn metadata is stored in YAML front
matter, while each stanza is a heading followed by a list of lyric lines.  A
language entry is represented by a Pandoc span carrying a ``lang`` attribute.
The reverse conversion accepts exactly that structure and rebuilds the ordered
YAML data without discarding information.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from functools import cache
from pathlib import Path
from typing import Any

import panflute as pf
import yaml


# Disable Pandoc's ``smart`` extension so literal curly quotes and dashes are
# data, rather than typography for Pandoc to rewrite.
PANDOC_MARKDOWN = "markdown-smart+yaml_metadata_block+bracketed_spans"


@cache
def pandoc_api_version() -> tuple[int, ...]:
    """Return the JSON API version used by the installed Pandoc."""

    empty_document = pf.convert_text("", standalone=True)
    return empty_document.api_version


def load_yaml(path: Path) -> list[dict[str, Any]]:
    """Load and minimally validate a hymn collection from YAML."""

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
        raise ValueError(f"{path} must contain a list of mappings")
    return data


def lyric_line_to_item(line: Mapping[str, str]) -> pf.ListItem:
    """Construct one Markdown list item from an ordered language mapping."""

    inlines: list[pf.Inline] = []
    for language, text in line.items():
        if not isinstance(language, str) or not isinstance(text, str):
            raise ValueError("lyric languages and text must be strings")
        if inlines:
            inlines.append(pf.LineBreak)
        inlines.append(pf.Span(pf.Str(text), attributes={"lang": language}))
    if not inlines:
        raise ValueError("a lyric line cannot be empty")
    return pf.ListItem(pf.Plain(*inlines))


def hymn_to_document(hymn: Mapping[str, Any]) -> pf.Doc:
    """Construct a Panflute document for one hymn mapping."""

    stanza = hymn.get("stanza")
    if not isinstance(stanza, Mapping):
        raise ValueError("each hymn must contain a stanza mapping")

    blocks: list[pf.Block] = []
    for stanza_name, lines in stanza.items():
        if not isinstance(lines, Sequence) or isinstance(lines, (str, bytes)):
            raise ValueError(f"stanza {stanza_name!r} must contain a list")
        blocks.append(pf.Header(pf.Str(str(stanza_name)), level=1))
        blocks.append(pf.BulletList(*(lyric_line_to_item(line) for line in lines)))

    metadata = {key: value for key, value in hymn.items() if key != "stanza"}
    document = pf.Doc(*blocks, metadata=metadata)
    # Panflute 2.0's default predates Pandoc 3.8; Pandoc rejects stale API
    # versions even though the elements used here are unchanged.
    document.api_version = pandoc_api_version()
    return document


def document_to_markdown(document: pf.Doc) -> str:
    """Render a Panflute document as unwrapped, standalone Markdown."""

    markdown = pf.convert_text(
        document,
        input_format="panflute",
        output_format=PANDOC_MARKDOWN,
        standalone=True,
        extra_args=["--wrap=none"],
    )
    return markdown.rstrip("\n") + "\n"


def yaml_to_markdown(source: Path, destination: Path) -> None:
    """Write every item in a YAML collection to a numbered Markdown file."""

    hymns = load_yaml(source)
    destination.mkdir(parents=True, exist_ok=True)
    for number, hymn in enumerate(hymns, start=1):
        markdown = document_to_markdown(hymn_to_document(hymn))
        (destination / f"{number}.md").write_text(markdown, encoding="utf-8")


def parse_lyric_item(item: pf.ListItem) -> dict[str, str]:
    """Recover one ordered language mapping from a Markdown list item."""

    if len(item.content) != 1 or not isinstance(item.content[0], (pf.Plain, pf.Para)):
        raise ValueError("each lyric list item must contain one paragraph")

    line: dict[str, str] = {}
    for inline in item.content[0].content:
        if isinstance(inline, pf.Span):
            language = inline.attributes.get("lang")
            if not language:
                raise ValueError("each lyric span must have a lang attribute")
            if language in line:
                raise ValueError(f"duplicate {language!r} span in one lyric line")
            line[language] = pf.stringify(inline)
        elif not isinstance(inline, (pf.LineBreak, pf.SoftBreak, pf.Space)):
            raise ValueError("lyric list items may only contain language spans")

    if not line:
        raise ValueError("a lyric list item must contain at least one language span")
    return line


def stanza_name(header: pf.Header) -> int | str:
    """Recover an integer stanza key or retain a named stanza such as a chorus."""

    name = pf.stringify(header)
    return int(name) if name.isdecimal() else name


def markdown_to_hymn(path: Path) -> dict[str, Any]:
    """Parse one numbered Markdown document back into a hymn mapping."""

    document = pf.convert_text(
        path.read_text(encoding="utf-8"),
        input_format=PANDOC_MARKDOWN,
        output_format="panflute",
        standalone=True,
    )
    hymn = document.get_metadata()
    stanza: dict[int | str, list[dict[str, str]]] = {}

    blocks = list(document.content)
    if len(blocks) % 2:
        raise ValueError(f"{path} must alternate stanza headings and lyric lists")
    for index in range(0, len(blocks), 2):
        header, lyric_list = blocks[index : index + 2]
        if not isinstance(header, pf.Header) or header.level != 1:
            raise ValueError(f"{path}: stanza must begin with a level-one heading")
        if not isinstance(lyric_list, pf.BulletList):
            raise ValueError(f"{path}: stanza heading must be followed by a bullet list")
        name = stanza_name(header)
        if name in stanza:
            raise ValueError(f"{path}: duplicate stanza heading {name!r}")
        stanza[name] = [parse_lyric_item(item) for item in lyric_list.content]

    # ``title`` is the sole field that follows ``stanza`` in the source
    # collection.  Retain that ordering so the reconstructed YAML is also a
    # byte-for-byte match, not merely an equivalent YAML document.
    has_title = "title" in hymn
    title = hymn.pop("title", None)
    hymn["stanza"] = stanza
    if has_title:
        hymn["title"] = title
    return hymn


def numbered_markdown_files(directory: Path) -> list[Path]:
    """Return numbered Markdown files in order, rejecting gaps and other names."""

    files = list(directory.glob("*.md"))
    if any(not path.stem.isdecimal() for path in files):
        raise ValueError(f"all Markdown files in {directory} must be named N.md")
    files.sort(key=lambda path: int(path.stem))
    numbers = [int(path.stem) for path in files]
    if numbers != list(range(1, len(files) + 1)):
        raise ValueError(f"Markdown file numbering in {directory} must start at 1 without gaps")
    return files


def markdown_to_yaml(source: Path, destination: Path) -> None:
    """Rebuild a YAML collection from a directory of numbered Markdown files."""

    hymns = [markdown_to_hymn(path) for path in numbered_markdown_files(source)]
    destination.write_text(
        yaml.safe_dump(hymns, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


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
