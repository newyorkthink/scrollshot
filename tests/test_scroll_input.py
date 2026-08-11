#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import scrollshot_app


class ScrollInputTests(unittest.TestCase):
    def test_detects_kitty_from_pointer_window_class(self) -> None:
        class Root:
            def query_pointer(self):
                return SimpleNamespace(child=client)

        class Client:
            def get_wm_class(self):
                return ("kitty", "kitty")

            def query_tree(self):
                return SimpleNamespace(parent=root)

        root = Root()
        client = Client()
        controller = SimpleNamespace(root=root)

        self.assertTrue(scrollshot_app._is_kitty_target(controller))

    def test_non_kitty_scroll_down_preserves_original_controller_path(self) -> None:
        controller = object()

        with mock.patch.object(
            scrollshot_app, "_is_kitty_target", return_value=False
        ), mock.patch.object(scrollshot_app, "_core_scroll_down") as original:
            scrollshot_app._scroll_down(controller, 3)

        original.assert_called_once_with(controller, 3)

    def test_non_kitty_scroll_up_uses_button4_without_keyboard_injection(self) -> None:
        calls = []

        class X:
            ButtonPress = 4
            ButtonRelease = 5

        class XTest:
            @staticmethod
            def fake_input(display, event_type, detail):
                calls.append((display, event_type, detail))

        class Display:
            def __init__(self):
                self.sync_calls = 0

            def sync(self):
                self.sync_calls += 1

        display = Display()
        controller = SimpleNamespace(X=X, xtest=XTest, display=display)

        with mock.patch.object(
            scrollshot_app, "_is_kitty_target", return_value=False
        ):
            scrollshot_app._scroll_up(controller, 2)

        self.assertEqual(
            calls,
            [
                (display, X.ButtonPress, 4),
                (display, X.ButtonRelease, 4),
                (display, X.ButtonPress, 4),
                (display, X.ButtonRelease, 4),
            ],
        )
        self.assertEqual(display.sync_calls, 1)

    def test_kitty_scroll_up_uses_ydotool_wheel(self) -> None:
        controller = object()

        with mock.patch.object(
            scrollshot_app, "_is_kitty_target", return_value=True
        ), mock.patch.object(scrollshot_app, "_ydotool_wheel") as wheel:
            scrollshot_app._scroll_up(controller, 3)

        wheel.assert_called_once_with(3, upward=True)

    def test_kitty_scroll_down_uses_ydotool_wheel(self) -> None:
        controller = object()

        with mock.patch.object(
            scrollshot_app, "_is_kitty_target", return_value=True
        ), mock.patch.object(scrollshot_app, "_ydotool_wheel") as wheel, mock.patch.object(
            scrollshot_app, "_core_scroll_down"
        ) as original:
            scrollshot_app._scroll_down(controller, 3)

        wheel.assert_called_once_with(3, upward=False)
        original.assert_not_called()

    def test_ydotool_wheel_uses_rel_wheel_signs(self) -> None:
        completed = SimpleNamespace(returncode=0, stderr="")

        with mock.patch.object(
            scrollshot_app, "_find_ydotool", return_value="/usr/bin/ydotool"
        ), mock.patch.object(
            scrollshot_app, "_host_input_environment", return_value={"PATH": "/usr/bin"}
        ), mock.patch.object(
            scrollshot_app.subprocess, "run", return_value=completed
        ) as run:
            scrollshot_app._ydotool_wheel(3, upward=True)
            scrollshot_app._ydotool_wheel(3, upward=False)

        self.assertEqual(run.call_count, 2)
        self.assertEqual(
            run.call_args_list[0].args[0],
            [
                "/usr/bin/ydotool",
                "mousemove",
                "--wheel",
                "-x",
                "0",
                "-y",
                "3",
            ],
        )
        self.assertEqual(
            run.call_args_list[1].args[0],
            [
                "/usr/bin/ydotool",
                "mousemove",
                "--wheel",
                "-x",
                "0",
                "-y",
                "-3",
            ],
        )

    def test_ydotool_failure_is_not_silently_ignored(self) -> None:
        completed = SimpleNamespace(returncode=1, stderr="socket unavailable")

        with mock.patch.object(
            scrollshot_app, "_find_ydotool", return_value="/usr/bin/ydotool"
        ), mock.patch.object(
            scrollshot_app, "_host_input_environment", return_value={"PATH": "/usr/bin"}
        ), mock.patch.object(
            scrollshot_app.subprocess, "run", return_value=completed
        ):
            with self.assertRaises(scrollshot_app.core.CaptureError):
                scrollshot_app._ydotool_wheel(1, upward=True)


if __name__ == "__main__":
    unittest.main()
