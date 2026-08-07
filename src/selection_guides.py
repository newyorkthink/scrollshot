#!/usr/bin/env python3
"""Crosshair selection overlay built on ScrollShot's stable X11 monitor."""

from __future__ import annotations

import os
import queue
from types import ModuleType
from typing import Callable

import numpy as np
from Xlib import display

import selection_ui as baseline
from pointer_guides import PointerMagnifier

WORKSPACE_SETTLE_MS = baseline.WORKSPACE_SETTLE_MS
X11_POLL_MS = baseline.X11_POLL_MS


def configure_overlay_window(window_id: int) -> None:
    """Preserve non-focusable behavior and expose a stable WM class."""

    baseline.set_window_non_focusable(window_id)
    x_display = display.Display()
    try:
        window = x_display.create_resource_object("window", int(window_id))
        window.set_wm_name("ScrollShot")
        window.set_wm_class("scrollshot", "ScrollShot")
        x_display.sync()
    finally:
        x_display.close()


def create_select_region(core: ModuleType) -> Callable[[], object]:
    """Create a selector compatible with the existing ScrollShot core module."""

    def select_region():
        if not os.environ.get("DISPLAY"):
            raise core.CaptureError("DISPLAY is not set; X11 is required")
        try:
            import tkinter as tk
        except ImportError as exc:
            raise core.CaptureError("tkinter is required") from exc

        desktop_frame = core.capture_desktop_frame()
        screen_height, screen_width = desktop_frame.shape[:2]
        events: queue.SimpleQueue[baseline.SelectionEvent] = queue.SimpleQueue()
        state: dict[str, object] = {
            "region": None,
            "cancelled": False,
            "start": None,
            "rectangle": None,
            "frame": desktop_frame,
            "background": None,
            "pointer": (screen_width // 2, screen_height // 2),
            "refreshing": False,
            "refresh_job": None,
            "refresh_serial": 0,
            "error": None,
        }

        root = tk.Tk()
        root.withdraw()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.geometry(f"{screen_width}x{screen_height}+0+0")
        root.option_add("*takeFocus", 0)
        root.wm_title("ScrollShot")
        canvas = tk.Canvas(
            root,
            cursor="none",
            highlightthickness=0,
            takefocus=False,
        )
        canvas.pack(fill="both", expand=True)

        def render_preview(frame: np.ndarray) -> None:
            photo = tk.PhotoImage(
                master=root,
                data=core.frame_to_ppm(core.build_selection_preview(frame)),
                format="PPM",
            )
            background = state["background"]
            if isinstance(background, int):
                canvas.itemconfigure(background, image=photo)
            else:
                state["background"] = canvas.create_image(
                    0,
                    0,
                    image=photo,
                    anchor="nw",
                )
                canvas.tag_lower(state["background"])
            canvas.background_photo = photo
            state["frame"] = frame

        render_preview(desktop_frame)
        notice_width = min(780, max(440, screen_width - 40))
        notice_left = (screen_width - notice_width) // 2
        canvas.create_rectangle(
            notice_left,
            14,
            notice_left + notice_width,
            60,
            fill="#111827",
            outline="#374151",
            width=1,
            tags=("notice",),
        )
        canvas.create_text(
            screen_width // 2,
            37,
            text=(
                "十字线精确定位 · 放大镜跟随鼠标 · Esc 取消 · 可切换 i3 工作区 / "
                "Crosshair · pointer-following magnifier · Esc cancels"
            ),
            fill="white",
            font=("Sans", 13, "bold"),
            tags=("notice",),
        )

        crosshair_vertical = canvas.create_line(
            screen_width // 2,
            0,
            screen_width // 2,
            screen_height,
            fill="#f8fafc",
            width=1,
            tags=("crosshair",),
        )
        crosshair_horizontal = canvas.create_line(
            0,
            screen_height // 2,
            screen_width,
            screen_height // 2,
            fill="#f8fafc",
            width=1,
            tags=("crosshair",),
        )
        magnifier = PointerMagnifier(
            canvas,
            root,
            core,
            tk.PhotoImage,
            screen_width,
            screen_height,
        )

        def clear_rectangle() -> None:
            rectangle = state["rectangle"]
            if isinstance(rectangle, int):
                canvas.delete(rectangle)
            state["rectangle"] = None
            state["start"] = None

        def hide_pointer_guides() -> None:
            canvas.itemconfigure("crosshair", state="hidden")
            magnifier.hide()

        def update_pointer_guides(x: int, y: int) -> None:
            if state["refreshing"]:
                return
            x = max(0, min(screen_width - 1, int(x)))
            y = max(0, min(screen_height - 1, int(y)))
            state["pointer"] = (x, y)
            canvas.coords(crosshair_vertical, x, 0, x, screen_height)
            canvas.coords(crosshair_horizontal, 0, y, screen_width, y)
            canvas.itemconfigure("crosshair", state="normal")
            canvas.tag_raise("crosshair")
            canvas.tag_raise("notice")

            rectangle = state["rectangle"]
            if isinstance(rectangle, int):
                canvas.tag_raise(rectangle)

            frame = state["frame"]
            if isinstance(frame, np.ndarray):
                start = state["start"]
                magnifier.update(
                    frame,
                    x,
                    y,
                    start if isinstance(start, tuple) else None,
                )

        def on_press(event) -> None:
            if state["refreshing"]:
                return
            clear_rectangle()
            x = max(0, min(screen_width - 1, int(event.x)))
            y = max(0, min(screen_height - 1, int(event.y)))
            state["start"] = (x, y)
            state["rectangle"] = canvas.create_rectangle(
                x,
                y,
                x,
                y,
                outline="#22d3ee",
                width=2,
            )
            update_pointer_guides(x, y)

        def on_drag(event) -> None:
            rectangle = state["rectangle"]
            start = state["start"]
            if isinstance(rectangle, int) and isinstance(start, tuple):
                x = max(0, min(screen_width - 1, int(event.x)))
                y = max(0, min(screen_height - 1, int(event.y)))
                canvas.coords(rectangle, start[0], start[1], x, y)
                update_pointer_guides(x, y)

        def on_release(event) -> None:
            if state["refreshing"]:
                return
            start = state["start"]
            if not isinstance(start, tuple):
                return
            x1, x2 = sorted((start[0], int(event.x)))
            y1, y2 = sorted((start[1], int(event.y)))
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(screen_width, x2), min(screen_height, y2)
            if (
                x2 - x1 >= core.MIN_REGION_SIZE
                and y2 - y1 >= core.MIN_REGION_SIZE
            ):
                state["region"] = core.Region(x1, y1, x2 - x1, y2 - y1)
                root.quit()
            else:
                clear_rectangle()
                update_pointer_guides(event.x, event.y)

        def on_cancel(_event=None) -> None:
            state["cancelled"] = True
            root.quit()

        def show_overlay() -> None:
            root.deiconify()
            root.update_idletasks()
            try:
                configure_overlay_window(root.winfo_id())
            except Exception:
                pass
            pointer = state["pointer"]
            assert isinstance(pointer, tuple)
            update_pointer_guides(pointer[0], pointer[1])

        def finish_workspace_refresh(serial: int, desktop: int | None) -> None:
            if serial != state["refresh_serial"]:
                return
            state["refresh_job"] = None
            try:
                current_before = baseline.read_current_desktop()
                if (
                    desktop is not None
                    and current_before is not None
                    and current_before != desktop
                ):
                    begin_workspace_refresh(current_before)
                    return
                frame = core.capture_desktop_frame()
                if frame.shape[:2] != (screen_height, screen_width):
                    raise core.CaptureError(
                        "screen dimensions changed while selecting a region"
                    )
                current_after = baseline.read_current_desktop()
                if current_before != current_after:
                    begin_workspace_refresh(current_after)
                    return
                render_preview(frame)
            except Exception as exc:
                state["error"] = exc
                root.quit()
                return
            state["refreshing"] = False
            show_overlay()

        def begin_workspace_refresh(desktop: int | None) -> None:
            state["refresh_serial"] = int(state["refresh_serial"]) + 1
            serial = int(state["refresh_serial"])
            state["refreshing"] = True
            clear_rectangle()
            hide_pointer_guides()
            root.withdraw()
            refresh_job = state["refresh_job"]
            if isinstance(refresh_job, str):
                try:
                    root.after_cancel(refresh_job)
                except Exception:
                    pass
            state["refresh_job"] = root.after(
                WORKSPACE_SETTLE_MS,
                lambda: finish_workspace_refresh(serial, desktop),
            )

        def poll_x11_events() -> None:
            while True:
                try:
                    event, desktop = events.get_nowait()
                except queue.Empty:
                    break
                if event == "cancel":
                    on_cancel()
                    return
                if event == "workspace":
                    begin_workspace_refresh(desktop)
                elif event == "monitor-error":
                    state["error"] = core.CaptureError(
                        "X11 selection event monitor stopped unexpectedly"
                    )
                    root.quit()
                    return
            root.after(X11_POLL_MS, poll_x11_events)

        canvas.bind(
            "<Motion>",
            lambda event: update_pointer_guides(event.x, event.y),
        )
        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        root.bind_all("<Escape>", on_cancel)

        try:
            monitor = baseline.SelectionX11Monitor(events)
        except Exception as exc:
            root.destroy()
            raise core.CaptureError(
                f"unable to start the X11 selection monitor: {exc}"
            ) from exc

        show_overlay()
        root.after(X11_POLL_MS, poll_x11_events)
        try:
            root.mainloop()
        finally:
            refresh_job = state["refresh_job"]
            if isinstance(refresh_job, str):
                try:
                    root.after_cancel(refresh_job)
                except Exception:
                    pass
            monitor.close()
            root.destroy()

        error = state["error"]
        if error is not None:
            if isinstance(error, core.CaptureError):
                raise error
            raise core.CaptureError(str(error)) from error
        if state["cancelled"] or not isinstance(state["region"], core.Region):
            raise core.SelectionCancelled
        return state["region"]

    return select_region
