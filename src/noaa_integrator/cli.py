"""Command-line interface: one subcommand per pipeline stage."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from noaa_integrator import __version__, bbox, dedup, download, extract, organize

logger = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="noaa-integrator",
        description="Acquire and process NOAA Marine Cadastre AIS data into an AISdb-aligned database.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # download
    cmd = subparsers.add_parser("download", help="Download yearly AIS archives from coast.noaa.gov")
    cmd.add_argument("--start-year", type=int, required=True)
    cmd.add_argument("--end-year", type=int, required=True)
    cmd.add_argument("--dest", type=Path, default=Path("data/downloads"), help="Download directory")
    cmd.add_argument("--no-skip-existing", action="store_true", help="Re-download existing files")

    # organize
    cmd = subparsers.add_parser("organize", help="Group archives into {year}{month} folders")
    cmd.add_argument("--base-dir", type=Path, required=True, help="Directory holding downloaded archives")
    cmd.add_argument("--workers", type=int, default=8)

    # extract
    cmd = subparsers.add_parser("extract", help="Extract .zip / .csv.zst archives")
    cmd.add_argument("--base-dir", type=Path, required=True, help="Directory with {yyyymm} archive folders")
    cmd.add_argument("--dest", type=Path, required=True, help="Destination for extracted CSV files")
    cmd.add_argument("--start", help="First {yyyymm} folder to extract (inclusive)")
    cmd.add_argument("--end", help="Last {yyyymm} folder to extract (inclusive)")
    cmd.add_argument("--workers", type=int, default=8)

    # gdb
    cmd = subparsers.add_parser("gdb", help="Convert legacy .gdb.zip archives (2011-2013) to CSV")
    cmd.add_argument("archives", type=Path, nargs="+", help=".gdb.zip files to convert")
    cmd.add_argument("--dest", type=Path, required=True, help="Destination for CSV files")

    # filter
    cmd = subparsers.add_parser("filter", help="Filter CSV files to a geographic bounding box")
    cmd.add_argument("--base-dir", type=Path, required=True, help="Directory with {yyyymm} CSV folders")
    cmd.add_argument("--dest", type=Path, required=True, help="Destination for filtered CSV files")
    cmd.add_argument("--start-year", type=int, required=True)
    cmd.add_argument("--end-year", type=int, required=True)
    cmd.add_argument("--start-month", type=int, default=1)
    cmd.add_argument("--end-month", type=int, default=12)
    cmd.add_argument("--min-lon", type=float, required=True)
    cmd.add_argument("--min-lat", type=float, required=True)
    cmd.add_argument("--max-lon", type=float, required=True)
    cmd.add_argument("--max-lat", type=float, required=True)

    # dedup
    cmd = subparsers.add_parser("dedup", help="Remove duplicate rows from merged CSV files")
    cmd.add_argument("--directory", type=Path, required=True)
    cmd.add_argument("--workers", type=int, default=2)

    # simplify
    cmd = subparsers.add_parser("simplify", help="Simplify trajectories (vw, rdp, tdtr)")
    cmd.add_argument("files", type=Path, nargs="+", help="Merged CSV files to simplify")
    cmd.add_argument("--dest", type=Path, required=True)
    cmd.add_argument("--algorithm", choices=("vw", "rdp", "tdtr"), default="vw")
    cmd.add_argument("--threshold", type=float, default=1e-6)
    cmd.add_argument("--metrics", action="store_true", help="Also write similarity metrics")

    # load
    cmd = subparsers.add_parser("load", help="Decode CSV files into SQLite or PostgreSQL (AISdb)")
    cmd.add_argument("--source-dir", type=Path, required=True, help="Directory with {yyyymm} CSV folders")
    cmd.add_argument("--start-year", type=int, required=True)
    cmd.add_argument("--end-year", type=int, required=True)
    cmd.add_argument("--start-month", type=int, default=1)
    cmd.add_argument("--end-month", type=int, default=12)
    target = cmd.add_mutually_exclusive_group(required=True)
    target.add_argument("--sqlite", type=Path, help="SQLite database path")
    target.add_argument("--dsn", nargs="?", const="", help="libpq DSN (or set NOAA_PG_DSN)")
    cmd.add_argument("--source", default="noaa", help="Source label stored in the database")
    cmd.add_argument("--workers", type=int, default=6)
    cmd.add_argument("--timescaledb", action="store_true", help="Use TimescaleDB hypertables (PostgreSQL)")
    cmd.add_argument("--max-retries", type=int, default=3)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )

    if args.command == "download":
        files = download.download_range(
            args.start_year, args.end_year, args.dest, skip_existing=not args.no_skip_existing
        )
        logger.info("Downloaded %d files to %s", len(files), args.dest)

    elif args.command == "organize":
        moved, skipped = organize.organize_directory(args.base_dir, workers=args.workers)
        logger.info("Moved %d archives; %d unmatched", len(moved), len(skipped))
        for path in skipped:
            logger.warning("No matching pattern: %s", path.name)

    elif args.command == "extract":
        report = extract.extract_tree(args.base_dir, args.dest, start=args.start, end=args.end, workers=args.workers)
        logger.info("Extracted %d files; %d failures", len(report.extracted), len(report.failed))
        for archive, error in report.failed:
            logger.error("%s: %s", archive, error)
        if report.failed:
            return 1

    elif args.command == "gdb":
        from noaa_integrator import gdb as gdb_module

        for archive in args.archives:
            written = gdb_module.convert_gdb_zip_to_csv(archive, args.dest)
            logger.info("%s -> %d CSV files", archive.name, len(written))

    elif args.command == "filter":
        box = bbox.BBox(args.min_lon, args.min_lat, args.max_lon, args.max_lat)
        box.validate()
        total_kept = 0
        for year in range(args.start_year, args.end_year + 1):
            for month in range(args.start_month, args.end_month + 1):
                month_dir = args.base_dir / f"{year}{month:02d}"
                if not month_dir.is_dir():
                    logger.warning("Missing month directory: %s", month_dir)
                    continue
                files = sorted(month_dir.glob("*.csv"))
                results = bbox.filter_files(files, box, args.dest / f"{year}{month:02d}")
                kept = sum(result.rows_kept for result in results)
                total_kept += kept
                logger.info("%s%02d: %d rows kept across %d files", year, month, kept, len(files))
        logger.info("Filtering complete: %d rows kept", total_kept)

    elif args.command == "dedup":
        results = dedup.dedupe_directory(args.directory, workers=args.workers)
        removed = sum(result.duplicates_removed for result in results)
        logger.info("Deduplicated %d files; removed %d duplicate rows", len(results), removed)

    elif args.command == "simplify":
        from noaa_integrator import simplify as simplify_module

        for file_path in args.files:
            out_path, metrics_path = simplify_module.simplify_file(
                file_path, args.dest, algorithm=args.algorithm, threshold=args.threshold, with_metrics=args.metrics
            )
            logger.info("Wrote %s%s", out_path, f" and {metrics_path}" if metrics_path else "")

    elif args.command == "load":
        from noaa_integrator import load as load_module

        dsn = None if args.sqlite else load_module.resolve_dsn(args.dsn or None)
        report = load_module.load_months(
            source_dir=args.source_dir,
            start_year=args.start_year,
            end_year=args.end_year,
            start_month=args.start_month,
            end_month=args.end_month,
            sqlite_path=args.sqlite,
            postgres_dsn=dsn,
            source=args.source,
            workers=args.workers,
            timescaledb=args.timescaledb,
            max_retries=args.max_retries,
        )
        logger.info("Loaded %d batches; %d failed", len(report.loaded), len(report.failed))
        if report.failed:
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
