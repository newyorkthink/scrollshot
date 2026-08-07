#!/usr/bin/env python3
"""Conservative cleanup for short dark bands created exactly at stitch seams."""

from __future__ import annotations

from types import ModuleType
from typing import Callable, Sequence

import cv2
import numpy as np

SEAM_SEARCH_RADIUS = 7
SEAM_REFERENCE_RADIUS = 4
SEAM_MAX_BAND_HEIGHT = 7
SEAM_DARK_DELTA = 14.0
SEAM_DARK_PIXEL_DELTA = 10.0
SEAM_DARK_PIXEL_FRACTION = 0.72
SEAM_EDGE_MARGIN_RATIO = 0.04
SEAM_SOURCE_MIN_GAIN = 8.0
SEAM_SOURCE_BAND_SPREAD = 4


def _seam_rows(matches: Sequence[object]) -> list[int]:
    if not matches:
        return []
    bottoms = [int(match.content_bottom) for match in matches if int(match.content_bottom) > 0]
    if not bottoms:
        return []
    base = min(bottoms)
    rows: list[int] = []
    cumulative = 0
    for match in matches:
        rows.append(base + cumulative)
        cumulative += int(match.shift)
    return rows


def _candidate_groups(rows: Sequence[int]) -> list[list[int]]:
    groups: list[list[int]] = []
    for row in rows:
        if not groups or row != groups[-1][-1] + 1:
            groups.append([row])
        else:
            groups[-1].append(row)
    return groups


def _detect_seam_artifact(
    image: np.ndarray,
    expected_row: int,
) -> tuple[list[int], dict[int, np.ndarray], int, int] | None:
    height, width = image.shape[:2]
    if height < 7 or width < 16:
        return None

    margin = max(2, int(width * SEAM_EDGE_MARGIN_RATIO))
    left, right = margin, width - margin
    if right - left < 8:
        left, right = 0, width

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    start = max(1, int(expected_row) - SEAM_SEARCH_RADIUS)
    end = min(height - 1, int(expected_row) + SEAM_SEARCH_RADIUS + 1)
    if start >= end:
        return None

    reference_start = max(0, start - SEAM_REFERENCE_RADIUS)
    reference_end = min(height, end + SEAM_REFERENCE_RADIUS)
    reference_rows = gray[reference_start:reference_end, left:right]
    if reference_rows.shape[0] < 3:
        return None

    reference = np.percentile(
        reference_rows.astype(np.float32),
        75,
        axis=0,
    )

    candidates: list[int] = []
    scores: dict[int, float] = {}
    masks: dict[int, np.ndarray] = {}
    for row in range(start, end):
        center = gray[row, left:right].astype(np.float32)
        delta = reference - center
        mean_delta = float(np.mean(delta))
        if mean_delta < SEAM_DARK_DELTA:
            continue
        mask = delta >= SEAM_DARK_PIXEL_DELTA
        dark_fraction = float(np.mean(mask))
        if dark_fraction < SEAM_DARK_PIXEL_FRACTION:
            continue
        candidates.append(row)
        scores[row] = mean_delta * dark_fraction
        masks[row] = mask

    groups = [
        group
        for group in _candidate_groups(candidates)
        if len(group) <= SEAM_MAX_BAND_HEIGHT
    ]
    if not groups:
        return None

    group = max(
        groups,
        key=lambda item: (
            sum(scores[row] for row in item),
            -min(abs(row - int(expected_row)) for row in item),
        ),
    )
    return group, {row: masks[row] for row in group}, left, right


def _source_row_for_seam(
    frames: Sequence[np.ndarray],
    matches: Sequence[object],
    seam_index: int,
    base_bottom: int,
    offset: int,
) -> np.ndarray | None:
    """Return another frame containing the same content row away from this seam."""

    if len(frames) != len(matches) + 1:
        return None
    if seam_index < 0 or seam_index >= len(matches):
        return None

    current_shift = int(matches[seam_index].shift)
    if offset < 0:
        source_index = seam_index + 1
        source_row = base_bottom + offset - current_shift
    else:
        source_index = seam_index + 2
        if source_index >= len(frames):
            return None
        next_shift = int(matches[seam_index + 1].shift)
        source_row = base_bottom - current_shift + offset - next_shift

    frame = frames[source_index]
    if source_row < 0 or source_row >= frame.shape[0]:
        return None
    return frame[source_row]


