"""Stage 4 (optional): remove duplicate rows from merged CSV files."""

from __future__ import annotations

import logging
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class DedupResult:
    """Outcome of deduplicating one file."""

    path: Path
    rows_read: int
    rows_written: int

    @property
    def duplicates_removed(self) -> int:
        return self.rows_read - self.rows_written


def dedupe_file(file_path: Path) -> DedupResult:
    """Remove duplicate data rows in-place, keeping the header and first
    occurrence of each row.

    Line-hash set is held in memory; suitable for month-sized CSV files.
    The original file is only replaced after the deduplicated copy is
    written completely.
    """
    temp_path = file_path.with_suffix(file_path.suffix + ".tmp")
    seen: set[str] = set()
    rows_read = 0
    rows_written = 0

    try:
        with file_path.open("r", errors="replace") as infile, temp_path.open("w") as outfile:
            header = next(infile, None)
            if header is None:
                temp_path.unlink(missing_ok=True)
                return DedupResult(path=file_path, rows_read=0, rows_written=0)
            outfile.write(header)

            for line in infile:
                rows_read += 1
                stripped = line.strip()
                if stripped and stripped not in seen:
                    outfile.write(line)
                    seen.add(stripped)
                    rows_written += 1

        temp_path.replace(file_path)
        return DedupResult(path=file_path, rows_read=rows_read, rows_written=rows_written)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def dedupe_directory(directory: Path, workers: int = 2) -> list[DedupResult]:
    """Deduplicate every ``*.csv`` file in ``directory`` in parallel."""
    if not directory.is_dir():
        raise FileNotFoundError(f"Directory does not exist: {directory}")

    csv_files = sorted(directory.glob("*.csv"))
    if not csv_files:
        logger.warning("No CSV files found in %s", directory)
        return []

    with ProcessPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(dedupe_file, csv_files))
