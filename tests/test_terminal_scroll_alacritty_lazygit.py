#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import terminal_scroll
import terminal_scroll_lazygit


class AlacrittyLazygitUpTests(unittest.TestCase):
    def make_bridge(self):
        core = SimpleNamespace(CaptureError=RuntimeError)
        return terminal_scroll_lazygit._TerminalLazygitBridge(
            core,
            tmux_executable="/usr/bin/tmux",
        )

    def test_lazygit_lookup_accepts_alacritty_and_kitty_markers(self):
        bridge = self.make_bridge()
        controller = object()
        state = terminal_scroll._PaneState(
            pane_id="%12",
            pane_mode="",
            original_scroll_position=None,
            alternate_on=True,
        )

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
            return_value="lazygit\n",
        ):
            self.assertIs(bridge._kitty_lazygit_state(controller), state)

        pid_lookup.assert_called_once_with(
            controller,
            terminal_scroll.TERMINAL_CLASS_MARKERS,
        )

    def test_upward_lazygit_sends_K_without_copy_mode(self):
        bridge = self.make_bridge()
        controller = object()
        state = terminal_scroll._PaneState(
            pane_id="%13",
            pane_mode="",
            original_scroll_position=None,
            alternate_on=True,
        )
        calls = []

        with mock.patch.object(
            bridge,
            "_kitty_lazygit_state",
            return_value=state,
        ), mock.patch.object(
            bridge,
            "_run",
            side_effect=lambda *args, **kwargs: calls.append((args, kwargs)) or "",
        ):
            self.assertTrue(
                bridge.scroll_kitty_lazygit(controller, 2, upward=True)
            )

        self.assertEqual(
            calls[0][0],
            ("send-keys", "-t", "%13", "-N", "2", "K"),
        )

    def test_configure_uses_extended_bridge_but_restores_module_class(self):
        original_bridge = terminal_scroll.TmuxScrollBridge
        captured = {}

        def fake_configure(core, capture_runner):
            captured["bridge_class"] = terminal_scroll.TmuxScrollBridge
            return capture_runner

        with mock.patch.object(
            terminal_scroll,
            "configure_terminal_scrolling",
            side_effect=fake_configure,
        ):
            runner = lambda args: args
            self.assertIs(
                terminal_scroll_lazygit.configure_terminal_scrolling(
                    SimpleNamespace(),
                    runner,
                ),
                runner,
            )

        self.assertIs(
            captured["bridge_class"],
            terminal_scroll_lazygit._TerminalLazygitBridge,
        )
        self.assertIs(terminal_scroll.TmuxScrollBridge, original_bridge)


if __name__ == "__main__":
    unittest.main()
