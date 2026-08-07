#!/usr/bin/env python3
"""Conservative cleanup for isolated dark lines created exactly at stitch seams."""

from __future__ import annotations

from types import ModuleType
from typing import Callable, Sequence

import cv2
import numpy as np

SEAM_SEARCH_RADIUS = 5
SEAM_DARK_DELTA = 14.0
SEAM_DARK_PIXEL_DELTA = 10.0
SEAM_DARK_PIXEL_FRACTION = 0.72
SEAM_EDGE_MARGIN_RATIO = 0.04


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


def _repair_one_seam(image: np.ndarray, expected_row: int) -> None:
    height, width = image.shape[:2]
    if height < 5 or width < 16:
        return

    margin = max(2, int(width * SEAM_EDGE_MARGIN_RATIO))
    left, right = margin, width - margin
    if right - left < 8:
        left, right = 0, width

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    start = max(2, int(expected_row) - SEAM_SEARCH_RADIUS)
    end = min(height - 2, int(expected_row) + SEAM_SEARCH_RADIUS + 1)
    if start >= end:
        return

    best: tuple[float, int] | None = None
    for row in range(start, end):
        center = gray[row, left:right].astype(np.float32)
        above = gray[row - 1, left:right].astype(np.float32)
        below = gray[row + 1, left:right].astype(np.float32)
        reference = (above + below) * 0.5

        mean_delta = float(np.mean(reference) - np.mean(center))
        if mean_delta < SEAM_DARK_DELTA:
            continue
        dark_fraction = float(np.mean((reference - center) >= SEAM_DARK_PIXEL_DELTA))
        if dark_fraction < SEAM_DARK_PIXEL_FRACTION:
            continue

        score = mean_delta * dark_fraction
        if best is None or score > best[0]:
            best = (score, row)

    if best is None:
        return

    row = best[1]
    repaired = (
        image[row - 1].astype(np.uint16) + image[row + 1].astype(np.uint16)
    ) // 2
    image[row] = repaired.astype(np.uint8)


def cleanup_stitch_seams(
    image: np.ndarray,
    matches: Sequence[object],
) -> np.ndarray:
    """Repair only strong one-row dark artifacts near known frame boundaries."""

    if not matches or image.ndim != 3 or image.shape[2] != 3:
        return image
    result = np.ascontiguousarray(image.copy())
    for row in _seam_rows(matches):
        _repair_one_seam(result, row)
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
        return cleanup_stitch_seams(stitched, matches)

    return stitch_frames
