"""Tests for CSV row deduplication."""

from pathlib import Path

import pytest

from noaa_integrator.dedup import dedupe_directory, dedupe_file


def test_dedupe_file_removes_duplicates_keeps_header(tmp_path: Path) -> None:
    target = tmp_path / "data.csv"
    target.write_text("MMSI,LAT\n123,44.5\n123,44.5\n456,45.0\n123,44.5\n")

    result = dedupe_file(target)

    assert result.rows_read == 4
    assert result.rows_written == 2
    assert result.duplicates_removed == 2
    assert target.read_text() == "MMSI,LAT\n123,44.5\n456,45.0\n"


def test_dedupe_file_empty_file(tmp_path: Path) -> None:
    target = tmp_path / "empty.csv"
    target.write_text("")

    result = dedupe_file(target)

    assert result.rows_read == 0
    assert result.rows_written == 0


def test_dedupe_file_no_temp_left_behind(tmp_path: Path) -> None:
    target = tmp_path / "data.csv"
    target.write_text("h\na\nb\n")

    dedupe_file(target)

    assert list(tmp_path.iterdir()) == [target]


def test_dedupe_directory(tmp_path: Path) -> None:
    (tmp_path / "one.csv").write_text("h\nx\nx\n")
    (tmp_path / "two.csv").write_text("h\ny\n")

    results = dedupe_directory(tmp_path, workers=1)

    assert len(results) == 2
    assert sum(result.duplicates_removed for result in results) == 1


def test_dedupe_directory_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        dedupe_directory(tmp_path / "nope")
