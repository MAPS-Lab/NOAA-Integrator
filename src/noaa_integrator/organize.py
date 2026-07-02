"""Stage 1: organize downloaded archives into ``{year}{month}`` folders.

NOAA file naming changed across the years; every known pattern is matched:

- 2025+:      ``{dlyear}_ais_{year}-{month}-{day}.csv.zst``
- 2015-2024:  ``{dlyear}_AIS_{year}_{month}_{day}.zip``
- 2009-2014:  ``{dlyear}_Zone{zz}_{year}_{month}.zip``
- 2011-2013:  ``{dlyear}_Zone{zz}_{year}_{month}.gdb.zip``

The leading ``{dlyear}_`` prefix is added by :mod:`noaa_integrator.download`.
"""

from __future__ import annotations

import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# Ordered: first match wins. Each entry is (pattern, year_group, month_group).
_PATTERNS: tuple[tuple[re.Pattern[str], int, int], ...] = (
    (re.compile(r"^(\d{4})_ais_(\d{4})-(\d{2})-\d{2}\.csv\.zst$"), 2, 3),
    (re.compile(r"^(\d{4})_AIS_(\d{4})_(\d{2})_\d{2}\.zip$"), 2, 3),
    (re.compile(r"^(\d{4})_Zone\d+_(\d{4})_(\d{2})\.gdb\.zip$"), 2, 3),
    (re.compile(r"^(\d{4})_Zone\d+_(\d{4})_(\d{2})\.zip$"), 2, 3),
)

ARCHIVE_SUFFIXES = (".zip", ".zst")


def parse_year_month(filename: str) -> tuple[str, str] | None:
    """Return ``(year, month)`` parsed from an archive file name, or None."""
    for pattern, year_group, month_group in _PATTERNS:
        match = pattern.match(filename)
        if match:
            return match.group(year_group), match.group(month_group)
    return None


def organize_file(path: Path, base_dir: Path) -> Path | None:
    """Move one archive into its ``{year}{month}`` folder. Returns new path."""
    parsed = parse_year_month(path.name)
    if parsed is None:
        return None
    year, month = parsed
    folder = base_dir / f"{year}{month}"
    folder.mkdir(parents=True, exist_ok=True)
    destination = folder / path.name
    shutil.move(str(path), str(destination))
    return destination


def organize_directory(base_dir: Path, workers: int = 8) -> tuple[list[Path], list[Path]]:
    """Group every archive in ``base_dir`` into ``{year}{month}`` subfolders.

    Returns ``(moved, skipped)`` lists. Both ``.zip`` and ``.csv.zst`` archives
    are handled (the original script only globbed ``*.zip`` and silently
    skipped 2025-format files).
    """
    if not base_dir.is_dir():
        raise FileNotFoundError(f"Directory does not exist: {base_dir}")

    candidates = [p for p in base_dir.iterdir() if p.is_file() and p.name.endswith(ARCHIVE_SUFFIXES)]
    moved: list[Path] = []
    skipped: list[Path] = []

    with ThreadPoolExecutor(max_workers=workers) as executor:
        destinations = executor.map(lambda p: organize_file(p, base_dir), candidates)
        for source, destination in zip(candidates, destinations, strict=True):
            if destination is None:
                skipped.append(source)
            else:
                moved.append(destination)

    return moved, skipped
