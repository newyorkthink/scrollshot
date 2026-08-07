#!/usr/bin/env python3
"""Structural shift verification for repetitive scrolling layouts."""

from __future__ import annotations

from types import ModuleType
from typing import Callable

import cv2
import numpy as np

STRUCTURAL_MIN_SCORE = 0.35
STRUCTURAL_OVERRIDE_MARGIN = 0.08
STRUCTURAL_SCORE_WINDOW = 2
STRUCTURAL_CANDIDATE_GAP = 4
STRUCTURAL_CANDIDATE_LIMIT = 12
STRUCTURAL_QUALITY_WEIGHT = 12.0


def _edge_feature_pair(
    previous: np.ndarray,
    current: np.ndarray,
    band: tuple[int, int],
    *,
    bins: int = 48,
) -> tuple[np.ndarray, np.ndarray]:
    """Build matching per-row vertical-edge features with one shared column mask."""

    previous_gray = (
        previous if previous.ndim == 2 else cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY)
    )
    current_gray = (
        current if current.ndim == 2 else cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
    )
    previous_edges = np.abs(cv2.Sobel(previous_gray, cv2.CV_32F, 1, 0, ksize=3))
    current_edges = np.abs(cv2.Sobel(current_gray, cv2.CV_32F, 1, 0, ksize=3))

    height, width = previous_edges.shape[:2]
    top, bottom = band
    top = max(0, min(height - 1, int(top)))
    bottom = max(top + 1, min(height, int(bottom)))

    left = max(4, int(width * 0.02))
    right = min(width - 4, int(width * 0.98))
    if right - left < 16:
        left, right = 0, width

    activity = (
        np.mean(previous_edges[top:bottom, left:right], axis=0)
        + np.mean(current_edges[top:bottom, left:right], axis=0)
    )
    if activity.size == 0:
        empty = np.empty((height, 0), dtype=np.float32)
        return empty, empty

    threshold = float(np.percentile(activity, 60))
    active = activity >= threshold
    bin_count = min(int(bins), max(12, (right - left) // 40))
    boundaries = np.linspace(left, right, bin_count + 1, dtype=int)

    def build_features(edges: np.ndarray) -> np.ndarray:
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

    return build_features(previous_edges), build_features(current_edges)


def _structural_shift_scores(
    previous: np.ndarray,
    current: np.ndarray,
    band: tuple[int, int],
    *,
    min_shift: int,
    maximum_shift: int,
) -> dict[int, float]:
    """Score each vertical shift from text/icon edges instead of row backgrounds."""

    previous_features, current_features = _edge_feature_pair(previous, current, band)
    if (
        previous_features.shape != current_features.shape
        or previous_features.shape[1] == 0
    ):
        return {}

    height = previous_features.shape[0]
    top, bottom = band
    minimum_compare = max(48, int((bottom - top) * 0.20))
    scores: dict[int, float] = {}

    for shift in range(int(min_shift), int(maximum_shift) + 1):
        compare_end = min(bottom, height - shift)
        if compare_end - top < minimum_compare:
            continue

        previous_aligned = previous_features[top + shift : compare_end + shift]
        current_aligned = current_features[top:compare_end]
        previous_centered = previous_aligned - np.mean(
            previous_aligned, axis=0, keepdims=True
        )
        current_centered = current_aligned - np.mean(
            current_aligned, axis=0, keepdims=True
        )
        denominator = float(
            np.sqrt(
                np.sum(previous_centered * previous_centered)
                * np.sum(current_centered * current_centered)
            )
        )
        if denominator <= 1e-6:
            continue

        scores[shift] = float(
            np.sum(previous_centered * current_centered) / denominator
        )

    return scores


def _score_near(scores: dict[int, float], shift: int) -> float:
    if not scores:
        return -1.0
    minimum_shift = min(scores)
    maximum_shift = max(scores)
    return max(
        (
            scores.get(candidate, -1.0)
            for candidate in range(
                max(minimum_shift, int(shift) - STRUCTURAL_SCORE_WINDOW),
                min(maximum_shift, int(shift) + STRUCTURAL_SCORE_WINDOW) + 1,
            )
        ),
        default=-1.0,
    )


def _structural_candidates(scores: dict[int, float]) -> list[int]:
    candidates: list[int] = []
    for shift, _score in sorted(
        scores.items(),
        key=lambda item: item[1],
        reverse=True,
    ):
        if any(
            abs(shift - existing) <= STRUCTURAL_CANDIDATE_GAP
            for existing in candidates
        ):
            continue
        candidates.append(shift)
        if len(candidates) >= STRUCTURAL_CANDIDATE_LIMIT:
            break
    return candidates


def create_structural_estimator(
    core: ModuleType,
    baseline_estimator: Callable[..., object],
) -> Callable[..., object]:
    """Wrap the stable matcher and override only clearly periodic false matches."""

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

        if previous.shape != current.shape:
            return baseline

        height, width = previous.shape[:2]
        maximum_shift = height - int(min_overlap)
        if (
            height < int(min_overlap) + int(min_shift) + 32
            or width < 64
            or maximum_shift <= int(min_shift)
        ):
            return baseline

        band = core.detect_motion_band(previous, current)
        if band is None:
            return baseline

        structural_scores = _structural_shift_scores(
            previous,
            current,
            band,
            min_shift=int(min_shift),
            maximum_shift=maximum_shift,
        )
        if not structural_scores:
            return baseline

        best_structural = max(structural_scores.values())
        structural_minimum = max(
            STRUCTURAL_MIN_SCORE,
            float(score_threshold) - 0.33,
        )
        if best_structural < structural_minimum:
            return baseline

        baseline_structural = (
            _score_near(structural_scores, baseline.shift)
            if baseline is not None
            else -1.0
        )
        if (
            baseline is not None
            and best_structural - baseline_structural < STRUCTURAL_OVERRIDE_MARGIN
        ):
            return baseline

        content_top, content_bottom = band
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

        candidate_floor = max(0.28, best_structural - 0.09)
        candidates = _structural_candidates(structural_scores)
        if baseline is not None and all(
            abs(int(baseline.shift) - candidate) > STRUCTURAL_CANDIDATE_GAP
            for candidate in candidates
        ):
            candidates.append(int(baseline.shift))

        verified: list[tuple[float, int, float, float]] = []
        for shift in candidates:
            structural_score = _score_near(structural_scores, shift)
            if structural_score < candidate_floor:
                continue

            result = core._candidate_alignment(
                previous_gray,
                current_gray,
                shift,
                band,
            )
            if result is None:
                continue

            aligned_error, static_error, _compare_height = result
            if aligned_error > 30.0:
                continue

            improvement = static_error - aligned_error
            if (
                improvement < 2.0
                and aligned_error > 7.0
                and structural_score < structural_minimum
            ):
                continue

            quality = (
                aligned_error
                - min(12.0, max(0.0, improvement)) * 0.20
                - structural_score * STRUCTURAL_QUALITY_WEIGHT
            )
            verified.append(
                (quality, shift, aligned_error, structural_score)
            )

        if not verified:
            return baseline

        _quality, shift, aligned_error, structural_score = min(
            verified,
            key=lambda item: item[0],
        )
        if baseline is not None and abs(int(baseline.shift) - shift) <= 3:
            return baseline

        return core.ShiftMatch(
            shift=shift,
            score=structural_score,
            anchors=1,
            content_top=content_top,
            content_bottom=content_bottom,
            alignment_error=aligned_error,
        )

    return estimate_vertical_shift
