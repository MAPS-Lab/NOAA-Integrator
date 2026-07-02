"""Tests for trajectory simplification algorithms and track iteration."""

from pathlib import Path

import numpy as np

from noaa_integrator.simplify import (
    apply_mask,
    iter_tracks,
    td_tr,
    visvalingam_whyatt,
)

CSV_HEADER = (
    "MMSI,BaseDateTime,LAT,LON,SOG,COG,Heading,VesselName,IMO,CallSign,"
    "VesselType,Status,Length,Width,Draft,Cargo,TransceiverClass\n"
)


def _row(mmsi: int, ts: str, lat: float, lon: float) -> str:
    return f"{mmsi},{ts},{lat},{lon},10.0,90.0,90.0,TEST,IMO123,CS,70,0,100,20,5,70,A\n"


def test_visvalingam_whyatt_keeps_endpoints_drops_collinear() -> None:
    points = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0], [3.0, 1.0]])
    mask = visvalingam_whyatt(points, threshold=0.01)

    assert mask[0] and mask[-1]  # endpoints always kept
    assert not mask[1]  # collinear interior point dropped
    assert mask[3]


def test_visvalingam_whyatt_short_track_untouched() -> None:
    points = np.array([[0.0, 0.0], [1.0, 1.0]])
    assert visvalingam_whyatt(points, threshold=1.0).all()


def test_td_tr_drops_time_synchronized_point() -> None:
    # Point at t=1 lies exactly on the segment interpolated in time.
    points = np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]])
    times = np.array([0.0, 1.0, 2.0])
    mask = td_tr(points, times, threshold=0.1)

    assert mask[0] and mask[2]
    assert not mask[1]


def test_td_tr_keeps_deviating_point() -> None:
    points = np.array([[0.0, 0.0], [1.0, 5.0], [2.0, 0.0]])
    times = np.array([0.0, 1.0, 2.0])
    assert td_tr(points, times, threshold=0.1).all()


def test_apply_mask_projects_all_columns() -> None:
    track = {"LAT": [1.0, 2.0, 3.0], "LON": [4.0, 5.0, 6.0], "MMSI": [9, 9, 9]}
    mask = np.array([True, False, True])
    reduced = apply_mask(track, mask)

    assert reduced["LAT"] == [1.0, 3.0]
    assert reduced["LON"] == [4.0, 6.0]
    assert len(reduced["MMSI"]) == 2


def test_iter_tracks_groups_and_sorts(tmp_path: Path) -> None:
    csv_path = tmp_path / "merged.csv"
    csv_path.write_text(
        CSV_HEADER
        + _row(222, "2023-01-01T00:02:00", 44.2, -63.2)
        + _row(111, "2023-01-01T00:01:00", 44.1, -63.1)
        + _row(222, "2023-01-01T00:01:00", 44.0, -63.0)
        + _row(111, "2023-01-01T00:00:00", 44.0, -63.0)
    )

    tracks = dict(iter_tracks(csv_path, chunk_size=2))

    assert set(tracks) == {111, 222}
    assert len(tracks[111]["LAT"]) == 2
    # Sorted by time within each track
    assert tracks[222]["LAT"] == [44.0, 44.2]
    assert tracks[111]["BaseDateTime"][0] < tracks[111]["BaseDateTime"][1]


def test_iter_tracks_skips_bad_rows(tmp_path: Path) -> None:
    csv_path = tmp_path / "merged.csv"
    csv_path.write_text(
        CSV_HEADER + _row(111, "2023-01-01T00:00:00", 44.0, -63.0) + _row(111, "not-a-date", 44.1, -63.1)
    )

    tracks = dict(iter_tracks(csv_path))
    assert len(tracks[111]["LAT"]) == 1


def test_douglas_peucker_drops_collinear() -> None:
    from noaa_integrator.simplify import douglas_peucker

    points = np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]])
    mask = douglas_peucker(points, epsilon=0.5)
    assert mask[0] and mask[-1]
    assert not mask[1]


def test_douglas_peucker_keeps_deviating_point() -> None:
    from noaa_integrator.simplify import douglas_peucker

    points = np.array([[0.0, 0.0], [1.0, 2.0], [2.0, 0.0]])
    assert douglas_peucker(points, epsilon=0.5).all()


def test_douglas_peucker_edge_cases() -> None:
    from noaa_integrator.simplify import douglas_peucker

    assert douglas_peucker(np.empty((0, 2)), epsilon=0.5).tolist() == []
    two = douglas_peucker(np.array([[0.0, 0.0], [1.0, 1.0]]), epsilon=0.5)
    assert two.all()
    # Zero-length segment (identical endpoints) must not divide by zero
    dup = np.array([[0.0, 0.0], [3.0, 3.0], [0.0, 0.0]])
    mask = douglas_peucker(dup, epsilon=0.5)
    assert mask[0] and mask[2] and mask[1]
