#!/usr/bin/env python3
"""ScrollShot 核心拼接算法测试。"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "scrollshot.py"
SPEC = importlib.util.spec_from_file_location("scrollshot", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
scrollshot = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = scrollshot
SPEC.loader.exec_module(scrollshot)


def build_document(width: int = 640, height: int = 2200) -> np.ndarray:
    """生成包含文字、横线和块状纹理的可重复测试页面。"""

    rng = np.random.default_rng(20260807)
    image = np.full((height, width, 3), 245, dtype=np.uint8)

    for y in range(20, height, 55):
        shade = int(rng.integers(20, 190))
        cv2.putText(
            image,
            f"ScrollShot line {y:04d}",
            (24, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (shade, 30, 210 - shade // 2),
            2,
            cv2.LINE_AA,
        )
        cv2.line(image, (20, y + 12), (width - 20, y + 12), (180, 180, 180), 1)

    for _ in range(80):
        x1 = int(rng.integers(10, width - 100))
        y1 = int(rng.integers(10, height - 80))
        x2 = min(width - 1, x1 + int(rng.integers(20, 100)))
        y2 = min(height - 1, y1 + int(rng.integers(10, 70)))
        color = tuple(int(value) for value in rng.integers(20, 235, size=3))
        cv2.rectangle(image, (x1, y1), (x2, y2), color, -1)

    return image


class GeometryTests(unittest.TestCase):
    def test_parse_geometry(self) -> None:
        region = scrollshot.parse_geometry("10,20,800,600")
        self.assertEqual(region, scrollshot.Region(10, 20, 800, 600))

    def test_unique_output_path_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            original = Path(directory) / "capture.png"
            original.write_bytes(b"existing")
            candidate = scrollshot.unique_output_path(original)
            self.assertEqual(candidate.name, "capture-01.png")


class MatchingTests(unittest.TestCase):
    def test_estimate_vertical_shift(self) -> None:
        document = build_document()
        viewport_height = 720
        shift = 173
        previous = document[0:viewport_height]
        current = document[shift : shift + viewport_height]

        match = scrollshot.estimate_vertical_shift(
            previous,
            current,
            min_overlap=100,
            score_threshold=0.65,
        )

        self.assertIsNotNone(match)
        assert match is not None
        self.assertLessEqual(abs(match.shift - shift), 2)
        self.assertGreaterEqual(match.anchors, 2)

    def test_estimate_partial_final_scroll(self) -> None:
        document = build_document()
        viewport_height = 680
        previous_start = 1000
        shift = 47
        previous = document[previous_start : previous_start + viewport_height]
        current = document[
            previous_start + shift : previous_start + shift + viewport_height
        ]

        match = scrollshot.estimate_vertical_shift(
            previous,
            current,
            min_overlap=100,
            score_threshold=0.65,
        )

        self.assertIsNotNone(match)
        assert match is not None
        self.assertLessEqual(abs(match.shift - shift), 2)

    def test_stable_frame_allows_small_animation(self) -> None:
        frame = build_document(width=500, height=500)
        animated = frame.copy()
        animated[100:108, 100:108] = 0
        self.assertTrue(scrollshot.frames_are_stable(frame, animated))

    def test_repetitive_scrolled_content_is_not_stable(self) -> None:
        frame = np.full((400, 400, 3), 255, dtype=np.uint8)
        for y in range(0, 400, 28):
            cv2.putText(
                frame,
                f"line {y // 28:02d}",
                (15, y + 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 0, 0),
                1,
                cv2.LINE_AA,
            )
        shifted = np.roll(frame, -84, axis=0)
        self.assertFalse(scrollshot.frames_are_stable(frame, shifted))

    def test_repetitive_layout_uses_full_overlap(self) -> None:
        document = np.full((1800, 420, 3), 255, dtype=np.uint8)
        for index, y in enumerate(range(0, 1800, 27)):
            background = 255 if index % 2 == 0 else 232
            cv2.rectangle(document, (0, y), (419, min(y + 26, 1799)), (background,) * 3, -1)
            cv2.putText(
                document,
                f"ScrollShot line {index:03d}",
                (14, y + 19),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.52,
                (20, 20, 20),
                1,
                cv2.LINE_AA,
            )
        shift = 216
        previous = document[:400]
        current = document[shift : shift + 400]
        match = scrollshot.estimate_vertical_shift(previous, current, min_overlap=80)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertLessEqual(abs(match.shift - shift), 2)

    def test_stitch_frames_reconstructs_document(self) -> None:
        document = build_document(width=500, height=1300)
        viewport_height = 600
        first_shift = 210
        second_shift = 185

        frame1 = document[0:viewport_height]
        frame2 = document[first_shift : first_shift + viewport_height]
        frame3 = document[
            first_shift + second_shift : first_shift + second_shift + viewport_height
        ]

        stitched = scrollshot.stitch_frames(
            [frame1, frame2, frame3],
            [first_shift, second_shift],
        )
        expected = document[: viewport_height + first_shift + second_shift]
        np.testing.assert_array_equal(stitched, expected)


if __name__ == "__main__":
    unittest.main()
