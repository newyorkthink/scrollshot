#!/usr/bin/env python3
"""Fallback vertical shift matching for browser pages and full application windows."""

from __future__ import annotations

from types import ModuleType
from typing import Callable, Iterator

import cv2
import numpy as np

FALLBACK_EDGE_BINS = 48
FALLBACK_MIN_SCORE = 0.34
FALLBACK_SCORE_MARGIN = 0.06
FALLBACK_TRIM_RATIO = 0.10
FALLBACK_SIDE_MARGIN_RATIO = 0.08

# Whole-window selections can include large fixed toolbars, side panels, or
# inspectors. These thresholds are only used after the normal matcher gives
# up, so successful existing matching paths are left unchanged.
FALLBACK_MOTION_PIXEL_THRESHOLD = 8
FALLBACK_MOTION_MIN_SCORE = 3.0
FALLBACK_MOTION_MIN_WIDTH_RATIO = 0.24
FALLBACK_MOTION_MAX_WIDTH_RATIO = 0.94
FALLBACK_MOTION_PADDING_RATIO = 0.02
FALLBACK_MOTION_SMOOTH_RATIO = 0.025
FALLBACK_MOTION_CLOSE_RATIO = 0.035


def _fallback_band(height: int) -> tuple[int, int]:
    trim = max(8, int(height * FALLBACK_TRIM_RATIO))
    if height - trim * 2 < 64:
        return 0, height
    return trim, height - trim


def _largest_true_segment(mask: np.ndarray) -> tuple[int, int] | None:
    best: tuple[int, int] | None = None
    start: int | None = None
    for index, value in enumerate(mask.astype(bool).tolist() + [False]):
        if value and start is None:
            start = index
        elif not value and start is not None:
            if best is None or index - start > best[1] - best[0]:
                best = (start, index)
            start = None
    return best


def _horizontal_motion_window(
    previous: np.ndarray,
    current: np.ndarray,
    band: tuple[int, int],
) -> tuple[int, int] | None:
    """Locate a broad horizontally scrolling content area inside a fixed GUI."""

    if previous.shape != current.shape:
        return None

    height, width = previous.shape[:2]
    top, bottom = band
    top = max(0, min(height - 1, int(top)))
    bottom = max(top + 1, min(height, int(bottom)))
    if bottom - top < 48 or width < 160:
        return None

    previous_gray = (
        previous if previous.ndim == 2 else cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY)
    )
    current_gray = (
        current if current.ndim == 2 else cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
    )
    difference = cv2.absdiff(
        previous_gray[top:bottom],
        current_gray[top:bottom],
    ).astype(np.float32)
    if difference.size == 0:
        return None

    changed_fraction = np.mean(
        difference > FALLBACK_MOTION_PIXEL_THRESHOLD,
        axis=0,
    )
    mean_difference = np.mean(difference, axis=0)
    score = changed_fraction * 24.0 + np.minimum(mean_difference, 32.0)

    smooth_width = max(9, int(width * FALLBACK_MOTION_SMOOTH_RATIO))
    if smooth_width % 2 == 0:
        smooth_width += 1
    kernel = np.full(smooth_width, 1.0 / smooth_width, dtype=np.float32)
    smooth = np.convolve(score.astype(np.float32), kernel, mode="same")

    low = float(np.percentile(smooth, 10))
    high = float(np.percentile(smooth, 90))
    if high < FALLBACK_MOTION_MIN_SCORE:
        return None

    threshold = max(
        FALLBACK_MOTION_MIN_SCORE,
        low + 0.24 * max(0.0, high - low),
    )
    mask = (smooth > threshold).astype(np.uint8).reshape(1, width)

    close_width = max(11, int(width * FALLBACK_MOTION_CLOSE_RATIO))
    if close_width % 2 == 0:
        close_width += 1
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        np.ones((1, close_width), dtype=np.uint8),
    )
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        np.ones((1, 7), dtype=np.uint8),
    ).ravel().astype(bool)

    segment = _largest_true_segment(mask)
    if segment is None:
        return None
    left, right = segment

    relaxed_threshold = max(
        2.0,
        threshold * 0.55,
    )
    while left > 0 and smooth[left - 1] > relaxed_threshold:
        left -= 1
    while right < width and smooth[right] > relaxed_threshold:
        right += 1

    padding = max(8, int(width * FALLBACK_MOTION_PADDING_RATIO))
    left = max(0, left - padding)
    right = min(width, right + padding)

    detected_width = right - left
    if detected_width < max(96, int(width * FALLBACK_MOTION_MIN_WIDTH_RATIO)):
        return None
    if detected_width >= int(width * FALLBACK_MOTION_MAX_WIDTH_RATIO):
        return None
    return left, right


