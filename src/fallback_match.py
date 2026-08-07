#!/usr/bin/env python3
"""Fallback vertical shift matching for browser pages that defeat the primary matcher."""

from __future__ import annotations

from types import ModuleType
from typing import Callable

import cv2
import numpy as np

FALLBACK_EDGE_BINS = 48
FALLBACK_MIN_SCORE = 0.34
FALLBACK_SCORE_MARGIN = 0.06
FALLBACK_TRIM_RATIO = 0.10
FALLBACK_SIDE_MARGIN_RATIO = 0.08


def _fallback_band(height: int) -> tuple[int, int]:
    trim = max(8, int(height * FALLBACK_TRIM_RATIO))
    if height - trim * 2 < 64:
        return 0, height
    return trim, height - trim


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


def create_fallback_estimator(
    core: ModuleType,
    baseline_estimator: Callable[..., object],
) -> Callable[..., object]:
    """Use a conservative full-band edge matcher only when the existing matcher gives up."""

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

        candidate = _best_shift(
            previous,
            current,
            band,
            min_shift=int(min_shift),
            maximum_shift=maximum_shift,
        )
        if candidate is None:
            return None
        shift, score, runner_up = candidate

        minimum_score = max(FALLBACK_MIN_SCORE, float(score_threshold) - 0.38)
        if score < minimum_score:
            return None
        if runner_up >= minimum_score and score - runner_up < FALLBACK_SCORE_MARGIN:
            return None

        top, bottom = band
        margin_x = max(8, int(width * 0.08))
        previous_gray = cv2.GaussianBlur(
            core.to_gray(previous)[:, margin_x : width - margin_x],
            (3, 3),
            0,
        )
        current_gray = cv2.GaussianBlur(
            core.to_gray(current)[:, margin_x : width - margin_x],
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
            return None
        aligned_error, static_error, _compare_height = verified
        improvement = static_error - aligned_error
        if aligned_error > 24.0:
            return None
        if improvement < 1.5 and aligned_error > 6.0:
            return None

        return core.ShiftMatch(
            shift=int(shift),
            score=float(score),
            anchors=1,
            content_top=int(top),
            content_bottom=int(bottom),
            alignment_error=float(aligned_error),
        )

    return estimate_vertical_shift
