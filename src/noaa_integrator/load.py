"""Stage 6: decode filtered CSV files into an AISdb-aligned database.

Requires the ``load`` extra (``uv sync --extra load``) which pulls in the
``aisdb`` package. Credentials are never hardcoded: pass a libpq DSN via
``--dsn`` or the ``NOAA_PG_DSN`` environment variable.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

DSN_ENV_VAR = "NOAA_PG_DSN"


@dataclass
class LoadReport:
    """Outcome of a load run over month batches."""

    loaded: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


def _require_aisdb():  # noqa: ANN202 - optional dependency gate
    try:
        # pyrefly: ignore[missing-import]  - provided by the optional 'load' extra
        import aisdb
    except ImportError as error:
        raise ImportError("Loading needs the 'load' extra: uv sync --extra load") from error
    return aisdb


def resolve_dsn(dsn: str | None) -> str:
    """Resolve the PostgreSQL DSN from argument or environment."""
    resolved = dsn or os.environ.get(DSN_ENV_VAR)
    if not resolved:
        raise ValueError(f"No PostgreSQL DSN: pass --dsn or set {DSN_ENV_VAR}")
    return resolved


def _month_batches(start_year: int, end_year: int, start_month: int, end_month: int) -> list[str]:
    """Inclusive ``yyyymm`` batches; month bounds apply to every year."""
    return [
        f"{year}{month:02d}" for year in range(start_year, end_year + 1) for month in range(start_month, end_month + 1)
    ]


def _load_month(
    aisdb,  # noqa: ANN001 - module object
    year_month: str,
    source_dir: Path,
    dbconn,  # noqa: ANN001 - aisdb connection object
    source: str,
    workers: int,
    timescaledb: bool,
) -> None:
    filepaths = aisdb.glob_files(str(source_dir / year_month), ".csv")
    filepaths = sorted(path for path in filepaths if year_month in path)
    logger.info("Loading %s: %d files", year_month, len(filepaths))
    if not filepaths:
        return

    kwargs = {
        "dbconn": dbconn,
        "source": source,
        "verbose": True,
        "skip_checksum": True,
        "raw_insertion": True,
        "workers": workers,
    }
    if timescaledb:
        kwargs["timescaledb"] = True
    aisdb.decode_msgs(filepaths, **kwargs)


def load_months(
    source_dir: Path,
    start_year: int,
    end_year: int,
    start_month: int = 1,
    end_month: int = 12,
    sqlite_path: Path | None = None,
    postgres_dsn: str | None = None,
    source: str = "noaa",
    workers: int = 6,
    timescaledb: bool = False,
    max_retries: int = 3,
    retry_wait: float = 10.0,
) -> LoadReport:
    """Load ``{yyyymm}`` folders of CSV files into SQLite or PostgreSQL.

    Exactly one of ``sqlite_path`` / ``postgres_dsn`` must be provided. Failed
    month batches are retried up to ``max_retries`` times.
    """
    if (sqlite_path is None) == (postgres_dsn is None):
        raise ValueError("Provide exactly one of sqlite_path or postgres_dsn")

    aisdb = _require_aisdb()
    report = LoadReport()
    pending = _month_batches(start_year, end_year, start_month, end_month)

    def connect():  # noqa: ANN202 - aisdb connection context
        if sqlite_path is not None:
            return aisdb.SQLiteDBConn(dbpath=str(sqlite_path))
        return aisdb.PostgresDBConn(libpq_connstring=postgres_dsn)

    for attempt in range(max_retries + 1):
        if not pending:
            break
        if attempt > 0:
            logger.info("Retry %d for %d failed batches", attempt, len(pending))
            time.sleep(retry_wait)

        still_failing: list[str] = []
        for year_month in pending:
            batch_start = time.monotonic()
            try:
                with connect() as dbconn:
                    _load_month(aisdb, year_month, source_dir, dbconn, source, workers, timescaledb)
                report.loaded.append(year_month)
            except Exception as error:  # noqa: BLE001 - collect and retry
                logger.error("Error loading %s: %s", year_month, error)
                still_failing.append(year_month)
            logger.info("Batch %s took %.2f s", year_month, time.monotonic() - batch_start)
        pending = still_failing

    report.failed = pending
    if report.failed:
        logger.error("Batches failed after %d retries: %s", max_retries, ", ".join(report.failed))
    return report
