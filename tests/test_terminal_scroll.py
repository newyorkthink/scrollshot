#!/usr/bin/env python3
from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest import mock

import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import terminal_scroll


class BridgeTests(unittest.TestCase):
    def make_bridge(self):
        core = SimpleNamespace(CaptureError=RuntimeError)
        return terminal_scroll.TmuxScrollBridge(core, tmux_executable="/usr/bin/tmux")

    def test_alternate_screen_uses_page_keys(self):
        bridge = self.make_bridge()
        controller = object()
        state = terminal_scroll._PaneState(
            pane_id="%7",
            pane_mode="",
            original_scroll_position=None,
            alternate_on=True,
        )
        calls = []
        with mock.patch.object(bridge, "_state_for", return_value=state), mock.patch.object(
            bridge, "_run", side_effect=lambda *args, **kwargs: calls.append((args, kwargs)) or ""
        ):
            self.assertTrue(bridge.try_scroll(controller, 3, upward=True))
            self.assertTrue(bridge.try_scroll(controller, 2, upward=False))

        self.assertEqual(
            calls[0][0],
            ("send-keys", "-t", "%7", "-N", "3", "PageUp"),
        )
        self.assertEqual(
            calls[1][0],
            ("send-keys", "-t", "%7", "-N", "2", "PageDown"),
        )

    def test_plain_shell_uses_copy_mode_and_restores_it(self):
        bridge = self.make_bridge()
        controller = object()
        state = terminal_scroll._PaneState(
            pane_id="%3",
            pane_mode="",
            original_scroll_position=None,
            alternate_on=False,
        )
        calls = []
        with mock.patch.object(bridge, "_resolve_pane", return_value=state), mock.patch.object(
            bridge, "_run", side_effect=lambda *args, **kwargs: calls.append((args, kwargs)) or ""
        ):
            self.assertTrue(bridge.try_scroll(controller, 4, upward=True))
            bridge.restore(controller)

        self.assertEqual(calls[0][0], ("copy-mode", "-H", "-t", "%3"))
        self.assertEqual(
            calls[1][0],
            ("send-keys", "-t", "%3", "-X", "-N", "4", "scroll-up"),
        )
        self.assertEqual(calls[2][0], ("send-keys", "-t", "%3", "-X", "cancel"))

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
            bridge, "_run", side_effect=lambda *args, **kwargs: calls.append((args, kwargs)) or ""
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

    def test_multiple_tmux_clients_without_process_match_are_not_guessed(self):
        bridge = self.make_bridge()
        clients = "/dev/pts/1\t100\n/dev/pts/2\t200\n"
        with mock.patch.object(bridge, "_run", return_value=clients), mock.patch.object(
            bridge, "_descendant_ttys", return_value={"/dev/pts/8"}
        ):
            self.assertIsNone(bridge._client_tty_for_terminal(1234))

    def test_matching_terminal_process_tty_selects_correct_client(self):
        bridge = self.make_bridge()
        clients = "/dev/pts/1\t100\n/dev/pts/2\t200\n"
        with mock.patch.object(bridge, "_run", return_value=clients), mock.patch.object(
            bridge, "_descendant_ttys", return_value={"/dev/pts/1"}
        ):
            self.assertEqual(bridge._client_tty_for_terminal(1234), "/dev/pts/1")


class ConfigureTests(unittest.TestCase):
    def test_scroll_up_reuses_stable_matcher_and_reverses_stitch_order(self):
        import argparse

        events = {"estimator": [], "stitch": [], "scroll": []}

        class Controller:
            def scroll_down(self, ticks):
                events["scroll"].append(("original", ticks))

            def close(self):
                events["scroll"].append(("close", 0))

        def build_parser():
            return argparse.ArgumentParser(add_help=False)

        def estimator(previous, current, **_kwargs):
            events["estimator"].append((previous, current))
            return "match"

        def stitcher(frames, matches):
            events["stitch"].append((list(frames), list(matches)))
            return "stitched"

        core = SimpleNamespace(
            CaptureError=RuntimeError,
            build_parser=build_parser,
            X11Controller=Controller,
            estimate_vertical_shift=estimator,
            stitch_frames=stitcher,
        )

        def capture_runner(_args):
            controller = core.X11Controller()
            try:
                controller.scroll_down(2)
                core.estimate_vertical_shift("bottom", "top")
                core.stitch_frames(["bottom", "top"], ["match"])
                return "ok"
            finally:
                controller.close()

        with mock.patch.object(
            terminal_scroll.TmuxScrollBridge,
            "try_scroll",
            side_effect=lambda _controller, ticks, upward: events["scroll"].append(
                ("up" if upward else "down", ticks)
            ) or True,
        ), mock.patch.object(
            terminal_scroll.TmuxScrollBridge,
            "restore",
            return_value=None,
        ):
            wrapped = terminal_scroll.configure_terminal_scrolling(core, capture_runner)
            parsed = core.build_parser().parse_args(["--scroll-up"])
            self.assertTrue(parsed.scroll_up)
            self.assertEqual(wrapped(parsed), "ok")

        self.assertIn(("up", 2), events["scroll"])
        self.assertEqual(events["estimator"], [("top", "bottom")])
        self.assertEqual(events["stitch"], [(["top", "bottom"], ["match"])])
        self.assertNotIn(("original", 2), events["scroll"])

    def test_normal_capture_falls_back_to_original_x11_scroll(self):
        import argparse

        events = []

        class Controller:
            def scroll_down(self, ticks):
                events.append(("original", ticks))

            def close(self):
                return None

        core = SimpleNamespace(
            CaptureError=RuntimeError,
            build_parser=lambda: argparse.ArgumentParser(add_help=False),
            X11Controller=Controller,
            estimate_vertical_shift=lambda a, b, **kwargs: None,
            stitch_frames=lambda frames, matches: None,
        )

        def capture_runner(_args):
            controller = core.X11Controller()
            try:
                controller.scroll_down(3)
                return "ok"
            finally:
                controller.close()

        with mock.patch.object(
            terminal_scroll.TmuxScrollBridge,
            "try_scroll",
            return_value=False,
        ), mock.patch.object(
            terminal_scroll.TmuxScrollBridge,
            "restore",
            return_value=None,
        ):
            wrapped = terminal_scroll.configure_terminal_scrolling(core, capture_runner)
            args = core.build_parser().parse_args([])
            self.assertEqual(wrapped(args), "ok")

        self.assertEqual(events, [("original", 3)])


if __name__ == "__main__":
    unittest.main()
