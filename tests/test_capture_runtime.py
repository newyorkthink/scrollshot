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


if __name__ == "__main__":
    unittest.main()
