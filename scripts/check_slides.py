#!/usr/bin/env python3
"""Check every rendered hymn deck for lyrics that do not fit its slides.

No one is going to look at 848 decks. This loads each one in the headless
browser Quarto already installs and reads back what `site/fit.html` recorded:
the type size the hymn settled on, and whether any slide still overflows at
that size. A deck that overflows is a failure; a deck that had to go very small
is reported so the stanza division can be looked at.

    python scripts/check_slides.py site/_site/slide
"""

from __future__ import annotations

import argparse
import concurrent.futures
import os
import re
import subprocess
import sys
from pathlib import Path

# Below this the words are still legible on a projector but the slide is
# crowded. It is a review threshold, not a failure.
SMALL_TYPE = 28.0
CHROME = (
    Path.home()
    / ".local/share/quarto/chrome-headless-shell/chrome-headless-shell-linux64"
    / "chrome-headless-shell"
)
ATTRIBUTE = re.compile(r'data-fit-(size|overflow|slides)="([0-9.]+)"')


def measure(chrome: Path, path: Path, timeout: int) -> dict[str, float]:
    """Load one deck and return what its fitting recorded."""

    result = subprocess.run(
        [
            str(chrome),
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--virtual-time-budget=15000",
            "--dump-dom",
            path.resolve().as_uri(),
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return {name: float(value) for name, value in ATTRIBUTE.findall(result.stdout)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="rendered deck directory")
    parser.add_argument("--chrome", type=Path, default=CHROME)
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--small-type", type=float, default=SMALL_TYPE)
    arguments = parser.parse_args()

    if not arguments.chrome.exists():
        parser.error(
            f"{arguments.chrome} is missing; run `quarto install chrome-headless-shell`"
        )
    decks = sorted(
        arguments.directory.glob("*.html"),
        key=lambda path: (not path.stem.isdecimal(), path.stem.zfill(8)),
    )
    if not decks:
        parser.error(f"no rendered decks in {arguments.directory}")

    unfitted: list[Path] = []
    failed: list[tuple[Path, Exception]] = []
    overflowing: list[tuple[Path, float]] = []
    small: list[tuple[Path, float]] = []
    sizes: list[float] = []
    slides = 0

    with concurrent.futures.ThreadPoolExecutor(arguments.jobs) as pool:
        futures = {
            pool.submit(measure, arguments.chrome, deck, arguments.timeout): deck
            for deck in decks
        }
        for future in concurrent.futures.as_completed(futures):
            deck = futures[future]
            # One browser that hangs or dies must not take the run with it. The
            # exception would otherwise leave this loop, and the pool would
            # still wait for all 800-odd decks still queued before anything was
            # reported at all -- the whole render budget spent to say nothing.
            try:
                measured = future.result()
            except Exception as error:
                failed.append((deck, error))
                continue
            if "size" not in measured:
                unfitted.append(deck)
                continue
            slides += int(measured.get("slides", 0))
            sizes.append(measured["size"])
            if measured.get("overflow", 0.0) > 0.5:
                overflowing.append((deck, measured["overflow"]))
            if measured["size"] < arguments.small_type:
                small.append((deck, measured["size"]))

    print(f"{len(decks)} decks, {slides} slides")
    if sizes:
        ordered = sorted(sizes)
        print(
            f"lyric type {ordered[0]:.1f}px smallest, "
            f"{ordered[len(ordered) // 2]:.1f}px median, "
            f"{ordered[-1]:.1f}px largest"
        )
    for deck, size in sorted(small, key=lambda item: item[1]):
        print(f"  small type {size:5.1f}px  {deck.name}")
    for deck, overflow in sorted(overflowing, key=lambda item: -item[1]):
        print(f"  OVERFLOWS by {overflow:.1f}px  {deck.name}", file=sys.stderr)
    for deck in unfitted:
        print(f"  NOT FITTED (no data-fit-size)  {deck.name}", file=sys.stderr)
    for deck, error in failed:
        print(f"  NOT MEASURED ({error!r})  {deck.name}", file=sys.stderr)

    return 1 if overflowing or unfitted or failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
