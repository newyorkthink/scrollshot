#!/usr/bin/env python3
"""Terminal-aware scrolling for ScrollShot without extra input daemons.

For ordinary GUI targets ScrollShot keeps its validated X11 Button4/5 path.
For Kitty/Alacritty windows that are running tmux, this module talks directly
to the already-running tmux server so terminal scrolling does not depend on
how the terminal emulator translates synthetic X11 wheel events.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Callable

TERMINAL_CLASS_MARKERS = ("kitty", "alacritty")
SYSTEM_TMUX_PATHS = (
    Path("/usr/bin/tmux"),
    Path("/bin/tmux"),
    Path("/usr/local/bin/tmux"),
)


@dataclass
class _PaneState:
    pane_id: str
    pane_mode: str
    original_scroll_position: int | None
    alternate_on: bool
    entered_copy_mode: bool = False


class TmuxScrollBridge:
    """Route terminal scrolling through the tmux client behind the X11 window."""

    def __init__(self, core: ModuleType, tmux_executable: str | None = None) -> None:
        self.core = core
        self.tmux_executable = tmux_executable
        self._states: dict[int, _PaneState] = {}

    @staticmethod
    def _host_environment() -> dict[str, str]:
        environment = os.environ.copy()
        for variable in ("LD_LIBRARY_PATH", "LD_LIBRARY_PATH_ORIG", "LD_PRELOAD"):
            environment.pop(variable, None)
        return environment

    def _find_tmux(self) -> str | None:
        if self.tmux_executable:
            return self.tmux_executable
        for candidate in SYSTEM_TMUX_PATHS:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
        return shutil.which("tmux", path=self._host_environment().get("PATH"))

    def _run(self, *arguments: str, allow_failure: bool = False) -> str | None:
        tmux = self._find_tmux()
        if tmux is None:
            return None
        try:
            completed = subprocess.run(
                [tmux, *arguments],
                check=False,
                env=self._host_environment(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=3.0,
            )
        except (OSError, subprocess.SubprocessError):
            if allow_failure:
                return None
            raise self.core.CaptureError("tmux terminal scrolling failed")
        if completed.returncode != 0:
            if allow_failure:
                return None
            detail = (completed.stderr or "").strip()
            message = "tmux terminal scrolling failed"
            if detail:
                message = f"{message}: {detail}"
            raise self.core.CaptureError(message)
        return completed.stdout

    @staticmethod
    def _is_terminal_class(values: tuple[str, ...]) -> bool:
        return any(
            marker in value.casefold()
            for value in values
            for marker in TERMINAL_CLASS_MARKERS
        )

    def _terminal_pid_under_pointer(self, controller) -> int | None:
        try:
            pointer = controller.root.query_pointer()
            window = getattr(pointer, "child", None)
            pid_atom = controller.display.intern_atom("_NET_WM_PID", only_if_exists=True)
        except Exception:
            return None

        visited: set[int] = set()
        while window is not None:
            marker = int(getattr(window, "id", id(window)))
            if marker in visited:
                break
            visited.add(marker)

            try:
                wm_class = window.get_wm_class() or ()
            except Exception:
                wm_class = ()
            classes = tuple(str(value) for value in wm_class if value)
            if classes and self._is_terminal_class(classes):
                try:
                    prop = window.get_full_property(pid_atom, controller.X.AnyPropertyType)
                    if prop is not None and len(prop.value):
                        return int(prop.value[0])
                except Exception:
                    pass

            if window == controller.root:
                break
            try:
                window = window.query_tree().parent
            except Exception:
                break
        return None

    @staticmethod
    def _descendant_ttys(root_pid: int) -> set[str]:
        pending = [int(root_pid)]
        visited: set[int] = set()
        ttys: set[str] = set()
        while pending:
            pid = pending.pop()
            if pid in visited:
                continue
            visited.add(pid)

            try:
                tty = os.readlink(f"/proc/{pid}/fd/0")
            except OSError:
                tty = ""
            if tty.startswith("/dev/pts/"):
                ttys.add(tty)

            try:
                raw_children = Path(f"/proc/{pid}/task/{pid}/children").read_text()
            except OSError:
                continue
            for child in raw_children.split():
                try:
                    pending.append(int(child))
                except ValueError:
                    continue
        return ttys

    def _client_tty_for_terminal(self, terminal_pid: int) -> str | None:
        output = self._run(
            "list-clients",
            "-F",
            "#{client_tty}\t#{client_activity}",
            allow_failure=True,
        )
        if not output:
            return None

        clients: list[tuple[str, int]] = []
        for line in output.splitlines():
            tty, separator, activity_text = line.partition("\t")
            if not separator or not tty:
                continue
            try:
                activity = int(activity_text or "0")
            except ValueError:
                activity = 0
            clients.append((tty, activity))
        if not clients:
            return None

        descendant_ttys = self._descendant_ttys(terminal_pid)
        matched = [item for item in clients if item[0] in descendant_ttys]
        if matched:
            return max(matched, key=lambda item: item[1])[0]

        # A single attached tmux client is unambiguous even if an AppImage
        # launcher obscures the terminal process tree. With multiple clients,
        # do not guess and risk scrolling the wrong terminal.
        if len(clients) == 1:
            return clients[0][0]
        return None

    def _resolve_pane(self, controller) -> _PaneState | None:
        terminal_pid = self._terminal_pid_under_pointer(controller)
        if terminal_pid is None:
            return None
        client_tty = self._client_tty_for_terminal(terminal_pid)
        if client_tty is None:
            return None

        output = self._run(
            "display-message",
            "-c",
            client_tty,
            "-p",
            "#{pane_id}\t#{pane_mode}\t#{scroll_position}\t#{alternate_on}",
            allow_failure=True,
        )
        if not output:
            return None
        line = output.strip().splitlines()[-1]
        parts = line.split("\t")
        if len(parts) != 4 or not parts[0].startswith("%"):
            return None

        pane_id, pane_mode, scroll_text, alternate_text = parts
        try:
            scroll_position = int(scroll_text) if scroll_text else None
        except ValueError:
            scroll_position = None
        return _PaneState(
            pane_id=pane_id,
            pane_mode=pane_mode,
            original_scroll_position=scroll_position,
            alternate_on=alternate_text == "1",
        )

    def _state_for(self, controller) -> _PaneState | None:
        key = id(controller)
        state = self._states.get(key)
        if state is None:
            state = self._resolve_pane(controller)
            if state is not None:
                self._states[key] = state
        return state

    def try_scroll(self, controller, ticks: int, *, upward: bool) -> bool:
        state = self._state_for(controller)
        if state is None:
            return False

        ticks = max(1, int(ticks))
        direction = "scroll-up" if upward else "scroll-down"

        if state.pane_mode == "copy-mode" or state.entered_copy_mode:
            self._run(
                "send-keys",
                "-t",
                state.pane_id,
                "-X",
                "-N",
                str(ticks),
                direction,
            )
            return True

        if state.alternate_on:
            # Full-screen TUIs receive PageUp/PageDown directly from tmux.
            # This bypasses Kitty's XInput2 wheel path entirely; Lazygit,
            # less, editors and similar TUIs commonly handle these keys.
            key = "PageUp" if upward else "PageDown"
            self._run(
                "send-keys",
                "-t",
                state.pane_id,
                "-N",
                str(ticks),
                key,
            )
            return True

        # Plain shell/history: use tmux copy mode instead of terminal-emulator
        # scrollback. -H hides tmux's copy-mode position indicator from capture.
        self._run("copy-mode", "-H", "-t", state.pane_id)
        state.entered_copy_mode = True
        state.pane_mode = "copy-mode"
        self._run(
            "send-keys",
            "-t",
            state.pane_id,
            "-X",
            "-N",
            str(ticks),
            direction,
        )
        return True

    def restore(self, controller) -> None:
        state = self._states.pop(id(controller), None)
        if state is None:
            return
        try:
            if state.entered_copy_mode:
                self._run(
                    "send-keys",
                    "-t",
                    state.pane_id,
                    "-X",
                    "cancel",
                    allow_failure=True,
                )
                return

            if state.pane_mode == "copy-mode" and state.original_scroll_position is not None:
                self._run(
                    "send-keys",
                    "-t",
                    state.pane_id,
                    "-X",
                    "history-bottom",
                    allow_failure=True,
                )
                if state.original_scroll_position > 0:
                    self._run(
                        "send-keys",
                        "-t",
                        state.pane_id,
                        "-X",
                        "-N",
                        str(state.original_scroll_position),
                        "scroll-up",
                        allow_failure=True,
                    )
        except Exception:
            return


def configure_terminal_scrolling(
    core: ModuleType,
    capture_runner: Callable,
) -> Callable:
    """Add tmux terminal scrolling while preserving the stable GUI path."""

    bridge = TmuxScrollBridge(core)
    original_build_parser = core.build_parser
    original_scroll_down = core.X11Controller.scroll_down
    original_controller_close = core.X11Controller.close
    stable_estimator = core.estimate_vertical_shift
    stable_stitcher = core.stitch_frames

    def build_parser_with_scroll_up():
        parser = original_build_parser()
        parser.add_argument(
            "--scroll-up",
            action="store_true",
            help="capture terminal/tmux history upward and stitch top-to-bottom",
        )
        return parser

    def terminal_aware_scroll_down(controller, ticks: int) -> None:
        if bridge.try_scroll(controller, ticks, upward=False):
            return
        original_scroll_down(controller, ticks)

    def close_with_terminal_restore(controller) -> None:
        try:
            bridge.restore(controller)
        finally:
            original_controller_close(controller)

    core.build_parser = build_parser_with_scroll_up
    core.X11Controller.scroll_down = terminal_aware_scroll_down
    core.X11Controller.close = close_with_terminal_restore

    def run_capture(args):
        if not bool(getattr(args, "scroll_up", False)):
            return capture_runner(args)

        previous_scroll_down = core.X11Controller.scroll_down
        previous_estimator = core.estimate_vertical_shift
        previous_stitcher = core.stitch_frames

        def terminal_scroll_up(controller, ticks: int) -> None:
            if bridge.try_scroll(controller, ticks, upward=True):
                return
            raise core.CaptureError(
                "--scroll-up requires the selected Kitty/Alacritty window to use an active tmux client"
            )

        def estimate_upward(previous, current, **kwargs):
            # Acquisition is bottom -> top. Swap the frame pair so the already
            # validated downward matcher still sees top -> bottom motion.
            return stable_estimator(current, previous, **kwargs)

        def stitch_upward(frames, matches):
            # Convert acquisition order bottom -> top back to normal reading
            # order top -> bottom before entering the stable stitching chain.
            return stable_stitcher(
                list(reversed(frames)),
                list(reversed(matches)),
            )

        core.X11Controller.scroll_down = terminal_scroll_up
        core.estimate_vertical_shift = estimate_upward
        core.stitch_frames = stitch_upward
        try:
            return capture_runner(args)
        finally:
            core.X11Controller.scroll_down = previous_scroll_down
            core.estimate_vertical_shift = previous_estimator
            core.stitch_frames = previous_stitcher

    return run_capture
