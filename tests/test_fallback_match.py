#!/usr/bin/env python3
from __future__ import annotations

import unittest
from dataclasses import dataclass
from types import SimpleNamespace

import cv2
import numpy as np

from fallback_match import create_fallback_estimator


@dataclass(frozen=True)
class ShiftMatch:
    shift: int
    score: float
    anchors: int
    content_top: int = 0
    content_bottom: int = 0
    alignment_error: float = 0.0


def to_gray(frame: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def candidate_alignment(previous_gray, current_gray, shift, band):
    height = previous_gray.shape[0]
    top, bottom = band
    compare_end = min(bottom, height - shift)
    if compare_end - top < 48:
        return None
    previous_aligned = previous_gray[top + shift : compare_end + shift]
    current_aligned = current_gray[top:compare_end]
    previous_static = previous_gray[top:compare_end]
    aligned_error = float(np.mean(cv2.absdiff(previous_aligned, current_aligned)))
    static_error = float(np.mean(cv2.absdiff(previous_static, current_aligned)))
    return aligned_error, static_error, compare_end - top


def fake_core():
    return SimpleNamespace(
        detect_motion_band=lambda _previous, _current: None,
        to_gray=to_gray,
        _candidate_alignment=candidate_alignment,
        ShiftMatch=ShiftMatch,
    )


class FallbackMatchTests(unittest.TestCase):
    def test_recovers_browser_shift_when_motion_band_is_unavailable(self) -> None:
        rng = np.random.default_rng(20260807)
        height, width = 720, 620
        shift = 173
        document = np.full((1800, width, 3), 248, dtype=np.uint8)
        for index, y in enumerate(range(24, 1780, 31)):
            x = int(rng.integers(20, 160))
            cv2.putText(
                document,
                f"item {index:03d} value {int(rng.integers(100000))}",
                (x, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (35, 35, 35),
                1,
                cv2.LINE_AA,
            )
            if index % 3 == 0:
                cv2.rectangle(document, (320, y - 16), (585, y - 4), (175, 175, 175), 1)

        previous = document[:height].copy()
        current = document[shift : shift + height].copy()
        previous[:58] = 30
        current[:58] = 30
        previous[-46:] = 232
        current[-46:] = 232

        estimator = create_fallback_estimator(fake_core(), lambda *_a, **_k: None)
        match = estimator(previous, current, min_overlap=80)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertLessEqual(abs(match.shift - shift), 2)

    def test_identical_frame_does_not_create_false_scroll(self) -> None:
        rng = np.random.default_rng(20260808)
        frame = rng.integers(0, 256, size=(720, 520, 3), dtype=np.uint8)
        estimator = create_fallback_estimator(fake_core(), lambda *_a, **_k: None)
        self.assertIsNone(estimator(frame, frame.copy(), min_overlap=80))


if __name__ == "__main__":
    unittest.main()