def _edge_features(frame: np.ndarray, band: tuple[int, int]) -> np.ndarray:
    gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape[:2]
    top, bottom = band
    top = max(0, min(height - 1, int(top)))
    bottom = max(top + 1, min(height, int(bottom)))

    margin = max(6, int(width * FALLBACK_SIDE_MARGIN_RATIO))
    left = margin
    right = width - margin
    if right - left < 32:
        left, right = 0, width

    edges = np.abs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))
    activity = np.mean(edges[top:bottom, left:right], axis=0)
    if activity.size == 0:
        return np.empty((height, 0), dtype=np.float32)

    active = activity >= float(np.percentile(activity, 55))
    bin_count = min(FALLBACK_EDGE_BINS, max(12, (right - left) // 36))
    boundaries = np.linspace(left, right, bin_count + 1, dtype=int)
    columns: list[np.ndarray] = []
    for start, end in zip(boundaries[:-1], boundaries[1:]):
        if end <= start:
            continue
        local_active = active[start - left : end - left]
        block = edges[:, start:end]
        if local_active.any():
            columns.append(np.mean(block[:, local_active], axis=1))
        else:
            columns.append(np.mean(block, axis=1))
    if not columns:
        return np.empty((height, 0), dtype=np.float32)
    return np.stack(columns, axis=1).astype(np.float32)


def _score_shift(
    previous_features: np.ndarray,
    current_features: np.ndarray,
    shift: int,
    band: tuple[int, int],
) -> float | None:
    height = previous_features.shape[0]
    top, bottom = band
    compare_end = min(bottom, height - shift)
    if compare_end - top < max(48, int((bottom - top) * 0.20)):
        return None

    previous_aligned = previous_features[top + shift : compare_end + shift]
    current_aligned = current_features[top:compare_end]
    previous_centered = previous_aligned - np.mean(previous_aligned, axis=0, keepdims=True)
    current_centered = current_aligned - np.mean(current_aligned, axis=0, keepdims=True)
    denominator = float(
        np.sqrt(
            np.sum(previous_centered * previous_centered)
            * np.sum(current_centered * current_centered)
        )
    )
    if denominator <= 1e-6:
        return None
    return float(np.sum(previous_centered * current_centered) / denominator)


def _best_shift(
    previous: np.ndarray,
    current: np.ndarray,
    band: tuple[int, int],
    *,
    min_shift: int,
    maximum_shift: int,
) -> tuple[int, float, float] | None:
    previous_features = _edge_features(previous, band)
    current_features = _edge_features(current, band)
    if (
        previous_features.shape != current_features.shape
        or previous_features.shape[1] == 0
    ):
        return None

    scored: list[tuple[float, int]] = []
    for shift in range(int(min_shift), int(maximum_shift) + 1):
        score = _score_shift(previous_features, current_features, shift, band)
        if score is not None:
            scored.append((score, shift))
    if not scored:
        return None

    scored.sort(reverse=True)
    best_score, best_shift = scored[0]
    separated = [score for score, shift in scored[1:] if abs(shift - best_shift) > 4]
    runner_up = separated[0] if separated else -1.0
    return best_shift, best_score, runner_up


def _matching_views(
    previous: np.ndarray,
    current: np.ndarray,
    band: tuple[int, int],
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Try the detected scrolling pane first, then preserve the old full-width fallback."""

    motion_window = _horizontal_motion_window(previous, current, band)
    if motion_window is not None:
        left, right = motion_window
        yield previous[:, left:right], current[:, left:right]
    yield previous, current


def create_fallback_estimator(
    core: ModuleType,
    baseline_estimator: Callable[..., object],
) -> Callable[..., object]:
    """Use conservative edge matching only when the existing matcher gives up."""

    def estimate_vertical_shift(
        previous: np.ndarray,
        current: np.ndarray,
        *,
        min_overlap: int = 80,
        min_shift: int = 4,
        score_threshold: float = 0.68,
    ):
        baseline = baseline_estimator(
            previous,
            current,
            min_overlap=min_overlap,
            min_shift=min_shift,
            score_threshold=score_threshold,
        )
        if baseline is not None or previous.shape != current.shape:
            return baseline

        height, width = previous.shape[:2]
        maximum_shift = height - int(min_overlap)
        if (
            height < int(min_overlap) + int(min_shift) + 32
            or width < 64
            or maximum_shift <= int(min_shift)
        ):
            return None

        band = core.detect_motion_band(previous, current)
        if band is None:
            band = _fallback_band(height)

        minimum_score = max(FALLBACK_MIN_SCORE, float(score_threshold) - 0.38)

        for match_previous, match_current in _matching_views(
            previous,
            current,
            band,
        ):
            candidate = _best_shift(
                match_previous,
                match_current,
                band,
                min_shift=int(min_shift),
                maximum_shift=maximum_shift,
            )
            if candidate is None:
                continue
            shift, score, runner_up = candidate

            if score < minimum_score:
                continue
            if runner_up >= minimum_score and score - runner_up < FALLBACK_SCORE_MARGIN:
                continue

            match_width = match_previous.shape[1]
            margin_x = max(8, int(match_width * 0.08))
            if match_width - margin_x * 2 < 32:
                margin_x = 0
            right = match_width - margin_x if margin_x else match_width
            previous_gray = cv2.GaussianBlur(
                core.to_gray(match_previous)[:, margin_x:right],
                (3, 3),
                0,
            )
            current_gray = cv2.GaussianBlur(
                core.to_gray(match_current)[:, margin_x:right],
                (3, 3),
                0,
            )
            verified = core._candidate_alignment(
                previous_gray,
                current_gray,
                int(shift),
                band,
            )
            if verified is None:
                continue
            aligned_error, static_error, _compare_height = verified
            improvement = static_error - aligned_error
            if aligned_error > 24.0:
                continue
            if improvement < 1.5 and aligned_error > 6.0:
                continue

            top, bottom = band
            return core.ShiftMatch(
                shift=int(shift),
                score=float(score),
                anchors=1,
                content_top=int(top),
                content_bottom=int(bottom),
                alignment_error=float(aligned_error),
            )

        return None

    return estimate_vertical_shift
