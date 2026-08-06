#!/usr/bin/env python3
"""框选预览与 X11 图像转换测试。"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import numpy as np

MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "scrollshot.py"
SPEC = importlib.util.spec_from_file_location("scrollshot", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
scrollshot = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = scrollshot
SPEC.loader.exec_module(scrollshot)


class SelectionPreviewTests(unittest.TestCase):
    def test_decode_x11_four_byte_pixels(self) -> None:
        data = bytes(
            [
                10,
                20,
                30,
                0,
                40,
                50,
                60,
                0,
            ]
        )
        frame = scrollshot.decode_x11_image(data, 2, 1)
        np.testing.assert_array_equal(
            frame,
            np.array([[[10, 20, 30], [40, 50, 60]]], dtype=np.uint8),
        )

    def test_selection_preview_remains_visible(self) -> None:
        frame = np.full((12, 16, 3), 200, dtype=np.uint8)
        preview = scrollshot.build_selection_preview(frame)
        self.assertEqual(preview.shape, frame.shape)
        self.assertGreater(int(preview.mean()), 0)
        self.assertLess(int(preview.mean()), int(frame.mean()))

    def test_frame_to_ppm_contains_dimensions(self) -> None:
        frame = np.zeros((3, 5, 3), dtype=np.uint8)
        ppm = scrollshot.frame_to_ppm(frame)
        self.assertTrue(ppm.startswith(b"P6\n5 3\n255\n"))
        self.assertEqual(len(ppm), len(b"P6\n5 3\n255\n") + 3 * 5 * 3)


if __name__ == "__main__":
    unittest.main()
