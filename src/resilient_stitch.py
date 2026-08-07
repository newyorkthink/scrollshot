#!/usr/bin/env python3
"""Resilient stitching for browser-like dynamic scrolling layouts."""

from __future__ import annotations

from statistics import median
from types import ModuleType
from typing import Callable, Sequence

import numpy as np

STATIC_SIDE_BLOCK = 12
STATIC_SIDE_MAX_FRACTION = 0.35
STATIC_SAME_MAX_ERROR = 2.5
STATIC_EVIDENCE_MARGIN = 1.5
STATIC_NEUTRAL_MAX_ERROR = 0.4


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
        (max(tops), min(bottoms)),
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


def _detect_static_side_bands(
    frames: Sequence[np.ndarray],
    matches: Sequence[object],
    top: int,
    bottom: int,
) -> tuple[int, int]:
    """Detect fixed left/right columns without treating the scrolling center as fixed."""

    if len(frames) < 2 or not matches:
        return 0, 0

    height, width = frames[0].shape[:2]
    if width < STATIC_SIDE_BLOCK * 4 or bottom - top < 48:
        return 0, 0

    same_profiles: list[np.ndarray] = []
    aligned_profiles: list[np.ndarray] = []
    for previous, current, match in zip(frames, frames[1:], matches):
        shift = int(match.shift)
        compare_end = min(bottom, height - shift)
        if shift <= 0 or compare_end - top < 48:
            continue

        previous_static = previous[top:compare_end].astype(np.int16, copy=False)
        current_aligned = current[top:compare_end].astype(np.int16, copy=False)
        previous_aligned = previous[top + shift : compare_end + shift].astype(
            np.int16,
            copy=False,
        )
        if (
            previous_static.shape != current_aligned.shape
            or previous_aligned.shape != current_aligned.shape
        ):
            continue

        same_profiles.append(
            np.mean(np.abs(previous_static - current_aligned), axis=(0, 2))
        )
        aligned_profiles.append(
            np.mean(np.abs(previous_aligned - current_aligned), axis=(0, 2))
        )

    if not same_profiles:
        return 0, 0

    same_error = np.median(np.stack(same_profiles, axis=0), axis=0)
    aligned_error = np.median(np.stack(aligned_profiles, axis=0), axis=0)

    flags: list[bool] = []
    for start in range(0, width, STATIC_SIDE_BLOCK):
        end = min(width, start + STATIC_SIDE_BLOCK)
        block_same = float(np.mean(same_error[start:end]))
        block_aligned = float(np.mean(aligned_error[start:end]))
        flags.append(
            block_same <= STATIC_SAME_MAX_ERROR
            and (
                block_aligned - block_same >= STATIC_EVIDENCE_MARGIN
                or block_same <= STATIC_NEUTRAL_MAX_ERROR
            )
        )

    maximum_blocks = max(
        1,
        int(np.ceil(width * STATIC_SIDE_MAX_FRACTION / STATIC_SIDE_BLOCK)),
    )

    def edge_width(edge_flags: Sequence[bool]) -> int:
        last_static = -1
        dynamic_run = 0
        for index, is_static in enumerate(edge_flags[:maximum_blocks]):
            if is_static:
                last_static = index
                dynamic_run = 0
                continue
            if last_static < 0:
                return 0
            dynamic_run += 1
            if dynamic_run >= 2:
                break
        if last_static < 0:
            return 0
        return min(width, (last_static + 1) * STATIC_SIDE_BLOCK)

    left = edge_width(flags)
    right = edge_width(list(reversed(flags)))
    if left + right >= width:
        return 0, 0
    return left, right


def _side_background_profile(
    frame: np.ndarray,
    top: int,
    bottom: int,
    start: int,
    end: int,
) -> np.ndarray:
    """Build a text-free vertical extension profile for one fixed side band."""

    region = frame[top:bottom, start:end]
    if region.size == 0:
        return np.empty((0, frame.shape[2]), dtype=frame.dtype)
    profile = np.median(region, axis=0)
    return np.rint(profile).astype(frame.dtype)


def _mask_static_sides(
    piece: np.ndarray,
    *,
    left: int,
    right: int,
    left_profile: np.ndarray,
    right_profile: np.ndarray,
) -> np.ndarray:
    if not left and not right:
        return piece

    result = piece.copy()
    if left:
        result[:, :left] = left_profile[np.newaxis, :, :]
    if right:
        result[:, -right:] = right_profile[np.newaxis, :, :]
    return result


def _stitch_with_common_band(
    frames: Sequence[np.ndarray],
    matches: Sequence[object],
    top: int,
    bottom: int,
    *,
    static_left: int = 0,
    static_right: int = 0,
) -> np.ndarray:
    """Stitch one moving band and avoid repeating fixed browser side columns."""

    pieces: list[np.ndarray] = [frames[0][:bottom]]
    band_height = bottom - top

    left_profile = _side_background_profile(
        frames[0],
        top,
        bottom,
        0,
        static_left,
    )
    right_profile = _side_background_profile(
        frames[0],
        top,
        bottom,
        frames[0].shape[1] - static_right,
        frames[0].shape[1],
    )

    for frame, match in zip(frames[1:], matches):
        shift = int(match.shift)
        if shift <= 0 or shift >= band_height:
            raise ValueError("consensus band cannot contain detected shift")
        piece = frame[bottom - shift : bottom]
        piece = _mask_static_sides(
            piece,
            left=static_left,
            right=static_right,
            left_profile=left_profile,
            right_profile=right_profile,
        )
        pieces.append(piece)

    pieces.append(frames[-1][bottom:])
    non_empty = [piece for piece in pieces if piece.size]
    return np.ascontiguousarray(np.concatenate(non_empty, axis=0))


def create_resilient_stitcher(
    core: ModuleType,
    baseline_stitcher: Callable[..., np.ndarray],
) -> Callable[..., np.ndarray]:
    """Preserve the stable stitcher and recover browser-specific stitching failures."""

    recoverable_messages = {
        "detected scrolling content band is too small",
        "invalid shift",
    }

    def stitch_frames(
        frames: Sequence[np.ndarray],
        shifts: Sequence[object],
    ) -> np.ndarray:
        matches = (
            list(shifts)
            if frames
            and len(shifts) == len(frames) - 1
            and shifts
            and all(isinstance(item, core.ShiftMatch) for item in shifts)
            else []
        )

        selected_band: tuple[int, int] | None = None
        static_sides = (0, 0)
        if matches:
            height, width = frames[0].shape[:2]
            if all(frame.shape[:2] == (height, width) for frame in frames):
                selected_band = _select_consensus_band(frames, matches)
                static_sides = _detect_static_side_bands(
                    frames,
                    matches,
                    selected_band[0],
                    selected_band[1],
                )
                if any(static_sides):
                    try:
                        return _stitch_with_common_band(
                            frames,
                            matches,
                            selected_band[0],
                            selected_band[1],
                            static_left=static_sides[0],
                            static_right=static_sides[1],
                        )
                    except ValueError:
                        pass

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

        top, bottom = selected_band or _select_consensus_band(frames, matches)
        if not any(static_sides):
            static_sides = _detect_static_side_bands(
                frames,
                matches,
                top,
                bottom,
            )
        try:
            return _stitch_with_common_band(
                frames,
                matches,
                top,
                bottom,
                static_left=static_sides[0],
                static_right=static_sides[1],
            )
        except ValueError:
            raw_shifts = [int(match.shift) for match in matches]
            return baseline_stitcher(frames, raw_shifts)

    return stitch_frames
