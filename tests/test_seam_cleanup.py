#!/usr/bin/env python3
from __future__ import annotations

import unittest
from dataclasses import dataclass

import numpy as np

from seam_cleanup import cleanup_stitch_seams


@dataclass(frozen=True)
class Match:
    shift: int
    content_bottom: int


class SeamCleanupTests(unittest.TestCase):
    def test_isolated_dark_line_at_stitch_boundary_is_repaired(self) -> None:
        image = np.full((520, 260, 3), 245, dtype=np.uint8)
        matches = [Match(110, 210), Match(95, 210)]
        image[211] = 20
        repaired = cleanup_stitch_seams(image, matches)
        self.assertGreater(float(repaired[211].mean()), 230.0)

    def test_dark_line_away_from_stitch_boundary_is_preserved(self) -> None:
        image = np.full((520, 260, 3), 245, dtype=np.uint8)
        matches = [Match(110, 210), Match(95, 210)]
        image[275] = 20
        repaired = cleanup_stitch_seams(image, matches)
        self.assertEqual(float(repaired[275].mean()), 20.0)


if __name__ == "__main__":
    unittest.main()
