"""Tests for the lossless hymn conversion boundaries."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import yaml

from hymn_projection.converter import (
    markdown_to_slides,
    markdown_to_yaml,
    yaml_to_markdown,
)
from hymn_projection.environment import BUILD_MODE_ENV
from hymn_projection.model import Hymn


HYMN_DATA = {
    "author": {"en": "An Author"},
    "category": {"zh": "分類——測試"},
    "meter": {"en": "8.6.8.6. with chorus", "zh": "8.6.8.6. 和"},
    "note": {"en": "Keep *meaningful* Markdown"},
    "stanza": {
        1: [
            {"en": "A “quoted” line—with punctuation.", "zh": "第一行。"},
            {"zh": "　　保留全形空格。"},
        ],
        "1-chorus": [{"en": "A line with *emphasis* and ^[a note]."}],
    },
    "title": {"en": "A title <!-- remains literal -->"},
}


class HymnConversionTest(TestCase):
    """Exercise the object and collection round trips."""

    def test_object_round_trip(self) -> None:
        hymn = Hymn.from_dict(HYMN_DATA)
        markdown = hymn.to_markdown()

        self.assertEqual(hymn.to_dict(), HYMN_DATA)
        self.assertEqual(Hymn.from_markdown(markdown), hymn)
        self.assertNotIn("{lang=", markdown)
        self.assertNotIn("auto-lang:", markdown)
        self.assertIn("category: 分類——測試", markdown)
        self.assertIn("meter: 8.6.8.6. with chorus和", markdown)
        self.assertIn("A “quoted” line—with punctuation.\n第一行。", markdown)
        self.assertIn("第一行。\n　　保留全形空格。\n", markdown)
        self.assertIn("note: Keep *meaningful* Markdown", markdown)
        self.assertIn("A line with *emphasis* and ^[a note].", markdown)

    def test_latin_scalar_meter_remains_a_scalar(self) -> None:
        hymn = Hymn.from_dict(dict(HYMN_DATA, meter="C.M."))

        recovered = Hymn.from_markdown(hymn.to_markdown())

        self.assertEqual(recovered.meter, "C.M.")

    def test_double_meter_notation_is_shared_between_languages(self) -> None:
        meter = {
            "en": "7.7.7.7.D. with repeat",
            "zh": "7.7.7.7.D. 重",
        }
        hymn = Hymn.from_dict(dict(HYMN_DATA, meter=meter))
        markdown = hymn.to_markdown()

        self.assertIn("meter: 7.7.7.7.D. with repeat重", markdown)
        self.assertEqual(Hymn.from_markdown(markdown).meter.to_dict(), meter)

    def test_directory_round_trip_is_byte_exact(self) -> None:
        source_yaml = yaml.safe_dump([HYMN_DATA], allow_unicode=True, sort_keys=False)
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.yml"
            markdown = root / "data"
            recovered = root / "recovered.yml"
            source.write_text(source_yaml, encoding="utf-8")

            yaml_to_markdown(source, markdown)
            markdown_to_yaml(markdown, recovered)

            self.assertEqual(recovered.read_bytes(), source.read_bytes())

    def test_an_empty_source_directory_is_named_as_the_problem(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            empty = Path(temporary_directory) / "data"
            empty.mkdir()

            with self.assertRaisesRegex(ValueError, "no N.md files"):
                markdown_to_yaml(empty, Path(temporary_directory) / "out.yml")

    def test_a_hymn_that_leaves_the_source_leaves_the_projection(self) -> None:
        source_yaml = yaml.safe_dump([HYMN_DATA, HYMN_DATA], allow_unicode=True, sort_keys=False)
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.yml"
            markdown = root / "data"
            slides = root / "site" / "slide"
            source.write_text(source_yaml, encoding="utf-8")
            yaml_to_markdown(source, markdown)
            markdown_to_slides(markdown, slides, jobs=2)
            self.assertTrue((slides / "2.md").exists())

            (markdown / "2.md").unlink()
            markdown_to_slides(markdown, slides, jobs=2)

            self.assertFalse((slides / "2.md").exists())
            self.assertTrue((slides / "1.md").exists())

    def test_developer_projection_writes_the_chorus_report(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "data"
            source.mkdir()
            (source / "1.md").write_text(
                Hymn.from_dict(HYMN_DATA).to_markdown(), encoding="utf-8"
            )

            with patch.dict("os.environ", {BUILD_MODE_ENV: "develop"}):
                markdown_to_slides(source, root / "site" / "slide", jobs=1)

            report = (root / "site" / "chorus.md").read_text(encoding="utf-8")
            self.assertIn("search: false", report)

    def test_production_projection_removes_the_chorus_report(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "data"
            site = root / "site"
            source.mkdir()
            site.mkdir()
            (source / "1.md").write_text(
                Hymn.from_dict(HYMN_DATA).to_markdown(), encoding="utf-8"
            )
            (site / "chorus.md").write_text("stale", encoding="utf-8")
            (site / "chorus.html").write_text("stale", encoding="utf-8")

            with patch.dict("os.environ", {BUILD_MODE_ENV: "production"}):
                markdown_to_slides(source, site / "slide", jobs=1)

            self.assertFalse((site / "chorus.md").exists())
            self.assertFalse((site / "chorus.html").exists())

    def test_parallel_projection_is_byte_identical(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "data"
            source.mkdir()
            for number in range(1, 4):
                (source / f"{number}.md").write_text(
                    Hymn.from_dict(HYMN_DATA).to_markdown(), encoding="utf-8"
                )

            serial = root / "serial" / "slide"
            parallel = root / "parallel" / "slide"
            markdown_to_slides(source, serial, jobs=1)
            markdown_to_slides(source, parallel, jobs=3)

            serial_files = {
                path.relative_to(serial.parent): path.read_bytes()
                for path in serial.parent.rglob("*")
                if path.is_file()
            }
            parallel_files = {
                path.relative_to(parallel.parent): path.read_bytes()
                for path in parallel.parent.rglob("*")
                if path.is_file()
            }
            self.assertEqual(parallel_files, serial_files)

    def test_unknown_hymn_field_is_rejected(self) -> None:
        invalid = dict(HYMN_DATA, unexpected="value")

        with self.assertRaisesRegex(ValueError, "unknown hymn fields"):
            Hymn.from_dict(invalid)

    def test_explicit_null_is_rejected(self) -> None:
        invalid = dict(HYMN_DATA, meter=None)

        with self.assertRaisesRegex(ValueError, "meter must be"):
            Hymn.from_dict(invalid)
