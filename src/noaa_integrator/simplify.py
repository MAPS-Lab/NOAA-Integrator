"""Stage 5 (optional): trajectory simplification and quality metrics.

Algorithms (all pure numpy): Visvalingam-Whyatt, Douglas-Peucker, and
Time-Dependent Trajectory Reduction (TD-TR). Evaluation metrics (DTW,
Frechet) need the ``simplify`` extra: ``uv sync --extra simplify``.
"""

from __future__ import annotations

import csv
import heapq
import logging
import tempfile
from collections import defaultdict
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_DATETIME_FORMATS = ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S")

Track = dict[str, list[Any]]

_TRACK_COLUMNS = (
    "MMSI",
    "BaseDateTime",
    "LAT",
    "LON",
    "SOG",
    "COG",
    "Heading",
    "VesselName",
    "IMO",
    "CallSign",
    "VesselType",
    "Status",
    "Length",
    "Width",
    "Draft",
    "Cargo",
    "TransceiverClass",
)
_FLOAT_COLUMNS = frozenset({"LAT", "LON", "SOG", "COG", "Heading"})


def _parse_datetime(value: str) -> datetime:
    """Parse a Marine Cadastre timestamp (ISO 'T' or space separator)."""
    for fmt in _DATETIME_FORMATS:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"Unrecognized timestamp: {value!r}")


