"""Stage 2: extract archives into a mirror ``{year}{month}`` tree.

Handles ``.zip`` (2009-2024) and ``.csv.zst`` (2025+). Legacy geodatabase
archives (``.gdb.zip``, 2011-2013) are handled by :mod:`noaa_integrator.gdb`.
"""

from __future__ import annotations

import logging
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

import zstandard

logger = logging.getLogger(__name__)

_YEAR_MONTH = re.compile(r"^\d{6}$")


@dataclass
class ExtractionReport:
    """Outcome of an extraction run."""

    extracted: list[Path] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)


def extract_zip(zip_path: Path, output_dir: Path) -> list[Path]:
    """Extract one ZIP archive after an integrity check.

    Raises ``zipfile.BadZipFile`` on corruption (including partial members).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        bad_member = archive.testzip()
        if bad_member is not None:
            raise zipfile.BadZipFile(f"Corrupted member in {zip_path}: {bad_member}")
        archive.extractall(output_dir)
        return [output_dir / name for name in archive.namelist()]


def extract_zst(zst_path: Path, output_dir: Path) -> Path:
    """Decompress one ``.csv.zst`` file (2025+ format)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / zst_path.name.removesuffix(".zst")
    decompressor = zstandard.ZstdDecompressor()
    with zst_path.open("rb") as compressed, target.open("wb") as plain:
        decompressor.copy_stream(compressed, plain)
    return target


def _extract_one(archive: Path, output_dir: Path) -> list[Path]:
    if archive.name.endswith(".csv.zst"):
        return [extract_zst(archive, output_dir)]
    return extract_zip(archive, output_dir)


def extract_tree(
    base_dir: Path,
    dest_dir: Path,
    start: str | None = None,
    end: str | None = None,
    workers: int = 8,
) -> ExtractionReport:
    """Extract every archive under ``base_dir/{yyyymm}/`` into ``dest_dir/{yyyymm}/``.

    ``start`` and ``end`` bound the ``yyyymm`` folders (inclusive, string
    comparison, e.g. ``"202301"``). Corrupted archives are reported, never fatal.
    """
    if not base_dir.is_dir():
        raise FileNotFoundError(f"Directory does not exist: {base_dir}")

    report = ExtractionReport()
    folders = sorted(
        entry
        for entry in base_dir.iterdir()
        if entry.is_dir()
        and _YEAR_MONTH.match(entry.name)
        and (start is None or entry.name >= start)
        and (end is None or entry.name <= end)
    )

    tasks: dict = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for folder in folders:
            output_dir = dest_dir / folder.name
            for archive in sorted(folder.iterdir()):
                if archive.name.endswith((".zip", ".csv.zst")):
                    tasks[executor.submit(_extract_one, archive, output_dir)] = archive

        for future in as_completed(tasks):
            archive = tasks[future]
            try:
                report.extracted.extend(future.result())
            except Exception as error:  # noqa: BLE001 - report and continue
                logger.error("Failed to extract %s: %s", archive, error)
                report.failed.append((archive, str(error)))

    return report
