#!/usr/bin/env python3
"""验证 Alt 工作区快捷键不被占用、快速切换不抢焦点及全局 Esc。"""

from __future__ import annotations

import importlib.util
import queue
import sys
import threading
import time
from pathlib import Path

from Xlib import X, XK, display, error
from Xlib.ext import xtest

ROOT = Path(__file__).resolve().parents[1]
CORE_SPEC = importlib.util.spec_from_file_location(
    "scrollshot", ROOT / "src" / "scrollshot.py"
)
assert CORE_SPEC is not None and CORE_SPEC.loader is not None
core = importlib.util.module_from_spec(CORE_SPEC)
sys.modules[CORE_SPEC.name] = core
CORE_SPEC.loader.exec_module(core)

UI_SPEC = importlib.util.spec_from_file_location(
    "selection_ui", ROOT / "src" / "selection_ui.py"
)
assert UI_SPEC is not None and UI_SPEC.loader is not None
selection_ui = importlib.util.module_from_spec(UI_SPEC)
sys.modules[UI_SPEC.name] = selection_ui
UI_SPEC.loader.exec_module(selection_ui)
selector = selection_ui.create_select_region(core)

control_display = display.Display()
control_root = control_display.screen().root
focus_window = control_root.create_window(
    20,
    20,
    240,
    120,
    0,
    control_display.screen().root_depth,
    X.InputOutput,
    X.CopyFromParent,
    background_pixel=control_display.screen().white_pixel,
    event_mask=X.ExposureMask,
)
focus_window.map()
focus_window.set_input_focus(X.RevertToParent, X.CurrentTime)
control_display.sync()

worker_errors: queue.SimpleQueue[BaseException] = queue.SimpleQueue()


def verify_shortcut_and_switch_workspaces() -> None:
    try:
        time.sleep(0.8)
        worker_display = display.Display()
        try:
            focused = worker_display.get_input_focus().focus
            focused_id = getattr(focused, "id", focused)
            assert focused_id == focus_window.id, (focused_id, focus_window.id)

            one_keycode = worker_display.keysym_to_keycode(
                XK.string_to_keysym("1")
            )
            try:
                worker_display.screen().root.grab_key(
                    one_keycode,
                    X.Mod1Mask,
                    False,
                    X.GrabModeAsync,
                    X.GrabModeAsync,
                )
                worker_display.sync()
            except error.BadAccess as exc:
                raise AssertionError("Alt+1 was unexpectedly grabbed") from exc
            finally:
                worker_display.screen().root.ungrab_key(
                    one_keycode,
                    X.Mod1Mask,
                )
                worker_display.sync()

            workspace_atom = worker_display.intern_atom("_NET_CURRENT_DESKTOP")
            cardinal_atom = worker_display.intern_atom("CARDINAL")
            for desktop in (1, 2, 3, 1):
                worker_display.screen().root.change_property(
                    workspace_atom,
                    cardinal_atom,
                    32,
                    [desktop],
                )
                worker_display.sync()
                time.sleep(0.04)

            time.sleep(0.65)
            focused = worker_display.get_input_focus().focus
            focused_id = getattr(focused, "id", focused)
            assert focused_id == focus_window.id, (focused_id, focus_window.id)

            escape_keycode = worker_display.keysym_to_keycode(
                XK.string_to_keysym("Escape")
            )
            xtest.fake_input(worker_display, X.KeyPress, escape_keycode)
            xtest.fake_input(worker_display, X.KeyRelease, escape_keycode)
            worker_display.sync()
        finally:
            worker_display.close()
    except BaseException as exc:
        worker_errors.put(exc)


worker = threading.Thread(
    target=verify_shortcut_and_switch_workspaces,
    daemon=True,
)
worker.start()
try:
    selector()
except core.SelectionCancelled:
    pass
else:
    raise AssertionError("plain Esc did not cancel selection")
finally:
    worker.join(timeout=4)
    focus_window.destroy()
    control_display.close()

if worker.is_alive():
    raise AssertionError("X11 input worker did not finish")
if not worker_errors.empty():
    raise worker_errors.get()

print("selection input and rapid workspace refresh smoke test passed")
