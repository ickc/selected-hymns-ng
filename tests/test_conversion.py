"""Tests for the lossless hymn conversion boundaries."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import yaml

from hymn_projection.converter import markdown_to_yaml, yaml_to_markdown
from hymn_projection.model import Hymn


HYMN_DATA = {
    "author": {"en": "An Author"},
    "category": {"zh": "分類——測試"},
    "meter": {"en": "8.6.8.6. with chorus", "zh": "8.6.8.6. 和"},
    "note": {"en": "Keep *literal* Markdown"},
    "stanza": {
        1: [
            {"en": "A “quoted” line—with punctuation.", "zh": "第一行。"},
            {"zh": "　　保留全形空格。"},
        ],
        "1-chorus": [{"en": r"Literal ^[note] and \\[bracket\\]."}],
    },
    "title": {"en": "A title <!-- remains literal -->"},
}


class HymnConversionTest(TestCase):
    """Exercise the object and collection round trips."""

    def test_object_round_trip(self) -> None:
        hymn = Hymn.from_dict(HYMN_DATA)

        self.assertEqual(hymn.to_dict(), HYMN_DATA)
        self.assertEqual(Hymn.from_markdown(hymn.to_markdown()), hymn)

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

    def test_unknown_hymn_field_is_rejected(self) -> None:
        invalid = dict(HYMN_DATA, unexpected="value")

        with self.assertRaisesRegex(ValueError, "unknown hymn fields"):
            Hymn.from_dict(invalid)

    def test_explicit_null_is_rejected(self) -> None:
        invalid = dict(HYMN_DATA, meter=None)

        with self.assertRaisesRegex(ValueError, "meter must be"):
            Hymn.from_dict(invalid)
