# NOAA-Integrator

Acquisition and processing of AIS data from [NOAA Marine Cadastre](https://hub.marinecadastre.gov/pages/vesseltraffic), with integration into an [AISdb](https://github.com/MAPS-Lab/AISdb)-aligned database (SQLite or PostgreSQL/TimescaleDB). It consumes the NOAA archive at `https://coast.noaa.gov/htdata/CMSP/AISDataHandler/{year}/` and supports every published format, including daily ZIP archives (2015-2024), zone archives (2009-2014), legacy geodatabases (`.gdb.zip`, 2011-2013), and Zstandard-compressed CSV (`.csv.zst`, 2025 onward).

## Features

- Downloads every archive NOAA publishes for a year range, resume-friendly by default
- Organizes archives into `{year}{month}` folders across all NOAA naming schemes since 2009
- Extracts `.zip` (with integrity check) and `.csv.zst`, and converts legacy `.gdb.zip` geodatabases
- Filters records to a WGS84 bounding box, skipping and counting malformed rows
- Deduplicates rows in place with atomic replacement
- Simplifies per-vessel trajectories (Visvalingam-Whyatt, Douglas-Peucker, TDTR) with optional quality metrics
- Loads month batches into SQLite or PostgreSQL/TimescaleDB through `aisdb.decode_msgs`, with retries

## Installation

```bash
uv sync                      # core pipeline (download, organize, extract, filter, dedup)
uv sync --extra load         # + aisdb for database loading
uv sync --extra gdb          # + geopandas/fiona for legacy .gdb.zip conversion
uv sync --extra simplify     # + rdp/fastdtw/similaritymeasures for trajectory simplification
```

## Quick start

Download one year, organize it, extract it, and load it into a SQLite database.

```bash
uv sync --extra load
uv run noaa-integrator download --start-year 2024 --end-year 2024 --dest data/downloads
uv run noaa-integrator organize --base-dir data/downloads
uv run noaa-integrator extract --base-dir data/downloads --dest data/extracted --start 202401 --end 202412
uv run noaa-integrator load --source-dir data/extracted \
    --start-year 2024 --end-year 2024 --sqlite marine_cadastre.db
```

## Pipeline

Each stage is a subcommand of `noaa-integrator`. Stages are independent; run the ones you need, in order.

### 1. Download

```bash
uv run noaa-integrator download --start-year 2023 --end-year 2024 --dest data/downloads
```

Scrapes the NOAA index per year and streams every archive. Existing non-empty files are skipped (resume-friendly); force with `--no-skip-existing`.

### 2. Organize

```bash
uv run noaa-integrator organize --base-dir data/downloads
```

Groups archives into `{year}{month}` folders (for example `202406/`), matching every NOAA naming scheme from 2009 to 2025+.

### 3. Extract

```bash
uv run noaa-integrator extract --base-dir data/downloads --dest data/extracted --start 202301 --end 202312
```

Decompresses `.zip` (with integrity check) and `.csv.zst` archives into a mirror `{yyyymm}` tree. Corrupted archives are reported and skipped, never fatal.

Legacy geodatabase archives (2011-2013) convert separately.

```bash
uv run noaa-integrator gdb data/downloads/201303/*.gdb.zip --dest data/extracted/201303
```

### 4. Filter (optional)

```bash
uv run noaa-integrator filter \
    --base-dir data/extracted --dest data/filtered \
    --start-year 2023 --end-year 2023 --start-month 1 --end-month 2 \
    --min-lon -77.36 --min-lat 36.02 --max-lon -57.62 --max-lat 48.64
```

Keeps only records inside the WGS84 bounding box. Malformed rows and non-numeric coordinates are skipped and counted; months without matching data produce no output files.

### 5. Dedup (optional)

```bash
uv run noaa-integrator dedup --directory data/merged
```

Removes duplicate rows in-place (header preserved, atomic replace).

### 6. Simplify (optional)

```bash
uv run noaa-integrator simplify data/merged/*.csv --dest data/simplified --algorithm vw --metrics
```

Per-vessel trajectory simplification with Visvalingam-Whyatt (`vw`), Douglas-Peucker (`rdp`), or Time-Dependent Trajectory Reduction (`tdtr`). `--metrics` also writes SR, LLR, DTW, Frechet, and ASED per track.

### 7. Load

```bash
# SQLite
uv run noaa-integrator load --source-dir data/filtered \
    --start-year 2023 --end-year 2023 --start-month 1 --end-month 2 \
    --sqlite marine_cadastre.db

# PostgreSQL / TimescaleDB
export NOAA_PG_DSN='postgresql://user:password@localhost:5432/noaa'
uv run noaa-integrator load --source-dir data/filtered \
    --start-year 2023 --end-year 2023 --dsn --timescaledb
```

Decodes month batches through `aisdb.decode_msgs`. Failed batches are retried (default 3 attempts). Credentials come from `--dsn` or the `NOAA_PG_DSN` environment variable, never from code.

## Development

```bash
uv sync --all-extras
uv run pytest              # test suite
uv run ruff check .        # lint
uv run ruff format .       # format
uv run pyrefly check       # typecheck
```

Continuous integration runs linting, type checking, and the test suite on Ubuntu and macOS for every push and pull request.

## Documentation

[Docs](https://aisviz.gitbook.io/documentation/) · [Tutorials](https://aisviz.gitbook.io/tutorials/) · [API reference](https://aisviz.cs.dal.ca/AISdb/) · [Website](https://aisviz.cs.dal.ca/)

## Related projects

- [AISdb](https://github.com/MAPS-Lab/AISdb), the core Python/Rust platform for storing, querying, and analyzing AIS data
- [AISdb-lite](https://github.com/MAPS-Lab/AISdb-lite), a lightweight AISdb variant built on PostGIS and TimescaleDB hypertables
- [Tutorials](https://github.com/MAPS-Lab/AISdb-Tutorials), hands-on notebook companions to the GitBook tutorials

## License

This project is licensed under the GNU Affero General Public License v3.0. See [LICENSE](LICENSE) for the full text.
