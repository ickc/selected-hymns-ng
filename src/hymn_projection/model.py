"""The validated hymn model and its lossless Markdown representation."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from os.path import commonprefix
from pathlib import Path
from typing import Any

import panflute as pf


# Pandoc's ``smart`` extension rewrites literal curly quotes and dashes.  The
# checked-in projection deliberately disables bracketed spans: language spans
# exist only inside the converter, on either side of the Lua filters.
PANDOC_MARKDOWN = "markdown-smart+yaml_metadata_block+line_blocks-bracketed_spans"
LANGUAGES = frozenset(("en", "zh"))
LANGUAGE_ORDER = {"en": 0, "zh": 1}
STANZA_NAME = re.compile(r"[1-9][0-9]*-chorus")
METER_PREFIX = re.compile(r"^(?:[0-9]+\.)+(?:D\.)?\s+")
AUTO_LANG = {"Han": "zh", "Latin": "en"}
FILTER_DIRECTORY = Path(__file__).with_name("filters")
AUTO_LANG_FILTER = FILTER_DIRECTORY / "auto-lang.lua"
STRIP_LANG_FILTER = FILTER_DIRECTORY / "strip-lang.lua"
PRESERVE_MARKDOWN_FILTER = FILTER_DIRECTORY / "preserve-markdown.lua"


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


def _language(element: pf.Element) -> str | None:
    """Return an element's language when it is a language span."""

    if isinstance(element, pf.Span):
        return element.attributes.get("lang")
    return None


def _text_piece(element: pf.Element) -> str:
    """Stringify one inline without dropping significant boundary spaces."""

    if isinstance(element, pf.Space):
        return " "
    if isinstance(element, (pf.LineBreak, pf.SoftBreak)):
        return "\n"
    if isinstance(element, pf.Str):
        return element.text
    return pf.stringify(element)


def _exact_text(elements: Sequence[pf.Element]) -> str:
    """Stringify adjacent metadata inlines, including trailing spaces."""

    return "".join(_text_piece(element) for element in elements)


def _localized_metadata(value: LocalizedText) -> pf.MetaInlines:
    """Represent localized metadata as internal language spans."""

    return pf.MetaInlines(
        *(
            pf.Span(pf.RawInline(text, format="markdown"), attributes={"lang": language})
            for language, text in value.translations.items()
        )
    )


def _localized_from_metadata(value: pf.MetaValue, description: str) -> LocalizedText:
    """Recover localized metadata after ``auto-lang.lua`` has tagged it."""

    if not isinstance(value, pf.MetaInlines):
        raise ValueError(f"{description} must contain language-detectable text")
    translations: dict[str, str] = {}
    for element in value.content:
        language = _language(element)
        if not language:
            raise ValueError(f"all {description} text must resolve to language spans")
        if language in translations:
            raise ValueError(f"duplicate {language!r} text in {description}")
        translations[language] = pf.stringify(element)
    return LocalizedText(translations)


def _meter_metadata(value: LocalizedText) -> pf.MetaInlines:
    """Factor a localized meter's shared notation out of its translations."""

    if len(value.translations) < 2:
        raise ValueError("a localized meter needs two languages to remain distinguishable")
    shared = commonprefix(list(value.translations.values()))
    if not METER_PREFIX.fullmatch(shared):
        raise ValueError("localized meter translations must share their meter notation")
    return pf.MetaInlines(
        pf.Str(shared),
        *(
            pf.Span(
                pf.RawInline(text[len(shared) :], format="markdown"),
                attributes={"lang": language},
            )
            for language, text in value.translations.items()
        ),
    )


