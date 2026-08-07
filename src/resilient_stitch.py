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

MOVING_RIGHT_EDGE_BLOCK = 4
MOVING_RIGHT_EDGE_MAX_PIXELS = 24
MOVING_RIGHT_EDGE_ROW_ERROR = 4.0
MOVING_RIGHT_EDGE_STATIC_FRACTION = 0.68
MOVING_RIGHT_EDGE_MIN_WIDTH = 8

# Some full-window viewers draw a thin, viewport-fixed dark separator exactly
# at the bottom edge of the scrolling pane. If that row is included in every
# appended slice, it becomes a repeated black line in the final long image.
# Only trim a very small bottom suffix when it is stable at the same screen
# coordinates across frames and contains a clearly darker separator.
STATIC_BOTTOM_MAX_ROWS = 12
STATIC_BOTTOM_REFERENCE_ROWS = 16
STATIC_BOTTOM_SAME_MAX_ERROR = 1.5
STATIC_BOTTOM_DARK_DELTA = 18.0
STATIC_BOTTOM_MIN_DYNAMIC_WIDTH = 96


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


def _detect_moving_right_edge(
    frames: Sequence[np.ndarray],
    matches: Sequence[object],
    top: int,
    bottom: int,
) -> int:
    """Detect a narrow viewport-fixed right edge whose thumb or indicator moves."""

    if len(frames) < 2 or not matches:
        return 0

    height, width = frames[0].shape[:2]
    maximum_width = min(
        MOVING_RIGHT_EDGE_MAX_PIXELS,
        max(0, width // 12),
    )
    maximum_width -= maximum_width % MOVING_RIGHT_EDGE_BLOCK
    if maximum_width < MOVING_RIGHT_EDGE_MIN_WIDTH or bottom - top < 48:
        return 0

    pair_errors: list[np.ndarray] = []
    for previous, current, match in zip(frames, frames[1:], matches):
        shift = int(match.shift)
        compare_end = min(bottom, height - shift)
        if shift <= 0 or compare_end - top < 48:
            continue

        previous_static = previous[top:compare_end, width - maximum_width :].astype(
            np.int16,
            copy=False,
        )
        current_static = current[top:compare_end, width - maximum_width :].astype(
            np.int16,
            copy=False,
        )
        if previous_static.shape != current_static.shape:
            continue

        pair_errors.append(
            np.mean(
                np.abs(previous_static - current_static),
                axis=2,
            )
        )

    if not pair_errors:
        return 0

    static_flags: list[bool] = []
    for offset in range(0, maximum_width, MOVING_RIGHT_EDGE_BLOCK):
        start = maximum_width - offset - MOVING_RIGHT_EDGE_BLOCK
        end = maximum_width - offset
        fractions = []
        for errors in pair_errors:
            row_error = np.mean(errors[:, start:end], axis=1)
            fractions.append(
                float(np.mean(row_error <= MOVING_RIGHT_EDGE_ROW_ERROR))
            )
        static_flags.append(
            float(np.median(fractions)) >= MOVING_RIGHT_EDGE_STATIC_FRACTION
        )

    last_static = -1
    for index, is_static in enumerate(static_flags):
        if not is_static:
            break
        last_static = index

    if last_static < 0:
        return 0

    width_detected = (last_static + 1) * MOVING_RIGHT_EDGE_BLOCK
    if width_detected < MOVING_RIGHT_EDGE_MIN_WIDTH:
        return 0
    return width_detected


def _detect_fixed_bottom_trim(
    frames: Sequence[np.ndarray],
    matches: Sequence[object],
    top: int,
    bottom: int,
    *,
    static_left: int = 0,
    static_right: int = 0,
) -> int:
    """Detect a short fixed dark separator touching the moving pane's bottom edge."""

    if len(frames) < 2 or not matches:
        return 0

    height, width = frames[0].shape[:2]
    if any(frame.shape[:2] != (height, width) for frame in frames):
        return 0

    left = max(0, min(width, int(static_left)))
    right = max(left, min(width, width - int(static_right)))
    if right - left < STATIC_BOTTOM_MIN_DYNAMIC_WIDTH or bottom - top < 64:
        return 0

    search_start = max(top + 16, bottom - STATIC_BOTTOM_MAX_ROWS)
    if search_start >= bottom:
        return 0

    pair_errors: list[np.ndarray] = []
    for previous, current in zip(frames, frames[1:]):
        previous_rows = previous[search_start:bottom, left:right].astype(
            np.int16,
            copy=False,
        )
        current_rows = current[search_start:bottom, left:right].astype(
            np.int16,
            copy=False,
        )
        if previous_rows.shape != current_rows.shape:
            return 0
        pair_errors.append(
            np.mean(np.abs(previous_rows - current_rows), axis=(1, 2))
        )

    if not pair_errors:
        return 0

    same_error = np.median(np.stack(pair_errors, axis=0), axis=0)
    static_rows = same_error <= STATIC_BOTTOM_SAME_MAX_ERROR

    suffix_start = len(static_rows)
    for index in range(len(static_rows) - 1, -1, -1):
        if not static_rows[index]:
            break
        suffix_start = index
    if suffix_start >= len(static_rows):
        return 0

    reference_start = max(top, search_start - STATIC_BOTTOM_REFERENCE_ROWS)
    if reference_start >= search_start:
        return 0

    reference_values: list[np.ndarray] = []
    candidate_values: list[np.ndarray] = []
    for frame in frames:
        reference_values.append(
            np.mean(
                frame[reference_start:search_start, left:right],
                axis=(1, 2),
            )
        )
        candidate_values.append(
            np.mean(
                frame[search_start:bottom, left:right],
                axis=(1, 2),
            )
        )

    reference_luma = float(np.median(np.concatenate(reference_values)))
    candidate_luma = np.median(np.stack(candidate_values, axis=0), axis=0)
    suffix_luma = candidate_luma[suffix_start:]
    if suffix_luma.size == 0:
        return 0
    if reference_luma - float(np.min(suffix_luma)) < STATIC_BOTTOM_DARK_DELTA:
        return 0

    return bottom - (search_start + suffix_start)


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
    bottom_trim: int = 0,
) -> np.ndarray:
    """Stitch one moving band and avoid repeating fixed browser side columns."""

    effective_bottom = max(top + 1, bottom - max(0, int(bottom_trim)))
    pieces: list[np.ndarray] = [frames[0][:effective_bottom]]
    band_height = effective_bottom - top

    left_profile = _side_background_profile(
        frames[0],
        top,
        effective_bottom,
        0,
        static_left,
    )
    right_profile = _side_background_profile(
        frames[0],
        top,
        effective_bottom,
        frames[0].shape[1] - static_right,
        frames[0].shape[1],
    )

    for frame, match in zip(frames[1:], matches):
        shift = int(match.shift)
        if shift <= 0 or shift >= band_height:
            raise ValueError("consensus band cannot contain detected shift")
        piece = frame[effective_bottom - shift : effective_bottom]
        piece = _mask_static_sides(
            piece,
            left=static_left,
            right=static_right,
            left_profile=left_profile,
            right_profile=right_profile,
        )
        pieces.append(piece)

    pieces.append(frames[-1][effective_bottom:])
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
        bottom_trim = 0
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
                moving_right = _detect_moving_right_edge(
                    frames,
                    matches,
                    selected_band[0],
                    selected_band[1],
                )
                static_sides = (
                    static_sides[0],
                    max(static_sides[1], moving_right),
                )
                if any(static_sides):
                    bottom_trim = _detect_fixed_bottom_trim(
                        frames,
                        matches,
                        selected_band[0],
                        selected_band[1],
                        static_left=static_sides[0],
                        static_right=static_sides[1],
                    )
                    try:
                        return _stitch_with_common_band(
                            frames,
                            matches,
                            selected_band[0],
                            selected_band[1],
                            static_left=static_sides[0],
                            static_right=static_sides[1],
                            bottom_trim=bottom_trim,
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
            moving_right = _detect_moving_right_edge(
                frames,
                matches,
                top,
                bottom,
            )
            static_sides = (
                static_sides[0],
                max(static_sides[1], moving_right),
            )
        if any(static_sides) and not bottom_trim:
            bottom_trim = _detect_fixed_bottom_trim(
                frames,
                matches,
                top,
                bottom,
                static_left=static_sides[0],
                static_right=static_sides[1],
            )
        try:
            return _stitch_with_common_band(
                frames,
                matches,
                top,
                bottom,
                static_left=static_sides[0],
                static_right=static_sides[1],
                bottom_trim=bottom_trim,
            )
        except ValueError:
            raw_shifts = [int(match.shift) for match in matches]
            return baseline_stitcher(frames, raw_shifts)

    return stitch_frames
