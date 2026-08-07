#!/usr/bin/env python3
"""Resilient stitching fallback for browser-like dynamic scrolling layouts."""

from __future__ import annotations

from statistics import median
from types import ModuleType
from typing import Callable, Sequence

import numpy as np


def _select_consensus_band(
    frames: Sequence[np.ndarray],
    matches: Sequence[object],
) -> tuple[int, int]:
    """Choose a stable common moving band while tolerating one noisy detector result."""

    height = int(frames[0].shape[0])
    tops = [max(0, min(height - 1, int(match.content_top))) for match in matches]
    bottoms = [max(1, min(height, int(match.content_bottom))) for match in matches]
    maximum_shift = max(int(match.shift) for match in matches)

    candidates = [
        (int(round(median(tops))), int(round(median(bottoms)))),
        (min(tops), max(bottoms)),
        (0, height),
    ]
    for top, bottom in candidates:
        top = max(0, min(height - 1, top))
        bottom = max(top + 1, min(height, bottom))
        if bottom - top > maximum_shift + 24:
            return top, bottom

    return 0, height


def _stitch_with_common_band(
    frames: Sequence[np.ndarray],
    matches: Sequence[object],
    top: int,
    bottom: int,
) -> np.ndarray:
    """Stitch with one consensus band so fixed browser chrome is not repeated."""

    pieces: list[np.ndarray] = [frames[0][:bottom]]
    band_height = bottom - top

    for frame, match in zip(frames[1:], matches):
        shift = int(match.shift)
        if shift <= 0 or shift >= band_height:
            raise ValueError("consensus band cannot contain detected shift")
        pieces.append(frame[bottom - shift : bottom])

    pieces.append(frames[-1][bottom:])
    non_empty = [piece for piece in pieces if piece.size]
    return np.ascontiguousarray(np.concatenate(non_empty, axis=0))


def create_resilient_stitcher(
    core: ModuleType,
    baseline_stitcher: Callable[..., np.ndarray],
) -> Callable[..., np.ndarray]:
    """Preserve the stable stitcher and recover from inconsistent motion-band metadata."""

    recoverable_messages = {
        "detected scrolling content band is too small",
        "invalid shift",
    }

    def stitch_frames(
        frames: Sequence[np.ndarray],
        shifts: Sequence[object],
    ) -> np.ndarray:
        try:
            return baseline_stitcher(frames, shifts)
        except ValueError as exc:
            if str(exc) not in recoverable_messages:
                raise

        if not frames or len(shifts) != len(frames) - 1:
            raise ValueError("frame and shift counts do not match")

        height, width = frames[0].shape[:2]
        if any(frame.shape[:2] != (height, width) for frame in frames):
            raise ValueError("all frames must have the same dimensions")

        matches = list(shifts)
        if not matches or not all(isinstance(item, core.ShiftMatch) for item in matches):
            return baseline_stitcher(frames, shifts)

        top, bottom = _select_consensus_band(frames, matches)
        try:
            return _stitch_with_common_band(frames, matches, top, bottom)
        except ValueError:
            raw_shifts = [int(match.shift) for match in matches]
            return baseline_stitcher(frames, raw_shifts)

    return stitch_frames
