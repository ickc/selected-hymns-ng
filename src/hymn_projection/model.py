"""The validated hymn model and its lossless Markdown representation."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from typing import Any

import panflute as pf


# Pandoc's ``smart`` extension rewrites literal curly quotes and dashes.
PANDOC_MARKDOWN = "markdown-smart+yaml_metadata_block+bracketed_spans"
LANGUAGES = frozenset(("en", "zh"))
STANZA_NAME = re.compile(r"[1-9][0-9]*-chorus")


def _mapping(value: object, description: str) -> Mapping[Any, Any]:
    """Return a mapping or raise a schema error mentioning its purpose."""

    if not isinstance(value, Mapping):
        raise ValueError(f"{description} must be a mapping")
    return value


@cache
def pandoc_api_version() -> tuple[int, ...]:
    """Return the JSON API version used by the installed Pandoc."""

    empty_document = pf.convert_text("", standalone=True)
    return empty_document.api_version


@dataclass
class LocalizedText:
    """An ordered mapping of supported language tags to text."""

    translations: dict[str, str]

    def __post_init__(self) -> None:
        if not self.translations:
            raise ValueError("localized text cannot be empty")
        for language, text in self.translations.items():
            if language not in LANGUAGES:
                raise ValueError(f"unsupported language {language!r}")
            if not isinstance(text, str):
                raise ValueError("localized text values must be strings")

    @classmethod
    def from_dict(cls, value: object, description: str) -> LocalizedText:
        """Validate and construct localized text from a YAML value."""

        mapping = _mapping(value, description)
        return cls(dict(mapping))

    def to_dict(self) -> dict[str, str]:
        """Return an independent YAML-compatible mapping."""

        return dict(self.translations)


@dataclass
class LyricLine:
    """One lyric line containing one or more translations."""

    translations: dict[str, str]

    def __post_init__(self) -> None:
        if not self.translations:
            raise ValueError("a lyric line cannot be empty")
        for language, text in self.translations.items():
            if language not in LANGUAGES:
                raise ValueError(f"unsupported lyric language {language!r}")
            if not isinstance(text, str):
                raise ValueError("lyric text must be a string")

    @classmethod
    def from_dict(cls, value: object) -> LyricLine:
        """Validate and construct one lyric line from a YAML value."""

        return cls(dict(_mapping(value, "lyric line")))

    def to_dict(self) -> dict[str, str]:
        """Return an independent YAML-compatible mapping."""

        return dict(self.translations)

    def to_list_item(self) -> pf.ListItem:
        """Construct the Pandoc list item used for this line."""

        inlines: list[pf.Inline] = []
        for language, text in self.translations.items():
            if inlines:
                inlines.append(pf.LineBreak)
            inlines.append(pf.Span(pf.Str(text), attributes={"lang": language}))
        return pf.ListItem(pf.Plain(*inlines))

    @classmethod
    def from_list_item(cls, item: pf.ListItem) -> LyricLine:
        """Recover one lyric line from a Pandoc list item."""

        if len(item.content) != 1 or not isinstance(item.content[0], (pf.Plain, pf.Para)):
            raise ValueError("each lyric list item must contain one paragraph")

        translations: dict[str, str] = {}
        for inline in item.content[0].content:
            if isinstance(inline, pf.Span):
                language = inline.attributes.get("lang")
                if not language:
                    raise ValueError("each lyric span must have a lang attribute")
                if language in translations:
                    raise ValueError(f"duplicate {language!r} span in one lyric line")
                translations[language] = pf.stringify(inline)
            elif not isinstance(inline, (pf.LineBreak, pf.SoftBreak, pf.Space)):
                raise ValueError("lyric list items may only contain language spans")
        return cls(translations)


@dataclass
class Stanza:
    """A numbered verse or named chorus and its lyric lines."""

    name: int | str
    lines: list[LyricLine]

    def __post_init__(self) -> None:
        valid_number = (
            isinstance(self.name, int)
            and not isinstance(self.name, bool)
            and self.name > 0
        )
        valid_chorus = isinstance(self.name, str) and STANZA_NAME.fullmatch(self.name)
        if not valid_number and not valid_chorus:
            raise ValueError(f"invalid stanza name {self.name!r}")
        if not self.lines:
            raise ValueError(f"stanza {self.name!r} cannot be empty")
        if not all(isinstance(line, LyricLine) for line in self.lines):
            raise ValueError("stanza lines must be LyricLine objects")

    @classmethod
    def from_yaml(cls, name: object, value: object) -> Stanza:
        """Validate and construct a stanza from its YAML key and value."""

        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            raise ValueError(f"stanza {name!r} must contain a list")
        return cls(name, [LyricLine.from_dict(line) for line in value])

    def to_yaml(self) -> list[dict[str, str]]:
        """Return the YAML-compatible list for this stanza."""

        return [line.to_dict() for line in self.lines]


@dataclass
class Hymn:
    """A validated hymn with YAML and Pandoc Markdown codecs."""

    category: LocalizedText
    stanzas: list[Stanza]
    author: LocalizedText | None = None
    meter: str | LocalizedText | None = None
    note: LocalizedText | None = None
    ref: LocalizedText | None = None
    title: LocalizedText | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.category, LocalizedText):
            raise ValueError("category must be localized text")
        if not self.stanzas or not all(isinstance(stanza, Stanza) for stanza in self.stanzas):
            raise ValueError("a hymn must contain stanzas")
        names = [stanza.name for stanza in self.stanzas]
        if len(names) != len(set(names)):
            raise ValueError("stanza names must be unique")
        if self.meter is not None and not isinstance(self.meter, (str, LocalizedText)):
            raise ValueError("meter must be a string or localized text")
        for name in ("author", "note", "ref", "title"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, LocalizedText):
                raise ValueError(f"{name} must be localized text")

    @classmethod
    def from_dict(cls, value: object) -> Hymn:
        """Validate and construct a hymn from a YAML-compatible mapping."""

        mapping = _mapping(value, "hymn")
        allowed = {"author", "category", "meter", "note", "ref", "stanza", "title"}
        unknown = set(mapping) - allowed
        missing = {"category", "stanza"} - set(mapping)
        if unknown:
            raise ValueError(f"unknown hymn fields: {sorted(unknown)!r}")
        if missing:
            raise ValueError(f"missing hymn fields: {sorted(missing)!r}")

        stanza_mapping = _mapping(mapping["stanza"], "stanza")
        meter: str | LocalizedText | None = None
        if "meter" in mapping:
            meter_value = mapping["meter"]
            if isinstance(meter_value, Mapping):
                meter = LocalizedText.from_dict(meter_value, "meter")
            elif isinstance(meter_value, str):
                meter = meter_value
            else:
                raise ValueError("meter must be a string or localized mapping")

        def optional_text(name: str) -> LocalizedText | None:
            if name not in mapping:
                return None
            return LocalizedText.from_dict(mapping[name], name)

        return cls(
            category=LocalizedText.from_dict(mapping["category"], "category"),
            stanzas=[Stanza.from_yaml(name, lines) for name, lines in stanza_mapping.items()],
            author=optional_text("author"),
            meter=meter,
            note=optional_text("note"),
            ref=optional_text("ref"),
            title=optional_text("title"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return the canonical YAML mapping used by the source collection."""

        result: dict[str, Any] = {}
        if self.author is not None:
            result["author"] = self.author.to_dict()
        result["category"] = self.category.to_dict()
        if self.meter is not None:
            result["meter"] = (
                self.meter.to_dict()
                if isinstance(self.meter, LocalizedText)
                else self.meter
            )
        if self.note is not None:
            result["note"] = self.note.to_dict()
        if self.ref is not None:
            result["ref"] = self.ref.to_dict()
        result["stanza"] = {stanza.name: stanza.to_yaml() for stanza in self.stanzas}
        if self.title is not None:
            result["title"] = self.title.to_dict()
        return result

    def to_document(self) -> pf.Doc:
        """Construct this hymn's Panflute document."""

        blocks: list[pf.Block] = []
        for stanza in self.stanzas:
            blocks.append(pf.Header(pf.Str(str(stanza.name)), level=1))
            blocks.append(pf.BulletList(*(line.to_list_item() for line in stanza.lines)))

        metadata = self.to_dict()
        del metadata["stanza"]
        document = pf.Doc(*blocks, metadata=metadata)
        # Panflute 2.0 defaults to an API version rejected by Pandoc 3.8.
        document.api_version = pandoc_api_version()
        return document

    def to_markdown(self) -> str:
        """Render this hymn as standalone, unwrapped Pandoc Markdown."""

        markdown = pf.convert_text(
            self.to_document(),
            input_format="panflute",
            output_format=PANDOC_MARKDOWN,
            standalone=True,
            extra_args=["--wrap=none"],
        )
        return markdown.rstrip("\n") + "\n"

    @classmethod
    def from_markdown(cls, markdown: str) -> Hymn:
        """Parse and validate one hymn from Pandoc Markdown."""

        document = pf.convert_text(
            markdown,
            input_format=PANDOC_MARKDOWN,
            output_format="panflute",
            standalone=True,
        )
        metadata = document.get_metadata()
        if "stanza" in metadata:
            raise ValueError("stanza is body content and cannot appear in front matter")

        blocks = list(document.content)
        if len(blocks) % 2:
            raise ValueError("document must alternate stanza headings and lyric lists")
        stanza: dict[int | str, list[dict[str, str]]] = {}
        for index in range(0, len(blocks), 2):
            header, lyric_list = blocks[index : index + 2]
            if not isinstance(header, pf.Header) or header.level != 1:
                raise ValueError("each stanza must begin with a level-one heading")
            if not isinstance(lyric_list, pf.BulletList):
                raise ValueError("each stanza heading must be followed by a bullet list")
            heading = pf.stringify(header)
            name: int | str = int(heading) if heading.isdecimal() else heading
            if name in stanza:
                raise ValueError(f"duplicate stanza heading {name!r}")
            stanza[name] = [LyricLine.from_list_item(item).to_dict() for item in lyric_list.content]

        has_title = "title" in metadata
        title = metadata.pop("title", None)
        metadata["stanza"] = stanza
        if has_title:
            metadata["title"] = title
        return cls.from_dict(metadata)
