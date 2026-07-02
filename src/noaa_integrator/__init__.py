"""NOAA-Integrator: acquisition and processing of NOAA Marine Cadastre AIS data.

Pipeline stages (each is a CLI subcommand of ``noaa-integrator``):

1. ``download``  - fetch yearly AIS archives from coast.noaa.gov
2. ``organize``  - group downloaded archives into ``{year}{month}`` folders
3. ``extract``   - decompress archives (``.zip``, ``.csv.zst``, legacy ``.gdb.zip``)
4. ``filter``    - keep only records inside a geographic bounding box
5. ``dedup``     - drop duplicate rows from merged CSV files
6. ``simplify``  - trajectory simplification (Visvalingam-Whyatt, RDP, TD-TR)
7. ``load``      - decode into an AISdb-aligned SQLite or PostgreSQL database
"""

__version__ = "1.0.0"