def iter_tracks(file_path: Path, chunk_size: int = 5_000_000) -> Iterator[tuple[int, Track]]:
    """Yield ``(mmsi, track)`` from a large CSV, sorted by (MMSI, time).

    External merge sort: the file is read in chunks, each chunk sorted and
    spilled to a temporary file, then all runs are heap-merged.
    """
    with tempfile.TemporaryDirectory(prefix="noaa-simplify-") as tmp:
        tmp_dir = Path(tmp)
        run_files: list[Path] = []

        with file_path.open("r", errors="replace") as csvfile:
            reader = csv.DictReader(csvfile)
            fieldnames = reader.fieldnames or []
            chunk: list[dict[str, str]] = []

            def spill(rows: list[dict[str, str]]) -> None:
                rows.sort(key=lambda row: (row["MMSI"], row["BaseDateTime"]))
                run_path = tmp_dir / f"run_{len(run_files)}.csv"
                with run_path.open("w", newline="") as run_csv:
                    writer = csv.DictWriter(run_csv, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
                run_files.append(run_path)

            for row in reader:
                try:
                    # Normalize timestamps so run files sort consistently.
                    row["BaseDateTime"] = _parse_datetime(row["BaseDateTime"]).isoformat(sep=" ")
                except ValueError as error:
                    logger.debug("Skipping row with bad timestamp: %s", error)
                    continue
                chunk.append(row)
                if len(chunk) >= chunk_size:
                    spill(chunk)
                    chunk = []
            if chunk:
                spill(chunk)

        handles = [run.open("r") for run in run_files]
        try:
            readers = [csv.DictReader(handle) for handle in handles]
            merged = heapq.merge(*readers, key=lambda row: (row["MMSI"], row["BaseDateTime"]))

            current_mmsi: int | None = None
            current_track: Track = defaultdict(list)
            for row in merged:
                try:
                    mmsi = int(row["MMSI"])
                except ValueError:
                    logger.debug("Skipping row with invalid MMSI: %r", row.get("MMSI"))
                    continue

                if mmsi != current_mmsi:
                    if current_mmsi is not None:
                        yield current_mmsi, current_track
                    current_mmsi = mmsi
                    current_track = defaultdict(list)

                for column in _TRACK_COLUMNS:
                    value: Any = row.get(column, "")
                    if column == "BaseDateTime":
                        value = _parse_datetime(value).timestamp()
                    elif column == "MMSI":
                        value = mmsi
                    elif column in _FLOAT_COLUMNS:
                        try:
                            value = float(value)
                        except ValueError:
                            value = float("nan")
                    current_track[column].append(value)

            if current_mmsi is not None:
                yield current_mmsi, current_track
        finally:
            for handle in handles:
                handle.close()


def _triangle_area(p1: np.ndarray, p2: np.ndarray, p3: np.ndarray) -> float:
    """Twice-signed triangle area magnitude, halved."""
    return abs((p2[0] - p1[0]) * (p3[1] - p1[1]) - (p3[0] - p1[0]) * (p2[1] - p1[1])) / 2


def visvalingam_whyatt(points: np.ndarray, threshold: float) -> np.ndarray:
    """Visvalingam-Whyatt simplification. Returns a keep-mask over points."""
    if len(points) < 3:
        return np.ones(len(points), dtype=bool)

    areas = np.zeros(len(points))
    for i in range(1, len(points) - 1):
        areas[i] = _triangle_area(points[i - 1], points[i], points[i + 1])
    areas[0] = areas[-1] = float("inf")

    mask = np.ones(len(points), dtype=bool)
    while True:
        min_idx = int(areas.argmin())
        if areas[min_idx] > threshold:
            break
        mask[min_idx] = False
        areas[min_idx] = float("inf")

        kept = np.flatnonzero(mask)
        position = int(np.searchsorted(kept, min_idx))
        # Recompute areas of the two surviving neighbours.
        for neighbour_pos in (position - 1, position):
            if 0 < neighbour_pos < len(kept) - 1:
                idx = kept[neighbour_pos]
                areas[idx] = _triangle_area(
                    points[kept[neighbour_pos - 1]], points[idx], points[kept[neighbour_pos + 1]]
                )

    return mask


def _perpendicular_distances(points: np.ndarray, start: np.ndarray, end: np.ndarray) -> np.ndarray:
    """Perpendicular distance of each point to the segment ``start -> end``."""
    segment = end - start
    length = float(np.hypot(*segment))
    if length == 0.0:
        return np.hypot(*(points - start).T)
    # 2D cross-product magnitude / segment length
    return np.abs(segment[0] * (start[1] - points[:, 1]) - segment[1] * (start[0] - points[:, 0])) / length


def douglas_peucker(points: np.ndarray, epsilon: float) -> np.ndarray:
    """Douglas-Peucker simplification (pure numpy). Returns a keep-mask.

    Implemented in-house: the ``rdp`` package relies on 2D ``np.cross``,
    which was removed in numpy 2.0.
    """
    mask = np.zeros(len(points), dtype=bool)
    if len(points) == 0:
        return mask
    mask[0] = mask[-1] = True
    if len(points) < 3:
        return mask

    stack: list[tuple[int, int]] = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        if last - first < 2:
            continue
        interior = points[first + 1 : last]
        distances = _perpendicular_distances(interior, points[first], points[last])
        farthest = int(distances.argmax())
        if distances[farthest] > epsilon:
            split = first + 1 + farthest
            mask[split] = True
            stack.append((first, split))
            stack.append((split, last))

    return mask


def td_tr(points: np.ndarray, times: np.ndarray, threshold: float) -> np.ndarray:
    """Time-Dependent Trajectory Reduction. Returns a keep-mask.

    Each interior point is compared against its time-synchronized position on
    the segment joining its neighbours; points closer than ``threshold``
    degrees are dropped.
    """
    if len(points) < 3:
        return np.ones(len(points), dtype=bool)

    mask = np.ones(len(points), dtype=bool)
    for i in range(1, len(points) - 1):
        t_start, t_end, t_i = float(times[i - 1]), float(times[i + 1]), float(times[i])
        if t_end == t_start:
            continue
        ratio = (t_i - t_start) / (t_end - t_start)
        x_sync = points[i - 1][0] + (points[i + 1][0] - points[i - 1][0]) * ratio
        y_sync = points[i - 1][1] + (points[i + 1][1] - points[i - 1][1]) * ratio
        distance = float(np.hypot(points[i][0] - x_sync, points[i][1] - y_sync))
        if distance < threshold:
            mask[i] = False
    return mask


def evaluate(track_origin: Track, track_simple: Track) -> dict[str, Any]:
    """Similarity metrics between original and simplified track.

    SR (simplification rate) and LLR (length-loss rate) are numpy-only;
    DTW and Frechet need the ``simplify`` extra.
    """
    try:
        from fastdtw import fastdtw
        from scipy.spatial.distance import euclidean
        from similaritymeasures import frechet_dist
    except ImportError as error:
        raise ImportError("Evaluation metrics need the 'simplify' extra: uv sync --extra simplify") from error

    origin = np.column_stack((track_origin["BaseDateTime"], track_origin["LON"], track_origin["LAT"]))
    simple = np.column_stack((track_simple["BaseDateTime"], track_simple["LON"], track_simple["LAT"]))

    def path_length(points: np.ndarray) -> float:
        return float(np.sum(np.linalg.norm(np.diff(points[:, 1:], axis=0), axis=1)))

    length_origin = path_length(origin)
    length_simple = path_length(simple)

    dtw_distance, _ = fastdtw(origin[:, 1:], simple[:, 1:], dist=euclidean)

    ased = 0.0
    for i in range(1, len(origin) - 1):
        t_start, x_start, y_start = origin[i - 1]
        t_end, x_end, y_end = origin[i + 1]
        t_i, x_i, y_i = origin[i]
        if t_end == t_start:
            continue
        ratio = (float(t_i) - float(t_start)) / (float(t_end) - float(t_start))
        x_sync = x_start + (x_end - x_start) * ratio
        y_sync = y_start + (y_end - y_start) * ratio
        ased += float(np.hypot(x_i - x_sync, y_i - y_sync))

    return {
        "SR": (len(origin) - len(simple)) / len(origin),
        "LLR": (length_origin - length_simple) / length_origin if length_origin else 0.0,
        "DTW": dtw_distance,
        "Frechet": frechet_dist(origin[:, 1:], simple[:, 1:]),
        "ASED": ased / len(origin),
        "mmsi": track_origin["MMSI"][0],
        "length_origin": length_origin,
        "point_origin": len(track_origin["BaseDateTime"]),
        "ship_type": track_origin["VesselType"][0],
    }


def apply_mask(track: Track, mask: np.ndarray) -> Track:
    """Project a keep-mask over every column of a track."""
    return {key: list(np.asarray(values, dtype=object)[mask]) for key, values in track.items()}


def write_track(track: Track, save_path: Path, first_write: bool) -> None:
    """Append one track to a CSV file (header written on first call)."""
    with save_path.open("a" if not first_write else "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(track.keys()))
        if first_write:
            writer.writeheader()
        for row in zip(*track.values(), strict=True):
            writer.writerow(dict(zip(track.keys(), row, strict=True)))


def write_metrics(metrics: dict[str, Any], save_path: Path, first_write: bool) -> None:
    """Append one metrics row to a CSV file (header written on first call)."""
    with save_path.open("a" if not first_write else "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(metrics.keys()))
        if first_write:
            writer.writeheader()
        writer.writerow(metrics)


def simplify_file(
    file_path: Path,
    output_dir: Path,
    algorithm: str = "vw",
    threshold: float = 1e-6,
    with_metrics: bool = False,
) -> tuple[Path, Path | None]:
    """Simplify every track of one merged CSV file.

    ``algorithm`` is one of ``vw``, ``rdp``, ``tdtr``. Returns the paths of
    the simplified CSV and (optionally) the metrics CSV.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{algorithm}_{file_path.name}"
    metrics_path = output_dir / f"eval_{algorithm}_{file_path.name}" if with_metrics else None

    first_write = True
    for _, track in iter_tracks(file_path):
        points = np.column_stack((track["LON"], track["LAT"]))
        if algorithm == "vw":
            mask = visvalingam_whyatt(points, threshold=threshold)
        elif algorithm == "rdp":
            mask = douglas_peucker(points, epsilon=threshold)
        elif algorithm == "tdtr":
            mask = td_tr(points, np.asarray(track["BaseDateTime"]), threshold=threshold)
        else:
            raise ValueError(f"Unknown algorithm: {algorithm!r} (expected vw, rdp, or tdtr)")

        simplified = apply_mask(track, mask)
        write_track(simplified, out_path, first_write)
        if metrics_path is not None:
            write_metrics(evaluate(track, simplified), metrics_path, first_write)
        first_write = False

    return out_path, metrics_path
