"""Legacy support: convert 2011-2013 geodatabase archives (``.gdb.zip``) to CSV.

Requires the ``gdb`` extra: ``uv sync --extra gdb`` (geopandas + fiona).
"""

from __future__ import annotations

import logging
import tempfile
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)

_CHUNK_ROWS = 100_000


def _require_geo():  # noqa: ANN202 - optional dependency gate
    try:
        import fiona
        import geopandas
    except ImportError as error:
        raise ImportError("GDB conversion needs the 'gdb' extra: uv sync --extra gdb") from error
    return geopandas, fiona


def convert_gdb_zip_to_csv(zip_file: Path, output_dir: Path) -> list[Path]:
    """Convert every layer of a zipped ESRI geodatabase into CSV files.

    Point geometries are flattened into ``X``/``Y`` columns. Returns the list
    of CSV files written.
    """
    geopandas, fiona = _require_geo()
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    with tempfile.TemporaryDirectory(prefix="noaa-gdb-") as tmp:
        tmp_dir = Path(tmp)
        with zipfile.ZipFile(zip_file) as archive:
            archive.extractall(tmp_dir)

        gdb_dirs = sorted(tmp_dir.rglob("*.gdb"))
        if not gdb_dirs:
            logger.warning("No .gdb folder found inside %s", zip_file)
            return written

        for gdb_path in gdb_dirs:
            identifier = gdb_path.stem
            for layer in fiona.listlayers(gdb_path):
                frame = geopandas.read_file(gdb_path, layer=layer)
                if "geometry" in frame.columns:
                    frame["X"] = frame.geometry.x
                    frame["Y"] = frame.geometry.y
                    frame = frame.drop(columns="geometry")

                csv_path = output_dir / f"{identifier}_{layer}.csv"
                for offset in range(0, len(frame), _CHUNK_ROWS):
                    chunk = frame.iloc[offset : offset + _CHUNK_ROWS]
                    chunk.to_csv(csv_path, mode="w" if offset == 0 else "a", index=False, header=offset == 0)
                written.append(csv_path)
                logger.info("Wrote %s (%d rows)", csv_path, len(frame))

    return written
