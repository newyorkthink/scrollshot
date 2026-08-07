#!/usr/bin/env python3
"""Tests for capture option adjustment."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from capture_options import effective_min_overlap


class CaptureOptionsTests(unittest.TestCase):
    def test_preserves_requested_overlap_for_tall_region(self) -> None:
        self.assertEqual(effective_min_overlap(80, 420), 80)

    def test_caps_overlap_for_short_region(self) -> None:
        self.assertEqual(effective_min_overlap(80, 100), 64)
        self.assertEqual(effective_min_overlap(80, 60), 24)

    def test_tiny_region_falls_back_without_error(self) -> None:
        self.assertEqual(effective_min_overlap(80, 32), 8)

    def test_rejects_invalid_values(self) -> None:
        with self.assertRaises(ValueError):
            effective_min_overlap(7, 100)
        with self.assertRaises(ValueError):
            effective_min_overlap(80, 0)


if __name__ == "__main__":
    unittest.main()
