#!/usr/bin/env python3
"""Regression tests for repetitive striped scrolling layouts."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
CORE_SPEC = importlib.util.spec_from_file_location(
    "scrollshot", ROOT / "src" / "scrollshot.py"
)
assert CORE_SPEC is not None and CORE_SPEC.loader is not None
core = importlib.util.module_from_spec(CORE_SPEC)
sys.modules[CORE_SPEC.name] = core
CORE_SPEC.loader.exec_module(core)

sys.path.insert(0, str(ROOT / "src"))
from structural_match import create_structural_estimator


def build_sparse_striped_document(
    *,
    width: int = 1920,
    height: int = 2200,
    row_height: int = 27,
) -> np.ndarray:
    rng = np.random.default_rng(5)
    image = np.full((height, width, 3), 248, dtype=np.uint8)

    for index, y in enumerate(range(0, height, row_height)):
        background = 248 if index % 2 == 0 else 235
        image[y : min(y + row_height, height)] = (background,) * 3
        marker = max(0, background - 12)

        x = 15
        for enabled in rng.integers(0, 2, size=24):
            if enabled:
                start_y = y + 5 + int(rng.integers(0, 5))
                cv2.line(
                    image,
                    (x, start_y),
                    (x, min(y + row_height - 4, start_y + 12)),
                    (marker,) * 3,
                    1,
                )
            x += 4

        cv2.line(
            image,
            (110, y),
            (110, min(y + row_height - 1, height - 1)),
            (200, 200, 200),
            1,
        )

    return image


class StructuralMatchingTests(unittest.TestCase):
    def test_repetitive_stripes_do_not_collapse_to_periodic_alias(self) -> None:
        document = build_sparse_striped_document()
        viewport_height = 1038
        shift = 492
        previous = document[:viewport_height]
        current = document[shift : shift + viewport_height]

        baseline = core.estimate_vertical_shift(previous, current, min_overlap=80)
        self.assertIsNotNone(baseline)
        assert baseline is not None
        self.assertGreater(abs(baseline.shift - shift), 20)

        improved = create_structural_estimator(
            core,
            core.estimate_vertical_shift,
        )
        match = improved(previous, current, min_overlap=80)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertLessEqual(abs(match.shift - shift), 2)

    def test_strong_normal_match_is_left_unchanged(self) -> None:
        rng = np.random.default_rng(20260807)
        document = rng.integers(
            0,
            256,
            size=(1600, 520, 3),
            dtype=np.uint8,
        )
        shift = 173
        previous = document[:720]
        current = document[shift : shift + 720]

        baseline = core.estimate_vertical_shift(previous, current, min_overlap=100)
        self.assertIsNotNone(baseline)
        assert baseline is not None

        improved = create_structural_estimator(
            core,
            core.estimate_vertical_shift,
        )
        match = improved(previous, current, min_overlap=100)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(match.shift, baseline.shift)


if __name__ == "__main__":
    unittest.main()
