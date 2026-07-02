"""Tests for the geographic bounding-box filter."""

from pathlib import Path

import pytest

from noaa_integrator.bbox import BBox, filter_csv, filter_files

# Nova Scotia-ish box
BOX = BBox(min_lon=-70.0, min_lat=40.0, max_lon=-55.0, max_lat=50.0)

CSV_HEADER = "MMSI,BaseDateTime,LAT,LON,SOG\n"


def _write_csv(path: Path, rows: list[str]) -> Path:
    path.write_text(CSV_HEADER + "".join(rows))
    return path


def test_bbox_validate_rejects_bad_ranges() -> None:
    with pytest.raises(ValueError):
        BBox(10.0, 0.0, -10.0, 1.0).validate()  # min_lon > max_lon
    with pytest.raises(ValueError):
        BBox(0.0, 95.0, 1.0, 99.0).validate()  # latitude out of domain


def test_filter_csv_keeps_only_rows_inside(tmp_path: Path) -> None:
    source = _write_csv(
        tmp_path / "input.csv",
        [
            "111000111,2023-01-01T00:00:00,44.5,-63.5,10.0\n",  # inside (Halifax)
            "222000222,2023-01-01T00:00:00,25.0,-80.0,9.0\n",  # outside (Miami)
            "333000333,2023-01-01T00:00:00,45.0,-60.0,8.0\n",  # inside
        ],
    )
    result = filter_csv(source, BOX, tmp_path / "out" / "filtered.csv")

    assert result.rows_processed == 3
    assert result.rows_kept == 2
    assert result.output is not None
    lines = result.output.read_text().strip().splitlines()
    assert len(lines) == 3  # header + 2 rows
    assert "222000222" not in result.output.read_text()


def test_filter_csv_skips_malformed_coordinates(tmp_path: Path) -> None:
    source = _write_csv(
        tmp_path / "input.csv",
        [
            "111000111,2023-01-01T00:00:00,44.5,-63.5,10.0\n",
            "444000444,2023-01-01T00:00:00,not-a-lat,-63.5,10.0\n",
            "555000555,2023-01-01T00:00:00,44.5,,10.0\n",
        ],
    )
    result = filter_csv(source, BOX, tmp_path / "filtered.csv")

    assert result.rows_kept == 1
    assert result.rows_skipped == 2


def test_filter_csv_removes_empty_output(tmp_path: Path) -> None:
    source = _write_csv(
        tmp_path / "input.csv",
        ["222000222,2023-01-01T00:00:00,25.0,-80.0,9.0\n"],
    )
    result = filter_csv(source, BOX, tmp_path / "filtered.csv")

    assert result.rows_kept == 0
    assert result.output is None
    assert not (tmp_path / "filtered.csv").exists()


def test_filter_files_continues_after_error(tmp_path: Path) -> None:
    good = _write_csv(tmp_path / "good.csv", ["111000111,2023-01-01T00:00:00,44.5,-63.5,10.0\n"])
    missing = tmp_path / "missing.csv"

    results = filter_files([missing, good], BOX, tmp_path / "out")

    assert results[0].output is None
    assert results[1].output is not None