def _edge_artifact_mask(
    image: np.ndarray,
    row: int,
    *,
    start: int,
    end: int,
    search_start: int,
    search_end: int,
) -> np.ndarray:
    """Extend a confirmed seam repair into edge columns only where they are also anomalously dark."""

    if end <= start:
        return np.zeros(0, dtype=bool)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    reference_rows = gray[search_start:search_end, start:end]
    if reference_rows.shape[0] < 3:
        return np.zeros(end - start, dtype=bool)
    reference = np.percentile(reference_rows.astype(np.float32), 75, axis=0)
    current = gray[row, start:end].astype(np.float32)
    return (reference - current) >= SEAM_DARK_PIXEL_DELTA


def _repair_one_seam(
    image: np.ndarray,
    expected_row: int,
    *,
    frames: Sequence[np.ndarray] | None = None,
    matches: Sequence[object] | None = None,
    seam_index: int | None = None,
    base_bottom: int | None = None,
) -> None:
    artifact = _detect_seam_artifact(image, expected_row)
    if artifact is None:
        return

    rows, masks, left, right = artifact
    top, bottom = rows[0], rows[-1]
    if top <= 0 or bottom >= image.shape[0] - 1:
        return

    height, width = image.shape[:2]
    search_start = max(0, int(expected_row) - SEAM_SEARCH_RADIUS - SEAM_REFERENCE_RADIUS)
    search_end = min(
        height,
        int(expected_row) + SEAM_SEARCH_RADIUS + SEAM_REFERENCE_RADIUS + 1,
    )

    source_enabled = False
    if (
        frames is not None
        and matches is not None
        and seam_index is not None
        and base_bottom is not None
        and len(frames) == len(matches) + 1
    ):
        bottoms = [int(match.content_bottom) for match in matches]
        source_enabled = (
            bool(bottoms)
            and max(bottoms) - min(bottoms) <= SEAM_SOURCE_BAND_SPREAD
            and all(frame.shape == frames[0].shape for frame in frames)
        )

    before = image[top - 1].astype(np.float32)
    after = image[bottom + 1].astype(np.float32)
    span = bottom - top + 2

    for index, row in enumerate(rows, start=1):
        mask = np.zeros(width, dtype=bool)
        mask[left:right] = masks[row]
        if left:
            mask[:left] = _edge_artifact_mask(
                image,
                row,
                start=0,
                end=left,
                search_start=search_start,
                search_end=search_end,
            )
        if right < width:
            mask[right:] = _edge_artifact_mask(
                image,
                row,
                start=right,
                end=width,
                search_start=search_start,
                search_end=search_end,
            )

        current = image[row]
        replacement: np.ndarray | None = None

        if source_enabled:
            source = _source_row_for_seam(
                frames,
                matches,
                seam_index,
                base_bottom,
                row - int(expected_row),
            )
            if source is not None and source.shape == image[row].shape:
                source_center = source[left:right]
                source_gain = float(
                    np.mean(source_center.astype(np.float32))
                    - np.mean(current[left:right].astype(np.float32))
                )
                if source_gain >= SEAM_SOURCE_MIN_GAIN:
                    replacement = source

        if replacement is None:
            alpha = index / span
            blended = before * (1.0 - alpha) + after * alpha
            replacement = np.clip(
                np.rint(blended),
                0,
                255,
            ).astype(np.uint8)

        repaired = current.copy()
        repaired[mask] = replacement[mask]
        image[row] = repaired


def cleanup_stitch_seams(
    image: np.ndarray,
    matches: Sequence[object],
    *,
    frames: Sequence[np.ndarray] | None = None,
) -> np.ndarray:
    """Repair only short, broad dark artifacts near known frame boundaries."""

    if not matches or image.ndim != 3 or image.shape[2] != 3:
        return image

    result = np.ascontiguousarray(image.copy())
    seam_rows = _seam_rows(matches)
    bottoms = [int(match.content_bottom) for match in matches if int(match.content_bottom) > 0]
    base_bottom = min(bottoms) if bottoms else None

    for seam_index, row in enumerate(seam_rows):
        _repair_one_seam(
            result,
            row,
            frames=frames,
            matches=matches,
            seam_index=seam_index,
            base_bottom=base_bottom,
        )
    return result


def create_seam_cleaning_stitcher(
    core: ModuleType,
    baseline_stitcher: Callable[..., np.ndarray],
) -> Callable[..., np.ndarray]:
    """Wrap the stable stitcher without changing normal content away from seams."""

    def stitch_frames(
        frames: Sequence[np.ndarray],
        shifts: Sequence[object],
    ) -> np.ndarray:
        stitched = baseline_stitcher(frames, shifts)
        matches = (
            list(shifts)
            if shifts and all(isinstance(item, core.ShiftMatch) for item in shifts)
            else []
        )
        if not matches:
            return stitched
        return cleanup_stitch_seams(
            stitched,
            matches,
            frames=frames,
        )

    return stitch_frames
