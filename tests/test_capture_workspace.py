#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
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


class CaptureWorkspaceTests(unittest.TestCase):
    def test_workspace_change_stops_before_foreign_frame_is_added(self) -> None:
        class Controller:
            capture_count = 0

            def move_to_region(self, _region):
                return None

            def scroll_down(self, _ticks):
                return None

            def capture(self, _region):
                type(self).capture_count += 1
                return np.full((100, 100, 3), type(self).capture_count, dtype=np.uint8)

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
            estimate_vertical_shift=lambda _a, _b, **_kwargs: Match(),
            stitch_frames=lambda frames, matches: saved.update(
                frames=len(frames), matches=len(matches)
            ) or np.zeros((100, 100, 3), dtype=np.uint8),
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

        desktops = iter([2, 2, 2, 2, 2, 3])

        def current_desktop():
            try:
                return next(desktops)
            except StopIteration:
                return 3

        with mock.patch.object(capture_runtime, "CaptureStopMonitor", StubMonitor), mock.patch.object(
            capture_runtime.time, "sleep", lambda _seconds: None
        ), mock.patch.object(capture_runtime, "read_current_desktop", current_desktop):
            runner = capture_runtime.create_capture_runner(
                core,
                lambda requested, height: min(requested, height - 36),
            )
            _path, frame_count, _height = runner(args)

        self.assertEqual(frame_count, 1)
        self.assertEqual(Controller.capture_count, 2)
        self.assertEqual(saved["frames"], 1)
        self.assertEqual(saved["matches"], 0)

    def test_missing_ewmh_workspace_support_does_not_stop_capture(self) -> None:
        class Controller:
            capture_count = 0

            def move_to_region(self, _region):
                return None

            def scroll_down(self, _ticks):
                return None

            def capture(self, _region):
                type(self).capture_count += 1
                return np.full((100, 100, 3), type(self).capture_count, dtype=np.uint8)

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
            frames_are_stable=lambda _a, _b: False,
            estimate_vertical_shift=lambda _a, _b, **_kwargs: Match(),
            stitch_frames=lambda frames, matches: saved.update(
                frames=len(frames), matches=len(matches)
            ) or np.zeros((100, 100, 3), dtype=np.uint8),
            save_png=lambda _path, _image: None,
        )
        args = SimpleNamespace(
            geometry=Region(),
            min_overlap=32,
            output=Path("/tmp/scrollshot-test.png"),
            debug_dir=None,
            settle_delay=0.0,
            scroll_ticks=3,
            delay=0.0,
            max_frames=3,
            stable_rounds=2,
            match_threshold=0.68,
        )

        with mock.patch.object(capture_runtime, "CaptureStopMonitor", StubMonitor), mock.patch.object(
            capture_runtime.time, "sleep", lambda _seconds: None
        ), mock.patch.object(capture_runtime, "read_current_desktop", lambda: None):
            runner = capture_runtime.create_capture_runner(
                core,
                lambda requested, height: min(requested, height - 36),
            )
            _path, frame_count, _height = runner(args)

        self.assertEqual(frame_count, 3)
        self.assertEqual(saved["frames"], 3)
        self.assertEqual(saved["matches"], 2)


if __name__ == "__main__":
    unittest.main()
