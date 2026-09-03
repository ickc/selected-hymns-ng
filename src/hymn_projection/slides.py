"""Project a hymn as the slide Markdown a presentation writer consumes.

This is a one-way projection, unlike the lossless ``data/N.md`` codec in
``model``.  It resolves what is actually sung — every stanza followed by the
chorus that belongs to it — and says nothing about how a slide looks.  Layout
lives in the presentation theme: the Markdown carries a ``lyrics`` Div, one
paragraph per lyric line, and a language span per translation, which the theme
renders interleaved or as aligned columns without this file changing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator

from .model import LANGUAGE_ORDER, Hymn, LyricLine, Stanza


# Four is the size of the most common stanza in the collection by a wide
# margin, so this keeps the great majority whole while halving the eight-line
# stanzas of a doubled meter at their natural break.
LINES_PER_SLIDE = 4
# The canonical collection is Traditional Chinese.  The projection's ``zh``
# becomes the specific tag a renderer can act on: CSS ``:lang()`` matches it by
# prefix, and Pandoc's LaTeX writer maps it to babel's ``chinese-hant``.
BCP47 = {"en": "en", "zh": "zh-Hant"}
# A Pandoc inline note, ``^[...]``, holding one level of nested brackets.  In
# this collection these are singing instructions rather than annotations of the
# text, so a slide shows them beside the stanza instead of as a footnote.
INLINE_NOTE = re.compile(r"\^\[([^\[\]]*(?:\[[^\]]*\][^\[\]]*)*)\]")
# Punctuation a lyric line ends with which a title should not.
TITLE_TRAILING = "，。、；：,;: "


def span(text: str, language: str) -> str:
    """Wrap text in the bracketed span carrying its language."""

    return f"[{text}]{{lang={BCP47[language]}}}"


def _yaml_scalar(text: str) -> str:
    """Quote one line of Markdown as a YAML scalar."""

    return "'" + text.replace("'", "''") + "'"


def _localized_inline(translations: dict[str, str]) -> str:
    """Render localized text as adjacent language spans."""

    return " ".join(span(text, language) for language, text in translations.items())


@dataclass
class Slide:
    """One projected slide: a label, its lyric lines, and its instructions."""

    identifier: str
    label: str
    lines: list[LyricLine]
    notes: list[tuple[str, str]] = field(default_factory=list)


def chorus_by_stanza(stanzas: list[Stanza]) -> dict[int, dict[str, list[LyricLine]]]:
    """Return the chorus each numbered stanza is sung with, per language.

    Four shapes occur in the collection: no chorus at all; one ``1-chorus``
    repeated after every stanza; a chorus paired with each stanza; and a mix,
    where a later chorus replaces the first from that stanza on — sometimes in
    only one language, so that a hymn keeps singing the English of
    ``1-chorus`` under a new Chinese one.  Carrying the most recent chorus
    forward per language covers all four, and reproduces the instruction that
    hymn 705 states in prose without reading it.
    """

    latest: dict[str, list[LyricLine]] = {}
    resolved: dict[int, dict[str, list[LyricLine]]] = {}
    current: int | None = None
    for stanza in stanzas:
        if isinstance(stanza.name, int):
            current = stanza.name
            resolved[current] = {
                language: list(lines) for language, lines in latest.items()
            }
            continue
        for language in {l for line in stanza.lines for l in line.translations}:
            latest[language] = [
                line for line in stanza.lines if language in line.translations
            ]
        if current is not None:
            resolved[current] = {
                language: list(lines) for language, lines in latest.items()
            }
    return resolved


def merge_languages(chorus: dict[str, list[LyricLine]]) -> list[LyricLine]:
    """Zip per-language chorus lines back into bilingual lyric lines."""

    if not chorus:
        return []
    languages = sorted(chorus, key=LANGUAGE_ORDER.__getitem__)
    lines: list[LyricLine] = []
    for index in range(max(len(run) for run in chorus.values())):
        translations = {
            language: chorus[language][index].translations[language]
            for language in languages
            if index < len(chorus[language])
        }
        if translations:
            lines.append(LyricLine(translations))
    return lines


def split_lines(
    lines: list[LyricLine], limit: int = LINES_PER_SLIDE
) -> list[list[LyricLine]]:
    """Divide a stanza into the fewest slides of no more than ``limit`` lines."""

    if limit < 1:
        raise ValueError("a slide must hold at least one lyric line")
    if len(lines) <= limit:
        return [lines]
    # Even parts rather than full ones: thirteen lines are 4-3-3-3, not
    # 4-4-4-1, so no stanza ends on a slide holding a single line.
    parts = -(-len(lines) // limit)
    size, remainder = divmod(len(lines), parts)
    divided: list[list[LyricLine]] = []
    start = 0
    for part in range(parts):
        end = start + size + (1 if part < remainder else 0)
        divided.append(lines[start:end])
        start = end
    return divided


def _extract_notes(lines: list[LyricLine]) -> tuple[list[LyricLine], list[tuple[str, str]]]:
    """Lift inline singing instructions out of the lyric lines they sit in."""

    notes: list[tuple[str, str]] = []
    stripped: list[LyricLine] = []
    for line in lines:
        translations: dict[str, str] = {}
        for language, text in line.translations.items():
            for note in INLINE_NOTE.findall(text):
                notes.append((language, note))
            translations[language] = INLINE_NOTE.sub("", text).strip()
        stripped.append(LyricLine(translations))
    return stripped, notes


def _parts(
    lines: list[LyricLine], identifier: str, label: str, limit: int
) -> Iterator[Slide]:
    """Yield the slides one stanza or chorus divides into."""

    divided = split_lines(lines, limit)
    for index, part in enumerate(divided, start=1):
        text, notes = _extract_notes(part)
        if len(divided) == 1:
            yield Slide(identifier, label, text, notes)
        else:
            yield Slide(
                f"{identifier}-{index}",
                f"{label} ({index}/{len(divided)})",
                text,
                notes,
            )


def slides(hymn: Hymn, limit: int = LINES_PER_SLIDE) -> list[Slide]:
    """Return the slides of one hymn, in the order it is sung."""

    chorus_label = f"{span('Chorus', 'en')} {span('副歌', 'zh')}"
    resolved = chorus_by_stanza(hymn.stanzas)
    result: list[Slide] = []
    for stanza in hymn.stanzas:
        if not isinstance(stanza.name, int):
            continue
        result.extend(_parts(stanza.lines, f"v{stanza.name}", str(stanza.name), limit))
        chorus = merge_languages(resolved.get(stanza.name, {}))
        if chorus:
            result.extend(_parts(chorus, f"c{stanza.name}", chorus_label, limit))
    return result


def title(hymn: Hymn) -> dict[str, str]:
    """Return the hymn's title, or the first line it is known by instead.

    One hymn in the collection carries a title.  A congregation names the rest
    by their opening line, which is what a slide should show.
    """

    if hymn.title is not None:
        return dict(hymn.title.translations)
    first = hymn.stanzas[0].lines[0].translations
    return {
        language: INLINE_NOTE.sub("", text).strip().rstrip(TITLE_TRAILING)
        for language, text in first.items()
    }


def document_language(hymn: Hymn) -> str:
    """Return the tag for the hymn as a whole, which its spans override."""

    languages = {
        language
        for stanza in hymn.stanzas
        for line in stanza.lines
        for language in line.translations
    }
    return BCP47["en" if "en" in languages else languages.pop()]


def _lyric_block(slide: Slide) -> str:
    """Render one slide's lyric lines, one paragraph each."""

    paragraphs = [
        "\\\n".join(span(text, language) for language, text in line.translations.items())
        for line in slide.lines
    ]
    return "::: lyrics\n" + "\n\n".join(paragraphs) + "\n:::"


