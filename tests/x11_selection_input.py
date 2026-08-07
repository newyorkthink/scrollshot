#!/usr/bin/env python3
"""Verify selection keeps focus available and catches Esc globally."""

from __future__ import annotations

import importlib.util
import queue
import sys
import threading
import time
from pathlib import Path

from Xlib import X, XK, display
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


def send_workspace_change_and_escape() -> None:
    try:
        time.sleep(0.8)
        worker_display = display.Display()
        try:
            focused = worker_display.get_input_focus().focus
            focused_id = getattr(focused, "id", focused)
            assert focused_id == focus_window.id, (focused_id, focus_window.id)

            workspace_atom = worker_display.intern_atom("_NET_CURRENT_DESKTOP")
            cardinal_atom = worker_display.intern_atom("CARDINAL")
            worker_display.screen().root.change_property(
                workspace_atom,
                cardinal_atom,
                32,
                [1],
            )
            worker_display.sync()
            time.sleep(0.25)

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


worker = threading.Thread(target=send_workspace_change_and_escape, daemon=True)
worker.start()
try:
    selector()
except core.SelectionCancelled:
    pass
else:
    raise AssertionError("plain Esc did not cancel selection")
finally:
    worker.join(timeout=3)
    focus_window.destroy()
    control_display.close()

if worker.is_alive():
    raise AssertionError("X11 input worker did not finish")
if not worker_errors.empty():
    raise worker_errors.get()

print("selection input smoke test passed")
