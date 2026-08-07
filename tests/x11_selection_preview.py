#!/usr/bin/env python3
"""在真实 X11 虚拟显示中验证框选背景预览与鼠标框选。"""

from __future__ import annotations

import importlib.util
import sys
import threading
import time
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SPEC = importlib.util.spec_from_file_location(
    "scrollshot", ROOT / "src" / "scrollshot.py"
)
assert CORE_SPEC is not None and CORE_SPEC.loader is not None
scrollshot = importlib.util.module_from_spec(CORE_SPEC)
sys.modules[CORE_SPEC.name] = scrollshot
CORE_SPEC.loader.exec_module(scrollshot)

UI_SPEC = importlib.util.spec_from_file_location(
    "selection_ui", ROOT / "src" / "selection_ui.py"
)
assert UI_SPEC is not None and UI_SPEC.loader is not None
selection_ui = importlib.util.module_from_spec(UI_SPEC)
sys.modules[UI_SPEC.name] = selection_ui
UI_SPEC.loader.exec_module(selection_ui)
select_region = selection_ui.create_select_region(scrollshot)

root = tk.Tk()
root.geometry("640x420+40+40")
root.configure(background="white")
label = tk.Label(
    root,
    text="Selection preview smoke test",
    foreground="black",
    background="white",
    font=("Sans", 24, "bold"),
)
label.pack(expand=True, fill="both")
root.update_idletasks()
root.update()

frame = scrollshot.capture_desktop_frame()
preview = scrollshot.build_selection_preview(frame)
photo = tk.PhotoImage(data=scrollshot.frame_to_ppm(preview), format="PPM")

assert frame.shape[:2] == preview.shape[:2]
assert photo.width() == frame.shape[1]
assert photo.height() == frame.shape[0]
assert float(frame.mean()) > 20.0
assert 0.0 < float(preview.mean()) < float(frame.mean())
root.destroy()


def perform_drag() -> None:
    time.sleep(0.8)
    X, display_module, xtest = scrollshot.import_x11()
    x_display = display_module.Display()
    try:
        xtest.fake_input(x_display, X.MotionNotify, x=100, y=120)
        xtest.fake_input(x_display, X.ButtonPress, 1)
        x_display.sync()
        time.sleep(0.1)
        xtest.fake_input(x_display, X.MotionNotify, x=520, y=420)
        x_display.sync()
        time.sleep(0.1)
        xtest.fake_input(x_display, X.ButtonRelease, 1)
        x_display.sync()
    finally:
        x_display.close()


drag_thread = threading.Thread(target=perform_drag, daemon=True)
drag_thread.start()
region = select_region()
drag_thread.join(timeout=2)

assert region == scrollshot.Region(100, 120, 420, 300), region
print("selection preview smoke test passed")
