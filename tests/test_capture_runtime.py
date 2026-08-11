#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

import capture_runtime


class StubMonitor:
    requested = False

    def wait(self, _timeout):
        return False

    def close(self):
        return None


class Region:
    x = 0
    y = 0
    width = 100
    height = 100


class Match:
    shift = 20
    content_top = 0
    content_bottom = 100


class CaptureRuntimeTests(unittest.TestCase):
    def test_apparent_bottom_gets_grace_period_before_stopping(self) -> None:
        sequence = [
            np.zeros((100, 100, 3), dtype=np.uint8),
            np.zeros((100, 100, 3), dtype=np.uint8),
            np.ones((100, 100, 3), dtype=np.uint8),
            np.full((100, 100, 3), 2, dtype=np.uint8),
            np.full((100, 100, 3), 2, dtype=np.uint8),
            np.full((100, 100, 3), 2, dtype=np.uint8),
            np.full((100, 100, 3), 2, dtype=np.uint8),
        ]

        class Controller:
            def __init__(self):
                self.index = 0

            def move_to_region(self, _region):
                return None

            def scroll_down(self, _ticks):
                return None

            def capture(self, _region):
                frame = sequence[min(self.index, len(sequence) - 1)]
                self.index += 1
                return frame

            def restore_pointer(self):
                return None

            def close(self):
                return None

        saved = {}

        core = SimpleNamespace(
            CaptureError=RuntimeError,
            unique_output_path=lambda path: path,
            default_output_path=lambda: Path("/tmp/scrollshot-test.png"),
            X11Controller=Controller,
            frames_are_stable=lambda a, b: np.array_equal(a, b),
            estimate_vertical_shift=lambda a, b, **_kwargs: (
                Match() if not np.array_equal(a, b) else None
            ),
            stitch_frames=lambda frames, matches: saved.update(
                frames=len(frames), matches=len(matches)
            ) or np.zeros((120, 100, 3), dtype=np.uint8),
            save_png=lambda path, image: saved.update(path=path, height=image.shape[0]),
        )
        args = SimpleNamespace(
            geometry=Region(),
            min_overlap=32,
            output=Path("/tmp/scrollshot-test.png"),
            debug_dir=None,
            settle_delay=0.0,
            scroll_ticks=3,
            delay=0.05,
            max_frames=10,
            stable_rounds=2,
            match_threshold=0.68,
        )

        with mock.patch.object(capture_runtime, "CaptureStopMonitor", StubMonitor), mock.patch.object(
            capture_runtime.time, "sleep", lambda _seconds: None
        ):
            runner = capture_runtime.create_capture_runner(
                core,
                lambda requested, height: min(requested, height - 36),
            )
            _path, frame_count, _height = runner(args)

        self.assertGreaterEqual(frame_count, 2)
        self.assertGreaterEqual(saved["matches"], 1)

    def test_scroll_up_reuses_stable_controller_interface_and_reverses_stitch_order(self) -> None:
        sequence = [
            np.zeros((100, 100, 3), dtype=np.uint8),
            np.ones((100, 100, 3), dtype=np.uint8),
        ]
        observed = {
            "scrolls": [],
            "estimate_pairs": [],
            "stitch_frames": [],
            "stitch_matches": 0,
        }

        class Controller:
            def __init__(self):
                self.index = 0

            def move_to_region(self, _region):
                return None

            def scroll_down(self, ticks):
                observed["scrolls"].append(("down", ticks))

            def capture(self, _region):
                frame = sequence[min(self.index, len(sequence) - 1)]
                self.index += 1
                return frame

            def restore_pointer(self):
                return None

            def close(self):
                return None

        def scroll_up(_controller, ticks):
            observed["scrolls"].append(("up", ticks))

        def estimate_vertical_shift(previous, current, **_kwargs):
            observed["estimate_pairs"].append(
                (int(previous[0, 0, 0]), int(current[0, 0, 0]))
            )
            return Match()

        def stitch_frames(frames, matches):
            observed["stitch_frames"] = [int(frame[0, 0, 0]) for frame in frames]
            observed["stitch_matches"] = len(matches)
            return np.zeros((120, 100, 3), dtype=np.uint8)

        core = SimpleNamespace(
            CaptureError=RuntimeError,
            unique_output_path=lambda path: path,
            default_output_path=lambda: Path("/tmp/scrollshot-up-test.png"),
            X11Controller=Controller,
            scroll_up=scroll_up,
            frames_are_stable=lambda a, b: np.array_equal(a, b),
            estimate_vertical_shift=estimate_vertical_shift,
            stitch_frames=stitch_frames,
            save_png=lambda _path, _image: None,
        )
        args = SimpleNamespace(
            geometry=Region(),
            min_overlap=32,
            output=Path("/tmp/scrollshot-up-test.png"),
            debug_dir=None,
            settle_delay=0.0,
            scroll_ticks=3,
            delay=0.05,
            max_frames=2,
            stable_rounds=2,
            match_threshold=0.68,
            scroll_up=True,
        )

        with mock.patch.object(capture_runtime, "CaptureStopMonitor", StubMonitor), mock.patch.object(
            capture_runtime.time, "sleep", lambda _seconds: None
        ):
            runner = capture_runtime.create_capture_runner(
                core,
                lambda requested, height: min(requested, height - 36),
            )
            _path, frame_count, _height = runner(args)

        self.assertEqual(frame_count, 2)
        self.assertEqual(observed["scrolls"], [("up", 3)])
        self.assertEqual(observed["estimate_pairs"], [(1, 0)])
        self.assertEqual(observed["stitch_frames"], [1, 0])
        self.assertEqual(observed["stitch_matches"], 1)


if __name__ == "__main__":
    unittest.main()
