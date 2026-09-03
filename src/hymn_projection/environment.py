"""Build-mode settings shared by projection and site rendering."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


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


def _linux_physical_cores(cpuinfo: str, allowed: set[int] | None = None) -> int | None:
    cores: set[tuple[str, str]] = set()
    for block in cpuinfo.split("\n\n"):
        fields = {}
        for line in block.splitlines():
            name, separator, value = line.partition(":")
            if separator:
                fields[name.strip()] = value.strip()
        try:
            processor = int(fields["processor"])
            core = (fields["physical id"], fields["core id"])
        except (KeyError, ValueError):
            continue
        if allowed is None or processor in allowed:
            cores.add(core)
    return len(cores) or None


def physical_cpu_count() -> int:
    """Return usable physical cores, with a logical-core fallback."""

    if sys.platform.startswith("linux"):
        try:
            allowed = set(os.sched_getaffinity(0))
        except AttributeError:
            allowed = None
        try:
            count = _linux_physical_cores(
                Path("/proc/cpuinfo").read_text(encoding="utf-8"), allowed
            )
        except OSError:
            count = None
        if count is not None:
            return count
        if allowed:
            return len(allowed)
    elif sys.platform == "darwin":
        result = subprocess.run(
            ["sysctl", "-n", "hw.physicalcpu"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip().isdecimal():
            return int(result.stdout)
    return os.cpu_count() or 1
