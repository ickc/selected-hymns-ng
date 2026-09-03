"""Tests for the one-way slide projection."""

from unittest import TestCase

from hymn_projection.model import Hymn
from hymn_projection.slides import (
    chorus_by_stanza,
    chorus_report_markdown,
    chorus_shape,
    chorus_sources,
    document_language,
    slides,
    split_lines,
    title,
    to_markdown,
)


def hymn(stanza: dict[object, list[dict[str, str]]], **fields: object) -> Hymn:
    """Build a hymn from stanzas alone, with the one required field filled."""

    return Hymn.from_dict({"category": {"zh": "分類"}, "stanza": stanza, **fields})


def labels(value: Hymn) -> list[str]:
    """Return the label of each slide, with the chorus label shortened."""

    return [
        "chorus" if slide.identifier.startswith("c") else slide.label
        for slide in slides(value)
    ]


class ChorusResolutionTest(TestCase):
    """The chorus each stanza is sung with, which the source only implies."""

    def test_a_hymn_without_a_chorus_is_its_stanzas(self) -> None:
        value = hymn({1: [{"en": "One"}], 2: [{"en": "Two"}]})

        self.assertEqual(labels(value), ["1", "2"])

    def test_a_single_chorus_is_repeated_after_every_stanza(self) -> None:
        value = hymn(
            {
                1: [{"en": "One"}],
                "1-chorus": [{"en": "Refrain"}],
                2: [{"en": "Two"}],
                3: [{"en": "Three"}],
            }
        )

        self.assertEqual(labels(value), ["1", "chorus", "2", "chorus", "3", "chorus"])

    def test_a_later_chorus_replaces_the_first_from_its_stanza_on(self) -> None:
        # Hymn 72's shape: stanzas 2 and 3 keep singing 1-chorus, and only
        # stanza 4 takes the new one.
        value = hymn(
            {
                1: [{"en": "One"}],
                "1-chorus": [{"en": "First refrain"}],
                2: [{"en": "Two"}],
                3: [{"en": "Three"}],
                4: [{"en": "Four"}],
                "4-chorus": [{"en": "Last refrain"}],
            }
        )
        sung = [slide.lines[0].translations["en"] for slide in slides(value)]

        self.assertEqual(
            sung,
            ["One", "First refrain", "Two", "First refrain", "Three", "First refrain",
             "Four", "Last refrain"],
        )

    def test_a_replacement_in_one_language_leaves_the_other_alone(self) -> None:
        # Hymn 668's shape: 3-chorus exists only in Chinese, so stanza 3 sings
        # the English of 1-chorus against a different Chinese chorus. The two
        # are not translations of each other, and are still sung together.
        value = hymn(
            {
                1: [{"en": "One", "zh": "一"}],
                "1-chorus": [{"en": "Refrain", "zh": "副歌"}],
                2: [{"en": "Two", "zh": "二"}],
                3: [{"en": "Three", "zh": "三"}],
                "3-chorus": [{"zh": "新副歌"}],
            }
        )
        resolved = chorus_by_stanza(value.stanzas)

        self.assertEqual(resolved[2]["en"][0].translations["en"], "Refrain")
        self.assertEqual(resolved[2]["zh"][0].translations["zh"], "副歌")
        self.assertEqual(resolved[3]["en"][0].translations["en"], "Refrain")
        self.assertEqual(resolved[3]["zh"][0].translations["zh"], "新副歌")
        self.assertEqual(
            slides(value)[-1].lines[0].translations, {"en": "Refrain", "zh": "新副歌"}
        )

    def test_choruses_of_unequal_length_keep_the_lines_they_have(self) -> None:
        value = hymn(
            {
                1: [{"en": "One", "zh": "一"}],
                "1-chorus": [{"en": "A", "zh": "甲"}, {"en": "B", "zh": "乙"}],
                2: [{"en": "Two", "zh": "二"}],
                "2-chorus": [{"zh": "丙"}],
            }
        )
        chorus = slides(value)[-1]

        self.assertEqual(chorus.lines[0].translations, {"en": "A", "zh": "丙"})
        self.assertEqual(chorus.lines[1].translations, {"en": "B"})


class StanzaDivisionTest(TestCase):
    """Long stanzas are divided into slides of even size."""

    def test_a_stanza_within_the_limit_is_one_slide(self) -> None:
        self.assertEqual(len(split_lines(list(range(4)), 4)), 1)

    def test_a_doubled_stanza_is_halved_rather_than_filled(self) -> None:
        self.assertEqual(split_lines(list(range(6)), 4), [[0, 1, 2], [3, 4, 5]])
        self.assertEqual(split_lines(list(range(8)), 4), [[0, 1, 2, 3], [4, 5, 6, 7]])

    def test_a_divided_stanza_says_which_part_is_showing(self) -> None:
        value = hymn({1: [{"en": str(number)} for number in range(6)]})

        self.assertEqual(labels(value), ["1 (1/2)", "1 (2/2)"])
        self.assertEqual([slide.identifier for slide in slides(value)], ["v1-1", "v1-2"])


