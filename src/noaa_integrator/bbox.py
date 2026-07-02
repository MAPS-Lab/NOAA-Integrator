"""Stage 3 (optional): filter AIS CSV files to a geographic bounding box."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import pandas as pd

logger = logging.getLogger(__name__)

_CHUNK_ROWS = 100_000


class BBox(NamedTuple):
    """Geographic bounding box in WGS84 degrees."""

    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float

    def validate(self) -> None:
        if not (-180.0 <= self.min_lon <= self.max_lon <= 180.0):
            raise ValueError(f"Invalid longitude range: {self.min_lon}..{self.max_lon}")
        if not (-90.0 <= self.min_lat <= self.max_lat <= 90.0):
            raise ValueError(f"Invalid latitude range: {self.min_lat}..{self.max_lat}")


@dataclass
class FilterResult:
    """Per-file outcome of a bounding-box filter."""

    source: Path
    output: Path | None
    rows_processed: int = 0
    rows_kept: int = 0
    rows_skipped: int = 0


def filter_csv(
    file_path: Path,
    bbox: BBox,
    output_path: Path,
    lon_column: str = "LON",
    lat_column: str = "LAT",
) -> FilterResult:
    """Filter one CSV, writing only rows inside ``bbox``.

    Non-numeric coordinates and malformed lines are skipped. If no row falls
    inside the box, no output file is left behind (``result.output is None``).
    """
    bbox.validate()
    result = FilterResult(source=file_path, output=None)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    first_chunk = True
    chunks = pd.read_csv(
        file_path,
        chunksize=_CHUNK_ROWS,
        on_bad_lines="skip",
        encoding_errors="replace",
        low_memory=False,
    )
    for chunk in chunks:
        result.rows_processed += len(chunk)
        if lon_column not in chunk.columns or lat_column not in chunk.columns:
            logger.warning("Columns %s/%s not found in %s", lon_column, lat_column, file_path)
            result.rows_skipped += len(chunk)
            continue

        chunk[lon_column] = pd.to_numeric(chunk[lon_column], errors="coerce")
        chunk[lat_column] = pd.to_numeric(chunk[lat_column], errors="coerce")
        valid = chunk.dropna(subset=[lon_column, lat_column])
        result.rows_skipped += len(chunk) - len(valid)

        mask = (
            (valid[lon_column] >= bbox.min_lon)
            & (valid[lon_column] <= bbox.max_lon)
            & (valid[lat_column] >= bbox.min_lat)
            & (valid[lat_column] <= bbox.max_lat)
        )
        selected = valid[mask]
        result.rows_kept += len(selected)

        if not selected.empty:
            selected.to_csv(output_path, mode="w" if first_chunk else "a", index=False, header=first_chunk)
            first_chunk = False

    if result.rows_kept > 0 and output_path.exists():
        result.output = output_path
    elif output_path.exists():
        output_path.unlink()

    return result


def filter_files(
    file_paths: list[Path],
    bbox: BBox,
    output_dir: Path,
    prefix: str = "",
) -> list[FilterResult]:
    """Filter many CSV files into ``output_dir``; returns per-file results."""
    results: list[FilterResult] = []
    for file_path in file_paths:
        output_path = output_dir / f"{prefix}{file_path.name}"
        try:
            results.append(filter_csv(file_path, bbox, output_path))
        except Exception as error:  # noqa: BLE001 - report and continue with next file
            logger.error("Error filtering %s: %s", file_path, error)
            results.append(FilterResult(source=file_path, output=None))
    return results
