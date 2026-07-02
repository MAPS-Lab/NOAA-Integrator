"""Tests for archive extraction (.zip and .csv.zst)."""

import zipfile
from pathlib import Path

import pytest
import zstandard

from noaa_integrator.extract import extract_tree, extract_zip, extract_zst


def _make_zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return path


def _make_zst(path: Path, data: bytes) -> Path:
    path.write_bytes(zstandard.ZstdCompressor().compress(data))
    return path


def test_extract_zip_roundtrip(tmp_path: Path) -> None:
    archive = _make_zip(tmp_path / "data.zip", {"a.csv": b"1,2\n", "b.csv": b"3,4\n"})
    extracted = extract_zip(archive, tmp_path / "out")

    assert sorted(path.name for path in extracted) == ["a.csv", "b.csv"]
    assert (tmp_path / "out" / "a.csv").read_bytes() == b"1,2\n"


def test_extract_zip_rejects_corrupted(tmp_path: Path) -> None:
    bogus = tmp_path / "corrupt.zip"
    bogus.write_bytes(b"this is not a zip file")

    with pytest.raises(zipfile.BadZipFile):
        extract_zip(bogus, tmp_path / "out")


def test_extract_zst_roundtrip(tmp_path: Path) -> None:
    source = _make_zst(tmp_path / "ais_2025-01-01.csv.zst", b"MMSI,LAT\n123,44.5\n")
    target = extract_zst(source, tmp_path / "out")

    assert target.name == "ais_2025-01-01.csv"
    assert target.read_bytes() == b"MMSI,LAT\n123,44.5\n"


def test_extract_tree_respects_range_and_reports_failures(tmp_path: Path) -> None:
    base = tmp_path / "archives"
    for year_month in ("202301", "202302", "202303"):
        (base / year_month).mkdir(parents=True)

    _make_zip(base / "202301" / "jan.zip", {"jan.csv": b"1\n"})
    _make_zip(base / "202302" / "feb.zip", {"feb.csv": b"2\n"})
    _make_zip(base / "202303" / "mar.zip", {"mar.csv": b"3\n"})
    (base / "202302" / "bad.zip").write_bytes(b"corrupted")
    _make_zst(base / "202302" / "2025_ais_2025-02-01.csv.zst", b"zst-data\n")

    dest = tmp_path / "out"
    report = extract_tree(base, dest, start="202301", end="202302")

    extracted_names = sorted(path.name for path in report.extracted)
    assert extracted_names == ["2025_ais_2025-02-01.csv", "feb.csv", "jan.csv"]
    assert not (dest / "202303").exists()  # out of range
    assert len(report.failed) == 1
    assert report.failed[0][0].name == "bad.zip"
