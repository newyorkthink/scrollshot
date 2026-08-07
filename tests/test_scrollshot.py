#!/usr/bin/env python3
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


def build_document(width: int = 640, height: int = 2600) -> np.ndarray:
    rng = np.random.default_rng(20260807)
    image = np.full((height, width, 3), 245, dtype=np.uint8)
    for y in range(25, height, 55):
        shade = int(rng.integers(20, 190))
        cv2.putText(
            image,
            f"line {y:04d}",
            (24, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (shade, 30, 210 - shade // 2),
            2,
            cv2.LINE_AA,
        )
        cv2.line(image, (20, y + 12), (width - 20, y + 12), (180, 180, 180), 1)
    for _ in range(100):
        x1 = int(rng.integers(10, width - 100))
        y1 = int(rng.integers(10, height - 80))
        x2 = min(width - 1, x1 + int(rng.integers(20, 100)))
        y2 = min(height - 1, y1 + int(rng.integers(10, 70)))
        color = tuple(int(value) for value in rng.integers(20, 235, size=3))
        cv2.rectangle(image, (x1, y1), (x2, y2), color, -1)
    return image


def build_fixed_viewport(
    document: np.ndarray,
    start: int,
    *,
    viewport_height: int = 720,
    header_height: int = 78,
    footer_height: int = 64,
) -> np.ndarray:
    width = document.shape[1]
    content_height = viewport_height - header_height - footer_height
    frame = np.full((viewport_height, width, 3), 248, dtype=np.uint8)
    frame[:header_height] = (35, 45, 55)
    cv2.putText(
        frame,
        "Fixed header",
        (24, 48),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        (240, 240, 240),
        2,
        cv2.LINE_AA,
    )
    frame[header_height : header_height + content_height] = document[
        start : start + content_height
    ]
    frame[-footer_height:] = (215, 220, 225)
    cv2.putText(
        frame,
        "Fixed footer",
        (24, viewport_height - 22),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (30, 30, 30),
        2,
        cv2.LINE_AA,
    )
    return frame


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
    def test_estimate_vertical_shift_full_frame(self) -> None:
        document = build_document()
        viewport_height = 720
        shift = 173
        previous = document[0:viewport_height]
        current = document[shift : shift + viewport_height]
        match = scrollshot.estimate_vertical_shift(previous, current, min_overlap=100)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertLessEqual(abs(match.shift - shift), 2)
        self.assertLessEqual(match.content_top, 8)
        self.assertGreaterEqual(match.content_bottom, viewport_height - 8)

    def test_estimate_partial_final_scroll(self) -> None:
        document = build_document()
        viewport_height = 680
        previous_start = 1000
        shift = 47
        previous = document[previous_start : previous_start + viewport_height]
        current = document[previous_start + shift : previous_start + shift + viewport_height]
        match = scrollshot.estimate_vertical_shift(previous, current, min_overlap=100)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertLessEqual(abs(match.shift - shift), 2)

    def test_fixed_header_and_footer_are_detected(self) -> None:
        document = build_document(width=520, height=2200)
        shift = 190
        previous = build_fixed_viewport(document, 0)
        current = build_fixed_viewport(document, shift)
        match = scrollshot.estimate_vertical_shift(previous, current, min_overlap=100)
        self.assertIsNotNone(match)
        assert match is not None
        self.assertLessEqual(abs(match.shift - shift), 2)
        self.assertGreaterEqual(match.content_top, 65)
        self.assertLessEqual(match.content_top, 90)
        self.assertGreaterEqual(match.content_bottom, 640)
        self.assertLessEqual(match.content_bottom, 670)

    def test_small_local_change_is_not_scrolling(self) -> None:
        previous = np.full((600, 700, 3), 20, dtype=np.uint8)
        current = previous.copy()
        cv2.putText(
            current,
            "new terminal prompt",
            (20, 570),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (230, 230, 230),
            2,
            cv2.LINE_AA,
        )
        self.assertIsNone(scrollshot.estimate_vertical_shift(previous, current))

    def test_static_frame_is_stable(self) -> None:
        frame = build_document(width=500, height=500)
        animated = frame.copy()
        animated[100:108, 100:108] = 0
        self.assertTrue(scrollshot.frames_are_stable(frame, animated))

    def test_repetitive_layout_uses_full_overlap(self) -> None:
        document = np.full((1800, 420, 3), 255, dtype=np.uint8)
        for index, y in enumerate(range(0, 1800, 27)):
            background = 255 if index % 2 == 0 else 232
            cv2.rectangle(document, (0, y), (419, min(y + 26, 1799)), (background,) * 3, -1)
            cv2.putText(
                document,
                f"line {index:03d}",
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


class StitchingTests(unittest.TestCase):
    def test_stitch_full_frame(self) -> None:
        document = build_document(width=500, height=1300)
        viewport_height = 600
        shifts = [210, 185]
        frame1 = document[0:viewport_height]
        frame2 = document[shifts[0] : shifts[0] + viewport_height]
        frame3 = document[sum(shifts) : sum(shifts) + viewport_height]
        stitched = scrollshot.stitch_frames([frame1, frame2, frame3], shifts)
        expected = document[: viewport_height + sum(shifts)]
        np.testing.assert_array_equal(stitched, expected)

    def test_stitch_fixed_bands_once(self) -> None:
        document = build_document(width=520, height=2400)
        shifts = [180, 170, 95]
        starts = [0, shifts[0], sum(shifts[:2]), sum(shifts)]
        frames = [build_fixed_viewport(document, start) for start in starts]
        matches = []
        for previous, current in zip(frames, frames[1:]):
            match = scrollshot.estimate_vertical_shift(previous, current, min_overlap=100)
            self.assertIsNotNone(match)
            assert match is not None
            matches.append(match)
        stitched = scrollshot.stitch_frames(frames, matches)

        top = max(match.content_top for match in matches)
        bottom = min(match.content_bottom for match in matches)
        expected = np.concatenate(
            [
                frames[0][:top],
                frames[0][top:bottom],
                frames[1][bottom - shifts[0] : bottom],
                frames[2][bottom - shifts[1] : bottom],
                frames[3][bottom - shifts[2] : bottom],
                frames[-1][bottom:],
            ],
            axis=0,
        )
        np.testing.assert_array_equal(stitched, expected)
        self.assertEqual(stitched.shape[0], 720 + sum(shifts))


class CaptureLoopTests(unittest.TestCase):
    def test_capture_loop_is_silent_and_stops_on_static_target(self) -> None:
        import contextlib
        import io
        from types import SimpleNamespace

        frame = np.full((240, 320, 3), 40, dtype=np.uint8)

        class FakeController:
            instance = None

            def __init__(self) -> None:
                self.scroll_calls = 0
                FakeController.instance = self

            def move_to_region(self, _region) -> None:
                return None

            def scroll_down(self, _ticks: int) -> None:
                self.scroll_calls += 1

            def capture(self, _region) -> np.ndarray:
                return frame.copy()

            def restore_pointer(self) -> None:
                return None

            def close(self) -> None:
                return None

        original_controller = scrollshot.X11Controller
        original_sleep = scrollshot.time.sleep
        original_save = scrollshot.save_png
        scrollshot.X11Controller = FakeController
        scrollshot.time.sleep = lambda _seconds: None
        scrollshot.save_png = lambda _path, _image: None
        try:
            args = SimpleNamespace(
                geometry=scrollshot.Region(0, 0, 320, 240),
                min_overlap=80,
                output=Path("capture.png"),
                debug_dir=None,
                settle_delay=0.0,
                max_frames=20,
                scroll_ticks=3,
                delay=0.0,
                stable_rounds=2,
                match_threshold=0.68,
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                _path, frame_count, height = scrollshot.run_capture(args)
            self.assertEqual(output.getvalue(), "")
            self.assertEqual(frame_count, 1)
            self.assertEqual(height, 240)
            assert FakeController.instance is not None
            self.assertEqual(FakeController.instance.scroll_calls, 2)
        finally:
            scrollshot.X11Controller = original_controller
            scrollshot.time.sleep = original_sleep
            scrollshot.save_png = original_save


if __name__ == "__main__":
    unittest.main()