def _note_block(slide: Slide) -> str:
    """Render the singing instructions found in one slide's lyric lines."""

    if not slide.notes:
        return ""
    ordered = sorted(slide.notes, key=lambda note: LANGUAGE_ORDER[note[0]])
    body = "\\\n".join(span(text, language) for language, text in ordered)
    return f"\n\n::: singing-note\n{body}\n:::"


def index_markdown(entries: list[tuple[int, Hymn]]) -> str:
    """Render the contents page the decks are reached from.

    A deck's own URL is its number, which is how a hymn is called for, so the
    directory only has to make the numbers findable and show enough of each
    hymn to recognise it by.
    """

    lines = [
        "---",
        "title: 詩歌選輯 Selected Hymns",
        "lang: en",
        # The project renders decks; this one page opts out. How that page
        # looks is `_quarto.yml`'s business, as it is for the decks.
        "format: html",
        "---",
        "",
        "::: hymn-index",
    ]
    for number, hymn in entries:
        named = " ".join(
            span(text, language) for language, text in title(hymn).items()
        )
        lines.append(f"[**{number}** {named}](slide/{number}.html)\\")
    lines[-1] = lines[-1].removesuffix("\\")
    lines.append(":::")
    return "\n".join(lines) + "\n"


def to_markdown(hymn: Hymn, number: int, limit: int = LINES_PER_SLIDE) -> str:
    """Render one hymn as the slide Markdown for a presentation writer."""

    metadata = [
        f"number: {number}",
        f"title: {_yaml_scalar(_localized_inline(title(hymn)))}",
        f"lang: {document_language(hymn)}",
        f"category: {_yaml_scalar(_localized_inline(hymn.category.translations))}",
    ]
    for name in ("author", "ref", "note"):
        value = getattr(hymn, name)
        if value is not None:
            metadata.append(
                f"{name}: {_yaml_scalar(_localized_inline(value.translations))}"
            )

    body = [
        f"## {slide.label} {{#{slide.identifier}}}\n\n"
        f"{_lyric_block(slide)}{_note_block(slide)}"
        for slide in slides(hymn, limit)
    ]
    return "---\n" + "\n".join(metadata) + "\n---\n\n" + "\n\n".join(body) + "\n"
