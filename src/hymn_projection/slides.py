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


def chorus_sources(stanzas: list[Stanza]) -> dict[int, dict[str, str]]:
    """Name the chorus each numbered stanza's languages are sung with.

    Four shapes occur in the collection: no chorus at all; one ``1-chorus``
    repeated after every stanza; a chorus paired with each stanza; and a mix,
    where a later chorus replaces the first from that stanza on — sometimes in
    only one language, so that a hymn keeps singing the English of
    ``1-chorus`` under a new Chinese one.  Carrying the most recent chorus
    forward per language covers all four, and reproduces the instruction that
    hymn 705 states in prose without reading it.

    This is the rule itself, kept apart from the lyrics it selects so that the
    report in ``site/chorus.md`` names exactly what the slides sing.
    """

    latest: dict[str, str] = {}
    resolved: dict[int, dict[str, str]] = {}
    current: int | None = None
    for stanza in stanzas:
        if isinstance(stanza.name, int):
            current = stanza.name
            resolved[current] = dict(latest)
            continue
        for language in {l for line in stanza.lines for l in line.translations}:
            latest[language] = str(stanza.name)
        if current is not None:
            resolved[current] = dict(latest)
    return resolved


def chorus_by_stanza(stanzas: list[Stanza]) -> dict[int, dict[str, list[LyricLine]]]:
    """Return the lyrics of the chorus each numbered stanza is sung with."""

    named = {str(stanza.name): stanza for stanza in stanzas}
    return {
        number: {
            language: [
                line for line in named[name].lines if language in line.translations
            ]
            for language, name in sources.items()
        }
        for number, sources in chorus_sources(stanzas).items()
    }


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


def chorus_shape(hymn: Hymn) -> str:
    """Classify what the resolution had to do, not how the choruses are written.

    The two differ, which is the point of classifying this way. Hymns 284 and
    671 pair a chorus with every stanza and so look as though nothing is
    resolved — but their later choruses are Chinese only, so English still
    falls back to ``1-chorus``. Judging by the written shape would hide exactly
    the case worth checking.
    """

    numbers = [
        stanza.name for stanza in hymn.stanzas if isinstance(stanza.name, int)
    ]
    names = [
        str(stanza.name) for stanza in hymn.stanzas if not isinstance(stanza.name, int)
    ]
    if not names:
        return "none"
    sources = chorus_sources(hymn.stanzas)
    if names == ["1-chorus"]:
        return "single"
    if names == [f"{number}-chorus" for number in numbers] and all(
        set(sources[number].values()) == {f"{number}-chorus"} for number in numbers
    ):
        return "paired"
    return "mixed"


def chorus_report_markdown(entries: list[tuple[int, Hymn]]) -> str:
    """Report every hymn whose chorus the projection had to work out.

    Three of the four shapes need no thought: a hymn with no chorus, one whose
    single ``1-chorus`` is repeated throughout, and one pairing a chorus with
    each stanza all sing what is written where it is written.  The rest are
    resolved by a rule, and a rule applied to 848 hymns deserves somewhere it
    can be read against the hymnal. This page is that list, regenerated with
    the slides so it cannot drift from what they sing.
    """

    counts = {shape: 0 for shape in ("none", "single", "paired", "mixed")}
    mixed: list[tuple[int, Hymn]] = []
    for number, hymn in entries:
        shape = chorus_shape(hymn)
        counts[shape] += 1
        if shape == "mixed":
            mixed.append((number, hymn))

    lines = [
        "---",
        "title: Chorus resolution 和詩對照",
        "lang: en",
        "format: html",
        "---",
        "",
        "A congregation sings the chorus again after each stanza, and the source",
        "records each chorus once. Which chorus a stanza takes is therefore",
        "worked out rather than read: **each language takes the most recent",
        "chorus at or before its stanza.**",
        "",
        f"- {counts['none']} hymns have no chorus;",
        f"- {counts['single']} have one `1-chorus`, repeated throughout;",
        f"- {counts['paired']} pair a chorus with each stanza;",
        f"- {counts['mixed']} replace the chorus partway through, and are listed below.",
        "",
        "Only the last group needs checking. Where the two columns differ, the",
        "hymn sings one language's chorus against a different one in the other:",
        "that is the collection's own doing, not the rule's, and hymn 705 states",
        "it in prose (`第三至第六節用第二節和詩`).",
        "",
        "| Hymn | Stanza | English chorus | Chinese chorus |",
        "|---:|---:|---|---|",
    ]
    for number, hymn in mixed:
        for stanza, sources in sorted(chorus_sources(hymn.stanzas).items()):
            english = sources.get("en")
            chinese = sources.get("zh")
            lines.append(
                f"| [{number}](slide/{number}.html) | {stanza} "
                f"| {f'`{english}`' if english else '—'} "
                f"| {f'`{chinese}`' if chinese else '—'} |"
            )
    return "\n".join(lines) + "\n"


def index_markdown(entries: list[tuple[int, Hymn]]) -> str:
    """Render the landing page: a box to open a hymn by its number.

    A deck's URL is its number, which is how a hymn is called for, so typing
    the number is the whole of what this page has to do. It is generated
    rather than static only so that the highest number is the collection's
    own; ``goto.html`` reads the range off the field rather than repeating it.
    """

    highest = max(number for number, _ in entries)
    return "\n".join(
        [
            "---",
            "title: 詩歌選輯 Selected Hymns",
            "lang: en",
            # The project renders decks; this one page opts out. How that page
            # looks is `_quarto.yml`'s business, as it is for the decks.
            "format: html",
            "---",
            "",
            '<form class="hymn-goto" id="hymn-goto" autocomplete="off">',
            '  <label for="hymn-number">Hymn 詩歌</label>',
            '  <input id="hymn-number" type="number" inputmode="numeric"',
            f'         min="1" max="{highest}" step="1" placeholder="123"',
            '         aria-describedby="hymn-goto-message" autofocus>',
            '  <button type="submit">Open 開啟</button>',
            '  <span id="hymn-goto-message" class="hymn-goto-message" role="alert" hidden></span>',
            "</form>",
        ]
    ) + "\n"


def to_markdown(hymn: Hymn, number: int, limit: int = LINES_PER_SLIDE) -> str:
    """Render one hymn as the slide Markdown for a presentation writer."""

    metadata = [
        # A project declaring more than one format renders every document to
        # all of them unless the document picks one. Without this each deck is
        # also built as a plain page, over the top of itself.
        "format: revealjs",
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
