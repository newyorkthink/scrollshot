#!/usr/bin/env python3
"""Regression tests for resilient browser-style stitching."""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np

from resilient_stitch import create_resilient_stitcher


@dataclass(frozen=True)
class ShiftMatch:
    shift: int
    score: float = 1.0
    anchors: int = 1
    content_top: int = 0
    content_bottom: int = 0
    alignment_error: float = 0.0


def build_frame(
    document: np.ndarray,
    start: int,
    *,
    viewport_height: int = 720,
    header_height: int = 80,
    footer_height: int = 60,
) -> np.ndarray:
    width = document.shape[1]
    content_height = viewport_height - header_height - footer_height
    frame = np.full((viewport_height, width, 3), 240, dtype=np.uint8)
    frame[:header_height] = (20, 30, 40)
    frame[header_height : viewport_height - footer_height] = document[
        start : start + content_height
    ]
    frame[-footer_height:] = (210, 220, 230)
    return frame


class ResilientStitchTests(unittest.TestCase):
    def test_successful_baseline_is_left_unchanged(self) -> None:
        core = SimpleNamespace(ShiftMatch=ShiftMatch)
        expected = np.zeros((3, 4, 3), dtype=np.uint8)
        wrapper = create_resilient_stitcher(
            core,
            lambda _frames, _shifts: expected,
        )
        result = wrapper([expected], [])
        self.assertIs(result, expected)

    def test_noisy_browser_motion_band_still_produces_complete_image(self) -> None:
        rng = np.random.default_rng(20260807)
        document = rng.integers(
            0,
            255,
            size=(2200, 320, 3),
            dtype=np.uint8,
        )
        shifts = [180, 170, 95]
        starts = [0, 180, 350, 445]
        frames = [build_frame(document, start) for start in starts]
        matches = [
            ShiftMatch(shifts[0], content_top=80, content_bottom=660),
            ShiftMatch(shifts[1], content_top=460, content_bottom=650),
            ShiftMatch(shifts[2], content_top=85, content_bottom=665),
        ]

        def baseline(frames, shifts):
            if shifts and isinstance(shifts[0], ShiftMatch):
                raise ValueError("detected scrolling content band is too small")
            pieces = [frames[0]]
            for frame, shift in zip(frames[1:], shifts):
                pieces.append(frame[-int(shift) :])
            return np.ascontiguousarray(np.concatenate(pieces, axis=0))

        core = SimpleNamespace(ShiftMatch=ShiftMatch)
        wrapper = create_resilient_stitcher(core, baseline)
        stitched = wrapper(frames, matches)

        self.assertEqual(stitched.shape[:2], (720 + sum(shifts), 320))
        np.testing.assert_array_equal(stitched[:660], frames[0][:660])
        np.testing.assert_array_equal(stitched[-60:], frames[-1][-60:])

    def test_non_recoverable_programming_error_is_not_hidden(self) -> None:
        core = SimpleNamespace(ShiftMatch=ShiftMatch)

        def baseline(_frames, _shifts):
            raise ValueError("frame and shift counts do not match")

        wrapper = create_resilient_stitcher(core, baseline)
        with self.assertRaisesRegex(ValueError, "frame and shift counts"):
            wrapper([], [])


if __name__ == "__main__":
    unittest.main()
