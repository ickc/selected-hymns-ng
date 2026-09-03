import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from scripts.build_site import _merge, _partition


class PartitionTest(TestCase):
    def test_every_hymn_belongs_to_one_balanced_worker(self) -> None:
        hymns = [Path(f"{number}.md") for number in range(1, 9)]

        partitions = _partition(hymns, 3)

        self.assertEqual([len(partition) for partition in partitions], [3, 3, 2])
        self.assertCountEqual([path for partition in partitions for path in partition], hymns)


class MergeTest(TestCase):
    def test_search_indexes_and_disjoint_decks_are_combined(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            outputs = [root / "worker-1", root / "worker-2"]
            for output in outputs:
                (output / "slide").mkdir(parents=True)
                (output / "site_libs").mkdir()
                (output / "site_libs" / "shared.js").write_text("same", encoding="utf-8")
            (outputs[0] / "index.html").write_text("real index", encoding="utf-8")
            (outputs[1] / "index.html").write_text("worker redirect", encoding="utf-8")
            (outputs[0] / "slide" / "1.html").write_text("one", encoding="utf-8")
            (outputs[1] / "slide" / "2.html").write_text("two", encoding="utf-8")
            (outputs[0] / "search.json").write_text(
                json.dumps(
                    [
                        {"objectID": "slide/1.html#v2", "href": "slide/1.html#v2"},
                        {"objectID": "slide/1.html#v10", "href": "slide/1.html#v10"},
                    ]
                ),
                encoding="utf-8",
            )
            (outputs[1] / "search.json").write_text(
                json.dumps([{"objectID": "slide/2.html#v1", "href": "slide/2.html#v1"}]),
                encoding="utf-8",
            )

            destination = root / "combined"
            count = _merge(outputs, destination)

            self.assertEqual(count, 3)
            self.assertEqual((destination / "index.html").read_text(), "real index")
            self.assertTrue((destination / "slide" / "1.html").is_file())
            self.assertTrue((destination / "slide" / "2.html").is_file())
            entries = json.loads((destination / "search.json").read_text())
            self.assertEqual(
                [entry["objectID"] for entry in entries],
                ["slide/1.html#v2", "slide/1.html#v10", "slide/2.html#v1"],
            )

    def test_the_chorus_report_cannot_enter_the_merged_search(self) -> None:
        with TemporaryDirectory() as temporary:
            output = Path(temporary) / "worker"
            output.mkdir()
            (output / "index.html").write_text("index", encoding="utf-8")
            (output / "search.json").write_text(
                json.dumps([{"objectID": "chorus.html", "href": "chorus.html"}]),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(RuntimeError, "chorus report"):
                _merge([output], Path(temporary) / "combined")
