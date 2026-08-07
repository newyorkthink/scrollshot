#!/usr/bin/env python3
"""Regression tests for resilient browser-style stitching."""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from types import SimpleNamespace

import cv2
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


def build_browser_frame_with_fixed_sides(
    document: np.ndarray,
    start: int,
    *,
    viewport_height: int = 720,
    width: int = 1000,
    left_width: int = 180,
    right_width: int = 24,
    header_height: int = 80,
    footer_height: int = 60,
) -> np.ndarray:
    content_height = viewport_height - header_height - footer_height
    frame = np.full((viewport_height, width, 3), 245, dtype=np.uint8)
    frame[:header_height] = (25, 30, 40)
    frame[-footer_height:] = (230, 232, 235)

    frame[header_height : viewport_height - footer_height, :left_width] = (
        248,
        248,
        248,
    )
    for index, y in enumerate(
        range(header_height + 24, viewport_height - footer_height, 38)
    ):
        cv2.putText(
            frame,
            f"item {index:02d}",
            (12, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (35, 35, 35),
            1,
            cv2.LINE_AA,
        )
    frame[:, left_width - 1 : left_width + 1] = (205, 205, 205)

    frame[
        header_height : viewport_height - footer_height,
        left_width : width - right_width,
    ] = document[start : start + content_height]

    frame[:, width - right_width :] = (250, 250, 250)
    cv2.rectangle(
        frame,
        (width - 10, 140),
        (width - 6, 260),
        (180, 180, 180),
        -1,
    )
    return frame


def build_frame_with_moving_scrollbar(
    document: np.ndarray,
    start: int,
    thumb_y: int,
    *,
    viewport_height: int = 720,
    right_width: int = 16,
    header_height: int = 80,
    footer_height: int = 60,
) -> np.ndarray:
    width = document.shape[1] + right_width
    content_height = viewport_height - header_height - footer_height
    frame = np.full((viewport_height, width, 3), 248, dtype=np.uint8)
    frame[:header_height, :-right_width] = (30, 35, 45)
    frame[-footer_height:, :-right_width] = (232, 234, 236)
    frame[
        header_height : viewport_height - footer_height,
        :-right_width,
    ] = document[start : start + content_height]

    frame[:, -right_width:] = (248, 248, 248)
    cv2.rectangle(
        frame,
        (width - 8, thumb_y),
        (width - 5, min(viewport_height - 1, thumb_y + 72)),
        (150, 150, 150),
        -1,
    )
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

    def test_fixed_browser_sidebars_are_not_repeated(self) -> None:
        rng = np.random.default_rng(20260807)
        document = rng.integers(
            0,
            255,
            size=(2400, 796, 3),
            dtype=np.uint8,
        )
        shifts = [180, 170, 95]
        starts = [0, 180, 350, 445]
        frames = [
            build_browser_frame_with_fixed_sides(document, start)
            for start in starts
        ]
        matches = [
            ShiftMatch(shift, content_top=80, content_bottom=660)
            for shift in shifts
        ]

        def baseline(frames, shifts):
            pieces = [frames[0][:660]]
            for frame, match in zip(frames[1:], shifts):
                pieces.append(frame[660 - int(match.shift) : 660])
            pieces.append(frames[-1][660:])
            return np.ascontiguousarray(np.concatenate(pieces, axis=0))

        core = SimpleNamespace(ShiftMatch=ShiftMatch)
        wrapper = create_resilient_stitcher(core, baseline)
        stitched = wrapper(frames, matches)
        repeated = baseline(frames, matches)

        self.assertEqual(stitched.shape[:2], (720 + sum(shifts), 1000))
        np.testing.assert_array_equal(
            stitched[:, 180:-24],
            repeated[:, 180:-24],
        )

        appended_start = 660
        appended_end = appended_start + sum(shifts)
        left_profile = np.rint(
            np.median(frames[0][80:660, :180], axis=0)
        ).astype(np.uint8)
        right_profile = np.rint(
            np.median(frames[0][80:660, -24:], axis=0)
        ).astype(np.uint8)

        np.testing.assert_array_equal(
            stitched[appended_start:appended_end, :180],
            np.broadcast_to(
                left_profile,
                (sum(shifts), 180, 3),
            ),
        )
        np.testing.assert_array_equal(
            stitched[appended_start:appended_end, -24:],
            np.broadcast_to(
                right_profile,
                (sum(shifts), 24, 3),
            ),
        )
        self.assertFalse(
            np.array_equal(
                stitched[appended_start:appended_end, :180],
                repeated[appended_start:appended_end, :180],
            )
        )

    def test_moving_right_scrollbar_is_not_repeated(self) -> None:
        rng = np.random.default_rng(20260807)
        document = rng.integers(
            0,
            255,
            size=(2400, 744, 3),
            dtype=np.uint8,
        )
        shifts = [180, 170, 95]
        starts = [0, 180, 350, 445]
        frames = [
            build_frame_with_moving_scrollbar(document, start, thumb_y)
            for start, thumb_y in zip(starts, (110, 510, 520, 570))
        ]
        matches = [
            ShiftMatch(shift, content_top=80, content_bottom=660)
            for shift in shifts
        ]

        def baseline(frames, shifts):
            pieces = [frames[0][:660]]
            for frame, match in zip(frames[1:], shifts):
                pieces.append(frame[660 - int(match.shift) : 660])
            pieces.append(frames[-1][660:])
            return np.ascontiguousarray(np.concatenate(pieces, axis=0))

        core = SimpleNamespace(ShiftMatch=ShiftMatch)
        wrapper = create_resilient_stitcher(core, baseline)
        stitched = wrapper(frames, matches)
        repeated = baseline(frames, matches)

        self.assertEqual(stitched.shape[:2], (720 + sum(shifts), 760))
        np.testing.assert_array_equal(stitched[:, :-16], repeated[:, :-16])

        appended_start = 660
        appended_end = appended_start + sum(shifts)
        right_profile = np.rint(
            np.median(frames[0][80:660, -16:], axis=0)
        ).astype(np.uint8)

        np.testing.assert_array_equal(
            stitched[appended_start:appended_end, -16:],
            np.broadcast_to(
                right_profile,
                (sum(shifts), 16, 3),
            ),
        )
        self.assertFalse(
            np.array_equal(
                stitched[appended_start:appended_end, -16:],
                repeated[appended_start:appended_end, -16:],
            )
        )

    def test_scrolling_content_at_right_edge_is_not_masked(self) -> None:
        rng = np.random.default_rng(20260808)
        document = rng.integers(
            0,
            255,
            size=(2400, 760, 3),
            dtype=np.uint8,
        )
        shifts = [180, 170, 95]
        starts = [0, 180, 350, 445]
        frames = [build_frame(document, start) for start in starts]
        matches = [
            ShiftMatch(shift, content_top=80, content_bottom=660)
            for shift in shifts
        ]

        def baseline(frames, shifts):
            pieces = [frames[0][:660]]
            for frame, match in zip(frames[1:], shifts):
                pieces.append(frame[660 - int(match.shift) : 660])
            pieces.append(frames[-1][660:])
            return np.ascontiguousarray(np.concatenate(pieces, axis=0))

        core = SimpleNamespace(ShiftMatch=ShiftMatch)
        wrapper = create_resilient_stitcher(core, baseline)
        repeated = baseline(frames, matches)
        stitched = wrapper(frames, matches)

        np.testing.assert_array_equal(stitched, repeated)

    def test_non_recoverable_programming_error_is_not_hidden(self) -> None:
        core = SimpleNamespace(ShiftMatch=ShiftMatch)

        def baseline(_frames, _shifts):
            raise ValueError("frame and shift counts do not match")

        wrapper = create_resilient_stitcher(core, baseline)
        with self.assertRaisesRegex(ValueError, "frame and shift counts"):
            wrapper([], [])


if __name__ == "__main__":
    unittest.main()
