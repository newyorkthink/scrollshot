#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import terminal_scroll


class BridgeTests(unittest.TestCase):
    def make_bridge(self):
        core = SimpleNamespace(CaptureError=RuntimeError)
        return terminal_scroll.TmuxScrollBridge(
            core, tmux_executable="/usr/bin/tmux"
        )

    def test_kitty_existing_copy_mode_scrolls_down_through_tmux(self):
        bridge = self.make_bridge()
        controller = object()
        state = terminal_scroll._PaneState(
            pane_id="%4",
            pane_mode="copy-mode",
            original_scroll_position=45,
            alternate_on=False,
        )
        calls = []
        with mock.patch.object(
            bridge,
            "_terminal_pid_under_pointer",
            return_value=1234,
        ) as pid_lookup, mock.patch.object(
            bridge,
            "_pane_state_for_pid",
            return_value=state,
        ), mock.patch.object(
            bridge,
            "_run",
            side_effect=lambda *args, **kwargs: calls.append((args, kwargs)) or "",
        ):
            self.assertTrue(
                bridge.scroll_existing_kitty_copy_mode(controller, 3)
            )

        pid_lookup.assert_called_once_with(
            controller, terminal_scroll.KITTY_CLASS_MARKERS
        )
        self.assertEqual(
            calls[0][0],
            ("send-keys", "-t", "%4", "-X", "-N", "3", "scroll-down"),
        )

    def test_kitty_without_copy_mode_falls_back(self):
        bridge = self.make_bridge()
        controller = object()
        state = terminal_scroll._PaneState(
            pane_id="%4",
            pane_mode="",
            original_scroll_position=None,
            alternate_on=False,
        )
        with mock.patch.object(
            bridge,
            "_terminal_pid_under_pointer",
            return_value=1234,
        ), mock.patch.object(
            bridge,
            "_pane_state_for_pid",
            return_value=state,
        ), mock.patch.object(
            bridge,
            "_run",
        ) as run:
            self.assertFalse(
                bridge.scroll_existing_kitty_copy_mode(controller, 3)
            )
        run.assert_not_called()

    def test_prepare_copy_mode_before_scroll(self):
        bridge = self.make_bridge()
        controller = object()
        state = terminal_scroll._PaneState(
            pane_id="%7",
            pane_mode="",
            original_scroll_position=None,
            alternate_on=False,
        )
        calls = []
        with mock.patch.object(
            bridge, "_state_for", return_value=state
        ), mock.patch.object(
            bridge,
            "_run",
            side_effect=lambda *args, **kwargs: calls.append((args, kwargs)) or "",
        ):
            self.assertTrue(bridge.prepare_copy_mode(controller))
            self.assertTrue(
                bridge.scroll_copy_mode(controller, 3, upward=True)
            )

        self.assertEqual(calls[0][0], ("copy-mode", "-H", "-t", "%7"))
        self.assertEqual(
            calls[1][0],
            ("send-keys", "-t", "%7", "-X", "-N", "3", "scroll-up"),
        )

    def test_prepare_existing_copy_mode_does_not_reenter(self):
        bridge = self.make_bridge()
        controller = object()
        state = terminal_scroll._PaneState(
            pane_id="%9",
            pane_mode="copy-mode",
            original_scroll_position=17,
            alternate_on=False,
        )
        calls = []
        with mock.patch.object(
            bridge, "_state_for", return_value=state
        ), mock.patch.object(
            bridge,
            "_run",
            side_effect=lambda *args, **kwargs: calls.append((args, kwargs)) or "",
        ):
            self.assertTrue(bridge.prepare_copy_mode(controller))
        self.assertEqual(calls, [])

    def test_entered_copy_mode_is_cancelled_on_restore(self):
        bridge = self.make_bridge()
        controller = object()
        state = terminal_scroll._PaneState(
            pane_id="%3",
            pane_mode="copy-mode",
            original_scroll_position=None,
            alternate_on=False,
            entered_copy_mode=True,
        )
        bridge._states[id(controller)] = state
        calls = []
        with mock.patch.object(
            bridge,
            "_run",
            side_effect=lambda *args, **kwargs: calls.append((args, kwargs)) or "",
        ):
            bridge.restore(controller)

        self.assertEqual(
            calls[0][0],
            ("send-keys", "-t", "%3", "-X", "cancel"),
        )

    def test_existing_copy_mode_position_is_restored(self):
        bridge = self.make_bridge()
        controller = object()
        state = terminal_scroll._PaneState(
            pane_id="%9",
            pane_mode="copy-mode",
            original_scroll_position=17,
            alternate_on=False,
        )
        bridge._states[id(controller)] = state
        calls = []
        with mock.patch.object(
            bridge,
            "_run",
            side_effect=lambda *args, **kwargs: calls.append((args, kwargs)) or "",
        ):
            bridge.restore(controller)

        self.assertEqual(
            calls[0][0],
            ("send-keys", "-t", "%9", "-X", "history-bottom"),
        )
        self.assertEqual(
            calls[1][0],
            ("send-keys", "-t", "%9", "-X", "-N", "17", "scroll-up"),
        )


