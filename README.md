# NOAA-Integrator

NOAA-Integrator acquires and processes AIS data from [NOAA Marine Cadastre](https://hub.marinecadastre.gov/pages/vesseltraffic) and loads it into an [AISdb](https://github.com/MAPS-Lab/AISdb)-aligned database (SQLite or PostgreSQL/TimescaleDB). It is a uv-managed Python tool with a pure-Python core that consumes the NOAA archive at `https://coast.noaa.gov/htdata/CMSP/AISDataHandler/{year}/` and supports every published format, including daily ZIP archives (2015-2024), zone archives (2009-2014), legacy geodatabases (`.gdb.zip`, 2011-2013), and Zstandard-compressed CSV (`.csv.zst`, 2025 onward). NOAA-Integrator is developed and maintained by the [MAPS Lab](https://mapslab.tech/) at Dalhousie University, continuing work that began under the [MERIDIAN](https://meridian.cs.dal.ca) initiative.

## Features

- Downloads every archive NOAA publishes for a year range, resume-friendly by default
- Organizes archives into `{year}{month}` folders across all NOAA naming schemes since 2009
- Extracts `.zip` (with integrity check) and `.csv.zst`, and converts legacy `.gdb.zip` geodatabases
- Filters records to a WGS84 bounding box, skipping and counting malformed rows
- Deduplicates rows in place with atomic replacement
- Simplifies per-vessel trajectories (Visvalingam-Whyatt, Douglas-Peucker, TD-TR) with optional quality metrics
- Loads month batches into SQLite or PostgreSQL/TimescaleDB through `aisdb.decode_msgs`, with retries

The pipeline runs as one console command, `noaa-integrator`, with a subcommand per stage. Every stage is independent, so you can run only the ones you need. Optional extras add database loading, legacy geodatabase conversion, and trajectory simplification without weighing down the core.

## Installation

NOAA-Integrator uses [uv](https://docs.astral.sh/uv/) for environment and dependency management. The core install covers download, organize, extract, filter, and dedup; optional extras add the heavier stages.

```bash
uv sync                      # core pipeline (download, organize, extract, filter, dedup)
uv sync --extra load         # + aisdb for database loading
uv sync --extra gdb          # + geopandas/fiona for legacy .gdb.zip conversion
uv sync --extra simplify     # + fastdtw/similaritymeasures/scipy for trajectory simplification
uv sync --all-extras         # everything at once
```

Without uv, install from a clone with pip (Python 3.10-3.12).

```bash
pip install .                # core pipeline
pip install ".[load]"        # with a chosen extra (load, gdb, simplify)
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

Scrapes the NOAA index per year and streams every archive. Existing non-empty files are skipped (resume-friendly); force a re-download with `--no-skip-existing`.

### 2. Organize

```bash
uv run noaa-integrator organize --base-dir data/downloads
```

Groups archives into `{year}{month}` folders (for example `202406/`), matching every NOAA naming scheme from 2009 to 2025 and beyond.

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

Removes duplicate rows in place (header preserved, atomic replace).

### 6. Simplify (optional)

```bash
uv run noaa-integrator simplify data/merged/*.csv --dest data/simplified --algorithm vw --metrics
```

Per-vessel trajectory simplification with Visvalingam-Whyatt (`vw`), Douglas-Peucker (`rdp`), or Time-Dependent Trajectory Reduction (`tdtr`). Adding `--metrics` also writes SR, LLR, DTW, Frechet, and ASED per track.

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

Decodes month batches through `aisdb.decode_msgs`. Failed batches are retried (three attempts by default). Credentials come from `--dsn` or the `NOAA_PG_DSN` environment variable, never from code.

## Development

```bash
uv sync --all-extras
uv run pytest              # test suite
uv run ruff check .        # lint
uv run ruff format .       # format
uv run pyrefly check       # typecheck
```

Continuous integration runs linting, type checking, and the test suite on Ubuntu and macOS against Python 3.10 and 3.12 for every push to `main` and every pull request.

## Documentation

[Docs](https://aisviz.gitbook.io/documentation/) · [Tutorials](https://aisviz.gitbook.io/tutorials/) · [API reference](https://maps-lab.github.io/AISdb/) · [Website](https://aisviz.cs.dal.ca/)

## Related projects

- [AISdb](https://github.com/MAPS-Lab/AISdb), the core Python/Rust platform for storing, querying, and analyzing AIS data
- [AISdb-lite](https://github.com/MAPS-Lab/AISdb-lite), a lightweight AISdb variant built on PostGIS and TimescaleDB hypertables
- [Tutorials](https://github.com/MAPS-Lab/AISdb-Tutorials), hands-on notebook companions to the GitBook tutorials

## Citation

If you use NOAA-Integrator in your work, please cite it. Citation metadata lives in [CITATION.cff](CITATION.cff), and the BibTeX entry follows.

```bibtex
@software{NOAAIntegrator2026:GSpadon,
  author    = {Spadon, Gabriel},
  title     = {NOAA-Integrator},
  year      = {2026},
  version   = {1.0.0},
  publisher = {MAPS Lab, Dalhousie University},
  url       = {https://github.com/MAPS-Lab/NOAA-Integrator},
  license   = {AGPL-3.0}
}
```

## License

This project is distributed under the terms of the GNU Affero General Public License v3.0 (AGPL-3.0). See [LICENSE](LICENSE) for details.
