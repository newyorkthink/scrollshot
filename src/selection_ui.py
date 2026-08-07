#!/usr/bin/env python3
"""X11 selection overlay with global Esc handling and workspace refresh."""

from __future__ import annotations

import os
import queue
import select
import threading
from types import ModuleType
from typing import Callable


class SelectionX11Monitor:
    """Observe plain Esc and EWMH workspace changes without taking focus."""

    def __init__(self, events: queue.SimpleQueue[str]) -> None:
        from Xlib import X, XK, display

        self.X = X
        self.events = events
        self.display = display.Display()
        self.root = self.display.screen().root
        self.workspace_atom = self.display.intern_atom("_NET_CURRENT_DESKTOP")
        self.escape_keycode = self.display.keysym_to_keycode(
            XK.string_to_keysym("Escape")
        )
        if not self.escape_keycode:
            self.display.close()
            raise RuntimeError("X11 did not provide an Escape keycode")

        self.root.change_attributes(event_mask=X.PropertyChangeMask)
        self.grabbed_modifiers = self._grab_escape()
        self.display.sync()

        self.stop_event = threading.Event()
        self.thread = threading.Thread(
            target=self._run,
            name="scrollshot-selection-x11",
            daemon=True,
        )
        self.thread.start()

    def _num_lock_mask(self) -> int:
        from Xlib import XK

        num_lock_keycode = self.display.keysym_to_keycode(
            XK.string_to_keysym("Num_Lock")
        )
        if not num_lock_keycode:
            return 0
        for index, keycodes in enumerate(self.display.get_modifier_mapping()):
            if num_lock_keycode in keycodes:
                return 1 << index
        return 0

    def _grab_escape(self) -> tuple[int, ...]:
        masks = {0, self.X.LockMask}
        num_lock_mask = self._num_lock_mask()
        if num_lock_mask:
            masks.update({num_lock_mask, self.X.LockMask | num_lock_mask})

        from Xlib import error

        grabbed: list[int] = []
        for modifiers in sorted(masks):
            try:
                self.root.grab_key(
                    self.escape_keycode,
                    modifiers,
                    False,
                    self.X.GrabModeAsync,
                    self.X.GrabModeAsync,
                )
                self.display.sync()
            except error.BadAccess:
                continue
            grabbed.append(modifiers)
        if 0 not in grabbed:
            raise RuntimeError("plain Escape is already grabbed by another X11 client")
        return tuple(grabbed)

    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                readable, _, _ = select.select(
                    [self.display.fileno()],
                    [],
                    [],
                    0.10,
                )
                if not readable:
                    continue
                while self.display.pending_events():
                    event = self.display.next_event()
                    if (
                        event.type == self.X.KeyPress
                        and event.detail == self.escape_keycode
                    ):
                        self.events.put("cancel")
                    elif (
                        event.type == self.X.PropertyNotify
                        and event.atom == self.workspace_atom
                    ):
                        self.events.put("workspace")
            except Exception:
                if not self.stop_event.is_set():
                    self.events.put("monitor-error")
                return

    def close(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=0.5)
        for modifiers in self.grabbed_modifiers:
            self.root.ungrab_key(self.escape_keycode, modifiers)
        self.display.sync()
        self.display.close()


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

        state: dict[str, object] = {
            "region": None,
            "cancelled": False,
            "start_x": 0,
            "start_y": 0,
            "rectangle": None,
            "background": None,
            "refreshing": False,
            "error": None,
        }
        events: queue.SimpleQueue[str] = queue.SimpleQueue()

        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.geometry(f"{screen_width}x{screen_height}+0+0")
        root.lift()

        canvas = tk.Canvas(
            master=root,
            cursor="crosshair",
            highlightthickness=0,
        )
        canvas.pack(fill="both", expand=True)

        def render_preview(frame) -> None:
            preview_ppm = core.frame_to_ppm(core.build_selection_preview(frame))
            photo = tk.PhotoImage(master=root, data=preview_ppm, format="PPM")
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

        render_preview(desktop_frame)

        notice_width = min(660, max(360, screen_width - 40))
        notice_left = (screen_width - notice_width) // 2
        canvas.create_rectangle(
            notice_left,
            14,
            notice_left + notice_width,
            60,
            fill="#111827",
            outline="#374151",
            width=1,
        )
        canvas.create_text(
            screen_width // 2,
            37,
            text=(
                "拖动框选滚动区域 · Esc 取消 · 可切换 i3 工作区 / "
                "Drag to select · Esc cancels · workspace keys remain active"
            ),
            fill="white",
            font=("Sans", 13, "bold"),
        )

        def clear_rectangle() -> None:
            rectangle = state["rectangle"]
            if isinstance(rectangle, int):
                canvas.delete(rectangle)
            state["rectangle"] = None

        def on_press(event) -> None:
            if state["refreshing"]:
                return
            state["start_x"] = max(0, min(screen_width - 1, int(event.x)))
            state["start_y"] = max(0, min(screen_height - 1, int(event.y)))
            clear_rectangle()
            state["rectangle"] = canvas.create_rectangle(
                state["start_x"],
                state["start_y"],
                state["start_x"],
                state["start_y"],
                outline="#22d3ee",
                width=3,
            )

        def on_drag(event) -> None:
            rectangle = state["rectangle"]
            if isinstance(rectangle, int):
                canvas.coords(
                    rectangle,
                    int(state["start_x"]),
                    int(state["start_y"]),
                    max(0, min(screen_width - 1, int(event.x))),
                    max(0, min(screen_height - 1, int(event.y))),
                )

        def on_release(event) -> None:
            if state["refreshing"]:
                return
            x1, x2 = sorted((int(state["start_x"]), int(event.x)))
            y1, y2 = sorted((int(state["start_y"]), int(event.y)))
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(screen_width, x2), min(screen_height, y2)
            if (
                x2 - x1 >= core.MIN_REGION_SIZE
                and y2 - y1 >= core.MIN_REGION_SIZE
            ):
                state["region"] = core.Region(x1, y1, x2 - x1, y2 - y1)
                root.quit()

        def on_cancel(_event=None) -> None:
            state["cancelled"] = True
            root.quit()

        def finish_workspace_refresh() -> None:
            try:
                frame = core.capture_desktop_frame()
                if frame.shape[:2] != (screen_height, screen_width):
                    raise core.CaptureError(
                        "screen dimensions changed while selecting a region"
                    )
                render_preview(frame)
            except Exception as exc:  # surfaced after Tk exits
                state["error"] = exc
                root.quit()
                return
            finally:
                state["refreshing"] = False

            root.deiconify()
            root.geometry(f"{screen_width}x{screen_height}+0+0")
            root.attributes("-topmost", True)
            root.lift()

        def begin_workspace_refresh() -> None:
            if state["refreshing"]:
                return
            state["refreshing"] = True
            clear_rectangle()
            root.withdraw()
            root.after(90, finish_workspace_refresh)

        def poll_x11_events() -> None:
            while True:
                try:
                    event = events.get_nowait()
                except queue.Empty:
                    break
                if event == "cancel":
                    on_cancel()
                    return
                if event == "workspace":
                    begin_workspace_refresh()
                if event == "monitor-error":
                    state["error"] = core.CaptureError(
                        "X11 selection event monitor stopped unexpectedly"
                    )
                    root.quit()
                    return
            root.after(30, poll_x11_events)

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        root.bind_all("<Escape>", on_cancel)

        try:
            monitor = SelectionX11Monitor(events)
        except Exception as exc:
            root.destroy()
            raise core.CaptureError(
                f"unable to start the X11 selection monitor: {exc}"
            ) from exc

        root.after(30, poll_x11_events)
        try:
            root.mainloop()
        finally:
            monitor.close()
            root.destroy()

        if state["error"] is not None:
            error = state["error"]
            if isinstance(error, core.CaptureError):
                raise error
            raise core.CaptureError(str(error)) from error
        if state["cancelled"] or not isinstance(state["region"], core.Region):
            raise core.SelectionCancelled
        return state["region"]

    return select_region
