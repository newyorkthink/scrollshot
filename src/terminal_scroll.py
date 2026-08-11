#!/usr/bin/env python3
"""Terminal scrolling helpers for ScrollShot through an already-running tmux client.

Alacritty and ordinary GUI downward capture keep the validated X11 path.
Kitty is routed through tmux when the selected pane is already in tmux copy
mode, or when Kitty is running Lazygit in the alternate screen. This avoids
Kitty's ignored synthetic X11 wheel while preserving small-step overlap for
stitching. Upward terminal capture prepares copy mode before the first frame is
captured.
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
KITTY_CLASS_MARKERS = ("kitty",)
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
    """Resolve the tmux pane below the pointer and control its copy mode."""

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
    def _is_terminal_class(
        values: tuple[str, ...],
        markers: tuple[str, ...] = TERMINAL_CLASS_MARKERS,
    ) -> bool:
        return any(
            marker in value.casefold()
            for value in values
            for marker in markers
        )

    def _terminal_pid_under_pointer(
        self,
        controller,
        markers: tuple[str, ...] = TERMINAL_CLASS_MARKERS,
    ) -> int | None:
        """Find the deepest requested terminal client below the pointer.

        i3 reparents clients into frame windows, so descend through the window
        below the pointer before inspecting WM_CLASS and _NET_WM_PID.
        """

        try:
            pid_atom = controller.display.intern_atom(
                "_NET_WM_PID", only_if_exists=True
            )
        except Exception:
            return None

        chain = []
        window = controller.root
        visited: set[int] = set()
        while window is not None:
            marker = int(getattr(window, "id", id(window)))
            if marker in visited:
                break
            visited.add(marker)

            try:
                pointer = window.query_pointer()
                child = getattr(pointer, "child", None)
            except Exception:
                break

            if child is None or child == getattr(controller.X, "NONE", 0):
                break
            chain.append(child)
            window = child

        for window in reversed(chain):
            try:
                wm_class = window.get_wm_class() or ()
            except Exception:
                wm_class = ()
            classes = tuple(str(value) for value in wm_class if value)
            if not classes or not self._is_terminal_class(classes, markers):
                continue

            try:
                prop = window.get_full_property(
                    pid_atom, controller.X.AnyPropertyType
                )
                if prop is not None and len(prop.value):
                    return int(prop.value[0])
            except Exception:
                continue
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
                raw_children = Path(
                    f"/proc/{pid}/task/{pid}/children"
                ).read_text()
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

        if len(clients) == 1:
            return clients[0][0]
        return None

    def _pane_state_for_pid(self, terminal_pid: int) -> _PaneState | None:
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

    def _resolve_pane(self, controller) -> _PaneState | None:
        terminal_pid = self._terminal_pid_under_pointer(controller)
        if terminal_pid is None:
            return None
        return self._pane_state_for_pid(terminal_pid)

    def _state_for(self, controller) -> _PaneState | None:
        key = id(controller)
        state = self._states.get(key)
        if state is None:
            state = self._resolve_pane(controller)
            if state is not None:
                self._states[key] = state
        return state

    def scroll_existing_kitty_copy_mode(self, controller, ticks: int) -> bool:
        """Handle Kitty down-scroll through tmux for copy mode and Lazygit."""

        terminal_pid = self._terminal_pid_under_pointer(
            controller, KITTY_CLASS_MARKERS
        )
        if terminal_pid is None:
            return False
        state = self._pane_state_for_pid(terminal_pid)
        if state is None:
            return False

        ticks = max(1, int(ticks))

        if state.pane_mode == "copy-mode":
            self._run(
                "send-keys",
                "-t",
                state.pane_id,
                "-X",
                "-N",
                str(ticks),
                "scroll-down",
            )
            return True

        # Kitty ignores ScrollShot's synthetic X11 wheel in Lazygit. Lazygit
        # maps uppercase J to its global small-step "scroll down main" action,
        # which keeps enough overlap between frames for ScrollShot stitching.
        if not state.alternate_on:
            return False
        command = self._run(
            "display-message",
            "-t",
            state.pane_id,
            "-p",
            "#{pane_current_command}",
            allow_failure=True,
        )
        if not command or Path(command.strip()).name.casefold() != "lazygit":
            return False

        self._run(
            "send-keys",
            "-t",
            state.pane_id,
            "-N",
            str(ticks),
            "J",
        )
        return True

    def prepare_copy_mode(self, controller) -> bool:
        """Enter copy mode without scrolling, before the first capture frame."""

        state = self._state_for(controller)
        if state is None:
            return False
        if state.pane_mode == "copy-mode":
            return True

        self._run("copy-mode", "-H", "-t", state.pane_id)
        state.entered_copy_mode = True
        state.pane_mode = "copy-mode"
        return True

    def scroll_copy_mode(self, controller, ticks: int, *, upward: bool) -> bool:
        """Scroll an already-prepared copy-mode pane by a small repeat count."""

        state = self._state_for(controller)
        if state is None or state.pane_mode != "copy-mode":
            return False

        direction = "scroll-up" if upward else "scroll-down"
        self._run(
            "send-keys",
            "-t",
            state.pane_id,
            "-X",
            "-N",
            str(max(1, int(ticks))),
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

            if (
                state.pane_mode == "copy-mode"
                and state.original_scroll_position is not None
            ):
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
    """Keep stable down capture, adding Kitty copy-mode and --scroll-up bridges."""

    bridge = TmuxScrollBridge(core)
    original_build_parser = core.build_parser
    original_scroll_down = core.X11Controller.scroll_down
    stable_estimator = core.estimate_vertical_shift
    stable_stitcher = core.stitch_frames

    def build_parser_with_scroll_up():
        parser = original_build_parser()
        parser.add_argument(
            "--scroll-up",
            action="store_true",
            help="capture tmux terminal history upward and stitch top-to-bottom",
        )
        return parser

    def terminal_aware_scroll_down(controller, ticks: int) -> None:
        # Alacritty and normal GUI remain on the validated X11 path.
        # Kitty copy mode and Kitty+Lazygit use tmux because Kitty ignores the
        # synthetic X11 wheel in those cases.
        if bridge.scroll_existing_kitty_copy_mode(controller, ticks):
            return
        original_scroll_down(controller, ticks)

    core.build_parser = build_parser_with_scroll_up
    core.X11Controller.scroll_down = terminal_aware_scroll_down

    def run_capture(args):
        if not bool(getattr(args, "scroll_up", False)):
            return capture_runner(args)

        previous_move_to_region = core.X11Controller.move_to_region
        previous_scroll_down = core.X11Controller.scroll_down
        previous_controller_close = core.X11Controller.close
        previous_estimator = core.estimate_vertical_shift
        previous_stitcher = core.stitch_frames

        def move_to_region_and_prepare(controller, region) -> None:
            previous_move_to_region(controller, region)
            if not bridge.prepare_copy_mode(controller):
                raise core.CaptureError(
                    "--scroll-up requires the selected Kitty/Alacritty window "
                    "to use an active tmux client"
                )

        def terminal_scroll_up(controller, ticks: int) -> None:
            if bridge.scroll_copy_mode(controller, ticks, upward=True):
                return
            raise core.CaptureError("tmux copy-mode upward scrolling is not ready")

        def close_with_terminal_restore(controller) -> None:
            try:
                bridge.restore(controller)
            finally:
                previous_controller_close(controller)

        def estimate_upward(previous, current, **kwargs):
            return stable_estimator(current, previous, **kwargs)

        def stitch_upward(frames, matches):
            return stable_stitcher(
                list(reversed(frames)),
                list(reversed(matches)),
            )

        core.X11Controller.move_to_region = move_to_region_and_prepare
        core.X11Controller.scroll_down = terminal_scroll_up
        core.X11Controller.close = close_with_terminal_restore
        core.estimate_vertical_shift = estimate_upward
        core.stitch_frames = stitch_upward
        try:
            return capture_runner(args)
        finally:
            core.X11Controller.move_to_region = previous_move_to_region
            core.X11Controller.scroll_down = previous_scroll_down
            core.X11Controller.close = previous_controller_close
            core.estimate_vertical_shift = previous_estimator
            core.stitch_frames = previous_stitcher

    return run_capture