"""Build-mode settings shared by projection and site rendering."""

from __future__ import annotations

import os


BUILD_MODE_ENV = "HYMN_BUILD_MODE"
DEVELOP = "develop"
PRODUCTION = "production"


def build_mode() -> str:
    """Return the validated build mode, defaulting to developer output."""

    mode = os.environ.get(BUILD_MODE_ENV, DEVELOP)
    if mode not in {DEVELOP, PRODUCTION}:
        raise ValueError(
            f"{BUILD_MODE_ENV} must be {DEVELOP!r} or {PRODUCTION!r}, not {mode!r}"
        )
    return mode