def _meter_from_metadata(value: pf.MetaValue) -> str | LocalizedText:
    """Recover a scalar meter or expand shared notation over its translations."""

    if not isinstance(value, pf.MetaInlines):
        return pf.stringify(value)

    languages = [
        language
        for element in value.content
        if (language := _language(element)) is not None
    ]
    if len(set(languages)) <= 1:
        # A scalar meter such as ``C.M.`` may itself be tagged as Latin.  A
        # localized meter in this collection always has both en and zh runs.
        return pf.stringify(value)

    rendered = _exact_text(value.content)
    match = METER_PREFIX.match(rendered)
    if not match:
        raise ValueError("localized meter must begin with shared meter notation")
    shared = match.group()

    translations: dict[str, str] = {}
    offset = 0
    for element in value.content:
        text = _text_piece(element)
        language = _language(element)
        if language:
            # ``D`` is Latin, so auto-lang may put the tail of a shared
            # ``7.7.7.7.D.`` prefix inside the English span.  Keep only the
            # part of each span which follows the shared prefix.
            suffix = text[max(len(shared) - offset, 0) :]
            if suffix:
                translations[language] = translations.get(language, "") + suffix
        elif offset + len(text) > len(shared):
            raise ValueError("localized meter has untagged text after its shared prefix")
        offset += len(text)

    if set(translations) != set(languages):
        raise ValueError("each localized meter language must have a distinct suffix")
    return LocalizedText(
        {language: shared + suffix for language, suffix in translations.items()}
    )


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
        order = [LANGUAGE_ORDER[language] for language in self.translations]
        if order != sorted(order):
            raise ValueError("lyric languages must be ordered en, then zh")

    @classmethod
    def from_dict(cls, value: object) -> LyricLine:
        """Validate and construct one lyric line from a YAML value."""

        return cls(dict(_mapping(value, "lyric line")))

    def to_dict(self) -> dict[str, str]:
        """Return an independent YAML-compatible mapping."""

        return dict(self.translations)

    def to_line_items(self) -> list[pf.LineItem]:
        """Construct the internally tagged line-block lines for this YAML line."""

        return [
            pf.LineItem(
                pf.Span(
                    pf.RawInline(text, format="markdown"),
                    attributes={"lang": language},
                )
            )
            for language, text in self.translations.items()
        ]

    @staticmethod
    def from_line_block(
        block: pf.LineBlock, source_lines: Sequence[str]
    ) -> list[LyricLine]:
        """Recover ordered YAML lines from one automatically tagged stanza."""

        if len(block.content) != len(source_lines):
            raise ValueError("Markdown source does not match parsed line block")
        lines: list[LyricLine] = []
        translations: dict[str, str] = {}
        previous_order = -1
        for line, source in zip(block.content, source_lines, strict=True):
            # Inline markup can interrupt the outer automatically inferred
            # span.  Notes are a separate flow in Pandoc, for example, so a
            # line containing ``text^[note]`` has two zh spans rather than one.
            languages = {
                language
                for element in line.content
                if (language := _language(element)) is not None
            }
            if len(languages) != 1:
                raise ValueError(
                    "each line-block line must resolve to exactly one language"
                )
            language = languages.pop()
            language_order = LANGUAGE_ORDER.get(language, -1)
            if language_order < 0:
                raise ValueError(f"unsupported lyric language {language!r}")

            # Each YAML mapping is in en/zh order.  A repeated language, or a
            # transition from zh back to en, therefore begins the next mapping.
            if translations and language_order <= previous_order:
                lines.append(LyricLine(translations))
                translations = {}
            translations[language] = source
            previous_order = language_order

        if translations:
            lines.append(LyricLine(translations))
        return lines


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
        """Construct the internally language-tagged Panflute document."""

        blocks: list[pf.Block] = []
        for stanza in self.stanzas:
            blocks.append(pf.Header(pf.Str(str(stanza.name)), level=1))
            blocks.append(
                pf.LineBlock(
                    *(item for line in stanza.lines for item in line.to_line_items())
                )
            )

        metadata: dict[str, Any] = {"auto-lang": AUTO_LANG}
        if self.author is not None:
            metadata["author"] = _localized_metadata(self.author)
        metadata["category"] = _localized_metadata(self.category)
        if self.meter is not None:
            metadata["meter"] = (
                _meter_metadata(self.meter)
                if isinstance(self.meter, LocalizedText)
                else pf.MetaInlines(pf.RawInline(self.meter, format="markdown"))
            )
        if self.note is not None:
            metadata["note"] = _localized_metadata(self.note)
        if self.ref is not None:
            metadata["ref"] = _localized_metadata(self.ref)
        if self.title is not None:
            metadata["title"] = _localized_metadata(self.title)
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
            extra_args=[f"--lua-filter={STRIP_LANG_FILTER}", "--wrap=none"],
        )
        return markdown.rstrip("\n") + "\n"

    @classmethod
    def from_markdown(cls, markdown: str) -> Hymn:
        """Parse and validate one hymn from Pandoc Markdown."""

        source_lines = iter(_line_block_sources(markdown))
        document = pf.convert_text(
            markdown,
            input_format=PANDOC_MARKDOWN,
            output_format="panflute",
            standalone=True,
            extra_args=[
                f"--lua-filter={AUTO_LANG_FILTER}",
                f"--lua-filter={PRESERVE_MARKDOWN_FILTER}",
            ],
        )
        plain_metadata = document.get_metadata()
        if "stanza" in plain_metadata:
            raise ValueError("stanza is body content and cannot appear in front matter")
        if plain_metadata.get("auto-lang") != AUTO_LANG:
            raise ValueError(f"auto-lang must be {AUTO_LANG!r}")

        allowed_metadata = {
            "auto-lang",
            "author",
            "category",
            "meter",
            "note",
            "ref",
            "title",
        }
        unknown = set(plain_metadata) - allowed_metadata
        if unknown:
            raise ValueError(f"unknown hymn metadata fields: {sorted(unknown)!r}")
        if "category" not in document.metadata:
            raise ValueError("missing hymn metadata field: 'category'")

        metadata: dict[str, Any] = {}
        if "author" in document.metadata:
            metadata["author"] = _localized_from_metadata(
                document.metadata["author"], "author"
            ).to_dict()

        metadata["category"] = _localized_from_metadata(
            document.metadata["category"], "category"
        ).to_dict()

        if "meter" in document.metadata:
            meter = _meter_from_metadata(document.metadata["meter"])
            metadata["meter"] = meter.to_dict() if isinstance(meter, LocalizedText) else meter
        for name in ("note", "ref"):
            if name in document.metadata:
                metadata[name] = _localized_from_metadata(
                    document.metadata[name], name
                ).to_dict()

        stanza: dict[int | str, list[dict[str, str]]] = {}
        current_name: int | str | None = None
        current_lines: list[dict[str, str]] = []
        for block in document.content:
            if isinstance(block, pf.Header):
                if block.level != 1:
                    raise ValueError("each stanza must begin with a level-one heading")
                if current_name is not None:
                    if not current_lines:
                        raise ValueError(f"stanza {current_name!r} cannot be empty")
                    stanza[current_name] = current_lines
                heading = pf.stringify(block)
                current_name = int(heading) if heading.isdecimal() else heading
                if current_name in stanza:
                    raise ValueError(f"duplicate stanza heading {current_name!r}")
                current_lines = []
            elif isinstance(block, pf.LineBlock) and current_name is not None:
                if current_lines:
                    raise ValueError("each stanza must contain exactly one line block")
                block_sources: list[str] = []
                for _ in block.content:
                    try:
                        block_sources.append(next(source_lines))
                    except StopIteration as error:
                        raise ValueError(
                            "Markdown source has fewer line-block lines than Pandoc parsed"
                        ) from error
                current_lines.extend(
                    line.to_dict()
                    for line in LyricLine.from_line_block(block, block_sources)
                )
            else:
                raise ValueError(
                    "document body must contain stanza headings and lyric line blocks"
                )
        if current_name is not None:
            if not current_lines:
                raise ValueError(f"stanza {current_name!r} cannot be empty")
            stanza[current_name] = current_lines

        try:
            next(source_lines)
        except StopIteration:
            pass
        else:
            raise ValueError("Markdown source has more line-block lines than Pandoc parsed")

        metadata["stanza"] = stanza
        if "title" in document.metadata:
            metadata["title"] = _localized_from_metadata(
                document.metadata["title"], "title"
            ).to_dict()
        return cls.from_dict(metadata)


def _line_block_sources(markdown: str) -> list[str]:
    """Return the Markdown source of each physical line-block line."""

    lines = markdown.splitlines()
    if lines and lines[0] == "---":
        for index, line in enumerate(lines[1:], start=1):
            if line in {"---", "..."}:
                lines = lines[index + 1 :]
                break
        else:
            raise ValueError("unterminated YAML metadata block")

    sources: list[str] = []
    for line in lines:
        if line == "|":
            sources.append("")
        elif line.startswith("| "):
            sources.append(line[2:])
    return sources