class ConfigureTests(unittest.TestCase):
    def make_core(self, events):
        class Controller:
            def move_to_region(self, region):
                events.append(("move", region))

            def scroll_down(self, ticks):
                events.append(("original-down", ticks))

            def close(self):
                events.append(("original-close", 0))

        return SimpleNamespace(
            CaptureError=RuntimeError,
            build_parser=lambda: argparse.ArgumentParser(add_help=False),
            X11Controller=Controller,
            estimate_vertical_shift=lambda a, b, **kwargs: (
                events.append(("estimate", a, b)) or "match"
            ),
            stitch_frames=lambda frames, matches: (
                events.append(("stitch", list(frames), list(matches)))
                or "stitched"
            ),
        )

    def test_normal_alacritty_or_gui_capture_keeps_original_down_path(self):
        events = []
        core = self.make_core(events)

        def capture_runner(_args):
            controller = core.X11Controller()
            try:
                controller.move_to_region("region")
                controller.scroll_down(3)
                return "ok"
            finally:
                controller.close()

        with mock.patch.object(
            terminal_scroll.TmuxScrollBridge,
            "scroll_existing_kitty_copy_mode",
            return_value=False,
        ):
            wrapped = terminal_scroll.configure_terminal_scrolling(
                core, capture_runner
            )
            args = core.build_parser().parse_args([])
            self.assertEqual(wrapped(args), "ok")

        self.assertEqual(
            events,
            [("move", "region"), ("original-down", 3), ("original-close", 0)],
        )

    def test_normal_kitty_copy_mode_uses_tmux_and_skips_x11_wheel(self):
        events = []
        core = self.make_core(events)

        def capture_runner(_args):
            controller = core.X11Controller()
            try:
                controller.move_to_region("region")
                controller.scroll_down(3)
                return "ok"
            finally:
                controller.close()

        with mock.patch.object(
            terminal_scroll.TmuxScrollBridge,
            "scroll_existing_kitty_copy_mode",
            side_effect=lambda _controller, ticks: (
                events.append(("kitty-copy-down", ticks)) or True
            ),
        ):
            wrapped = terminal_scroll.configure_terminal_scrolling(
                core, capture_runner
            )
            args = core.build_parser().parse_args([])
            self.assertEqual(wrapped(args), "ok")

        self.assertEqual(
            events,
            [
                ("move", "region"),
                ("kitty-copy-down", 3),
                ("original-close", 0),
            ],
        )

    def test_scroll_up_prepares_before_first_capture_and_reverses_match(self):
        events = []
        core = self.make_core(events)

        def capture_runner(_args):
            controller = core.X11Controller()
            try:
                controller.move_to_region("region")
                events.append(("capture-first", 0))
                controller.scroll_down(2)
                core.estimate_vertical_shift("bottom", "top")
                core.stitch_frames(["bottom", "top"], ["match"])
                return "ok"
            finally:
                controller.close()

        with mock.patch.object(
            terminal_scroll.TmuxScrollBridge,
            "prepare_copy_mode",
            side_effect=lambda _controller: events.append(("prepare", 0)) or True,
        ), mock.patch.object(
            terminal_scroll.TmuxScrollBridge,
            "scroll_copy_mode",
            side_effect=lambda _controller, ticks, upward: (
                events.append(("up", ticks, upward)) or True
            ),
        ), mock.patch.object(
            terminal_scroll.TmuxScrollBridge,
            "restore",
            side_effect=lambda _controller: events.append(("restore", 0)),
        ), mock.patch.object(
            terminal_scroll.TmuxScrollBridge,
            "scroll_existing_kitty_copy_mode",
            return_value=False,
        ):
            wrapped = terminal_scroll.configure_terminal_scrolling(
                core, capture_runner
            )
            args = core.build_parser().parse_args(["--scroll-up"])
            self.assertEqual(wrapped(args), "ok")

        self.assertLess(
            events.index(("prepare", 0)),
            events.index(("capture-first", 0)),
        )
        self.assertIn(("up", 2, True), events)
        self.assertIn(("estimate", "top", "bottom"), events)
        self.assertIn(("stitch", ["top", "bottom"], ["match"]), events)
        self.assertLess(
            events.index(("restore", 0)),
            events.index(("original-close", 0)),
        )


if __name__ == "__main__":
    unittest.main()
