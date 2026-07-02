"""Tests for archive filename parsing and {yyyymm} organization."""

from pathlib import Path

import pytest

from noaa_integrator.organize import organize_directory, parse_year_month


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("2025_ais_2025-01-15.csv.zst", ("2025", "01")),
        ("2024_AIS_2024_06_30.zip", ("2024", "06")),
        ("2014_Zone01_2014_12.zip", ("2014", "12")),
        ("2013_Zone10_2013_03.gdb.zip", ("2013", "03")),
        ("2009_Zone17_2009_07.zip", ("2009", "07")),
        ("random_file.zip", None),
        ("2024_AIS_2024_06_30.csv", None),
        ("AIS_2024_06_30.zip", None),
    ],
)
def test_parse_year_month(filename: str, expected: tuple[str, str] | None) -> None:
    assert parse_year_month(filename) == expected


def test_organize_directory_moves_all_formats(tmp_path: Path) -> None:
    names = [
        "2025_ais_2025-01-15.csv.zst",
        "2024_AIS_2024_06_30.zip",
        "2013_Zone10_2013_03.gdb.zip",
        "unmatched.zip",
    ]
    for name in names:
        (tmp_path / name).write_bytes(b"data")

    moved, skipped = organize_directory(tmp_path)

    assert {path.name for path in moved} == set(names) - {"unmatched.zip"}
    assert (tmp_path / "202501" / "2025_ais_2025-01-15.csv.zst").exists()
    assert (tmp_path / "202406" / "2024_AIS_2024_06_30.zip").exists()
    assert (tmp_path / "201303" / "2013_Zone10_2013_03.gdb.zip").exists()
    assert [path.name for path in skipped] == ["unmatched.zip"]
    assert (tmp_path / "unmatched.zip").exists()  # left in place


def test_organize_directory_missing_dir() -> None:
    with pytest.raises(FileNotFoundError):
        organize_directory(Path("/nonexistent/dir"))