class ProjectionTest(TestCase):
    """What the slide Markdown carries, and what it drops."""

    def test_a_hymn_without_a_title_is_named_by_its_first_line(self) -> None:
        value = hymn({1: [{"en": "God, our Father, we adore Thee!", "zh": "阿爸父神，我們拜你，"}]})

        self.assertEqual(
            title(value),
            {"en": "God, our Father, we adore Thee!", "zh": "阿爸父神，我們拜你"},
        )

    def test_a_hymn_with_a_title_keeps_it(self) -> None:
        value = hymn({1: [{"en": "First line"}]}, title={"en": "A Title"})

        self.assertEqual(title(value), {"en": "A Title"})

    def test_a_singing_instruction_leaves_the_lyric_line(self) -> None:
        value = hymn({1: [{"en": "We rise, O Lord, to build! ^[Repeat the last four lines]"}]})
        slide = slides(value)[0]

        self.assertEqual(slide.lines[0].translations["en"], "We rise, O Lord, to build!")
        self.assertEqual(slide.notes, [("en", "Repeat the last four lines")])

    def test_the_document_language_follows_a_monolingual_hymn(self) -> None:
        self.assertEqual(document_language(hymn({1: [{"zh": "一"}]})), "zh-Hant")
        self.assertEqual(document_language(hymn({1: [{"en": "One", "zh": "一"}]})), "en")

    def test_the_markdown_carries_language_spans_and_drops_the_meter(self) -> None:
        value = hymn(
            {1: [{"en": "One", "zh": "一"}], "1-chorus": [{"en": "Refrain"}]},
            meter="8.7.8.7.",
            note={"en": "A note"},
        )
        markdown = to_markdown(value, 104)

        self.assertIn("format: revealjs", markdown)
        self.assertIn("number: 104", markdown)
        self.assertNotIn("meter", markdown)
        self.assertIn("note: '[A note]{lang=en}'", markdown)
        self.assertIn("## 1 {#v1}", markdown)
        self.assertIn("[One]{lang=en}\\\n[一]{lang=zh-Hant}", markdown)
        self.assertIn("::: lyrics", markdown)

    def test_a_quote_in_the_metadata_survives_yaml(self) -> None:
        value = hymn({1: [{"en": "It's here"}]})

        self.assertIn("title: '[It''s here]{lang=en}'", to_markdown(value, 1))


class ChorusReportTest(TestCase):
    """The list of hymns whose chorus the projection had to work out."""

    def test_the_three_plain_shapes_are_named(self) -> None:
        none = hymn({1: [{"en": "One"}]})
        single = hymn({1: [{"en": "One"}], "1-chorus": [{"en": "R"}], 2: [{"en": "Two"}]})
        paired = hymn(
            {
                1: [{"en": "One"}],
                "1-chorus": [{"en": "R"}],
                2: [{"en": "Two"}],
                "2-chorus": [{"en": "S"}],
            }
        )

        self.assertEqual(chorus_shape(none), "none")
        self.assertEqual(chorus_shape(single), "single")
        self.assertEqual(chorus_shape(paired), "paired")

    def test_a_replacement_partway_through_is_the_shape_worth_checking(self) -> None:
        value = hymn(
            {
                1: [{"en": "One"}],
                "1-chorus": [{"en": "R"}],
                2: [{"en": "Two"}],
                3: [{"en": "Three"}],
                "3-chorus": [{"en": "S"}],
            }
        )

        self.assertEqual(chorus_shape(value), "mixed")

    def test_the_report_names_the_chorus_each_language_takes(self) -> None:
        mixed = hymn(
            {
                1: [{"en": "One", "zh": "一"}],
                "1-chorus": [{"en": "R", "zh": "甲"}],
                2: [{"en": "Two", "zh": "二"}],
                "2-chorus": [{"zh": "乙"}],
            }
        )
        report = chorus_report_markdown([(1, hymn({1: [{"en": "Plain"}]})), (668, mixed)])

        self.assertEqual(chorus_sources(mixed.stanzas)[2], {"en": "1-chorus", "zh": "2-chorus"})
        self.assertIn("| [668](slide/668.html) | 2 | `1-chorus` | `2-chorus` |", report)
        self.assertIn("1 hymns have no chorus", report)
        # A hymn needing no resolution is counted and then left out of the list.
        self.assertNotIn("slide/1.html", report)
