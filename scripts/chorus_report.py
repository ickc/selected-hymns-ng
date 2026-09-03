#!/usr/bin/env python3
"""Print the hymns whose chorus the slide projection has to work out.

A congregation sings the chorus again after each stanza, and the source records
each chorus once, so which chorus a stanza takes is resolved rather than read:
each language takes the most recent chorus at or before its stanza. Most hymns
need no thought. The ones that do are worth being able to list on demand and
check against the hymnal, which is what this is for.

    python scripts/chorus_report.py data
    python scripts/chorus_report.py data --expect 17   # fail if the list grows

Judging by the written shape is not enough: hymns 284 and 671 pair a chorus
with every stanza and still fall back, because their later choruses are Chinese
only. This classifies by what the resolution did.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hymn_projection.converter import numbered_markdown_files  # noqa: E402
from hymn_projection.model import Hymn  # noqa: E402
from hymn_projection.slides import chorus_shape, chorus_sources  # noqa: E402


SHAPES = {
    "none": "no chorus",
    "single": "one 1-chorus, repeated throughout",
    "paired": "a chorus with each stanza",
    "mixed": "the chorus replaced partway through",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="the data/ directory")
    parser.add_argument(
        "--expect",
        type=int,
        help="fail unless exactly this many hymns need resolving",
    )
    arguments = parser.parse_args()

    counts = {shape: 0 for shape in SHAPES}
    resolved: list[tuple[int, dict[int, dict[str, str]]]] = []
    for path in numbered_markdown_files(arguments.directory):
        hymn = Hymn.from_markdown(path.read_text(encoding="utf-8"))
        shape = chorus_shape(hymn)
        counts[shape] += 1
        if shape == "mixed":
            resolved.append((int(path.stem), chorus_sources(hymn.stanzas)))

    total = sum(counts.values())
    print(f"{total} hymns")
    for shape, description in SHAPES.items():
        print(f"  {counts[shape]:4d}  {description}")
    print()
    print(f"{len(resolved)} needing resolution:")
    for number, sources in resolved:
        print(f"  hymn {number}")
        for stanza, languages in sorted(sources.items()):
            taken = "  ".join(
                f"{language}: {name}" for language, name in sorted(languages.items())
            )
            # A stanza whose languages take different choruses is the case to
            # look at: the hymn sings one language's chorus against another's.
            mark = " *" if len(set(languages.values())) > 1 else ""
            print(f"    stanza {stanza}: {taken}{mark}")

    if arguments.expect is not None and len(resolved) != arguments.expect:
        print(
            f"expected {arguments.expect} hymns needing resolution, found {len(resolved)}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
