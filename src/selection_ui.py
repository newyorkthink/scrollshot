#!/usr/bin/env python3
"""X11 selection overlay with global Esc, workspace refresh, and magnifier."""

from __future__ import annotations

import os
import queue
import select
import threading
from types import ModuleType
from typing import Callable

import numpy as np

MAGNIFIER_SOURCE_SIZE = 15
MAGNIFIER_ZOOM = 12
WORKSPACE_SETTLE_MS = 220
X11_POLL_MS = 15

SelectionEvent = tuple[str, int | None]


def build_magnifier_frame(
    frame: np.ndarray,
    x: int,
    y: int,
    *,
    source_size: int = MAGNIFIER_SOURCE_SIZE,
    zoom: int = MAGNIFIER_ZOOM,
) -> np.ndarray:
    """Return an edge-padded nearest-neighbour magnifier centered on one pixel."""

    if frame.ndim != 3 or frame.shape[2] != 3:
        raise ValueError("magnifier requires a three-channel image")
    if source_size < 3 or source_size % 2 == 0:
        raise ValueError("source_size must be an odd integer of at least 3")
    if zoom < 1:
        raise ValueError("zoom must be at least 1")

    height, width = frame.shape[:2]
    if width <= 0 or height <= 0:
        raise ValueError("magnifier source image is empty")

    x = max(0, min(width - 1, int(x)))
    y = max(0, min(height - 1, int(y)))
    radius = source_size // 2
    requested_left = x - radius
    requested_top = y - radius
    requested_right = x + radius + 1
    requested_bottom = y + radius + 1

    left = max(0, requested_left)
    top = max(0, requested_top)
    right = min(width, requested_right)
    bottom = min(height, requested_bottom)
    patch = frame[top:bottom, left:right]

    padding = (
        (top - requested_top, requested_bottom - bottom),
        (left - requested_left, requested_right - right),
        (0, 0),
    )
    if any(before or after for before, after in padding):
        patch = np.pad(patch, padding, mode="edge")

    magnified = np.repeat(np.repeat(patch, zoom, axis=0), zoom, axis=1)
    return np.ascontiguousarray(magnified)


def read_current_desktop() -> int | None:
    """Read the EWMH current desktop without changing focus or mappings."""

    from Xlib import X, display

    x_display = display.Display()
    try:
        root = x_display.screen().root
        atom = x_display.intern_atom("_NET_CURRENT_DESKTOP")
        value = root.get_full_property(atom, X.AnyPropertyType)
        if value is None or len(value.value) == 0:
            return None
        return int(value.value[0])
    finally:
        x_display.close()


def set_window_non_focusable(window_id: int) -> None:
    """Set WM_HINTS.input=false so clicking the overlay does not take focus."""

    from Xlib import display

    x_display = display.Display()
    try:
        window = x_display.create_resource_object("window", int(window_id))
        window.set_wm_hints(input=0)
        x_display.sync()
    finally:
        x_display.close()


class SelectionX11Monitor:
    """Observe plain Esc and EWMH workspace changes without grabbing Alt keys."""

    def __init__(self, events: queue.SimpleQueue[SelectionEvent]) -> None:
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
        try:
            self.grabbed_modifiers = self._grab_escape()
            self.display.sync()
        except Exception:
            self.display.close()
            raise

        self.stop_event = threading.Event()
        self.thread = threading.Thread(
            target=self._run,
            name="scrollshot-selection-x11",
            daemon=True,
        )
        self.thread.start()

    def _num_lock_mask(self) -> int:
        from Xlib import XK

        keycode = self.display.keysym_to_keycode(XK.string_to_keysym("Num_Lock"))
        if not keycode:
            return 0
        for index, keycodes in enumerate(self.display.get_modifier_mapping()):
            if keycode in keycodes:
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

    def _current_desktop(self) -> int | None:
        value = self.root.get_full_property(
            self.workspace_atom,
            self.X.AnyPropertyType,
        )
        if value is None or len(value.value) == 0:
            return None
        return int(value.value[0])

    def _run(self) -> None:
        while not self.stop_event.is_set():
            try:
                readable, _, _ = select.select(
                    [self.display.fileno()], [], [], 0.10
                )
                if not readable:
                    continue
                while self.display.pending_events():
                    event = self.display.next_event()
                    if (
                        event.type == self.X.KeyPress
                        and event.detail == self.escape_keycode
                    ):
                        self.events.put(("cancel", None))
                    elif (
                        event.type == self.X.PropertyNotify
                        and event.atom == self.workspace_atom
                    ):
                        self.events.put(("workspace", self._current_desktop()))
            except Exception:
                if not self.stop_event.is_set():
                    self.events.put(("monitor-error", None))
                return

    def close(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=0.5)
        try:
            for modifiers in self.grabbed_modifiers:
                self.root.ungrab_key(self.escape_keycode, modifiers)
            self.display.sync()
        finally:
            self.display.close()


class PixelMagnifier:
    """Render a movable pixel grid and live selection coordinates on a canvas."""

    BORDER = 2
    LABEL_HEIGHT = 30
    MARGIN = 18

    def __init__(
        self,
        canvas,
        root,
        core: ModuleType,
        photo_image_type,
        screen_width: int,
        screen_height: int,
    ) -> None:
        self.canvas = canvas
        self.root = root
        self.core = core
        self.photo_image_type = photo_image_type
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.image_size = MAGNIFIER_SOURCE_SIZE * MAGNIFIER_ZOOM
        self.panel_width = self.image_size + self.BORDER * 2
        self.panel_height = self.image_size + self.LABEL_HEIGHT + self.BORDER * 2
        self.photo = None

        self.panel = canvas.create_rectangle(
            0,
            0,
            1,
            1,
            fill="#0f172a",
            outline="white",
            width=2,
            tags=("magnifier",),
        )
        self.image = canvas.create_image(
            0,
            0,
            anchor="nw",
            tags=("magnifier",),
        )
        self.grid = [
            canvas.create_line(
                0,
                0,
                1,
                1,
                fill="#334155",
                width=1,
                tags=("magnifier",),
            )
            for _ in range((MAGNIFIER_SOURCE_SIZE + 1) * 2)
        ]
        self.pixel = canvas.create_rectangle(
            0,
            0,
            1,
            1,
            outline="#fb7185",
            width=2,
            tags=("magnifier",),
        )
        self.label = canvas.create_text(
            0,
            0,
            anchor="center",
            fill="white",
            font=("Sans", 11, "bold"),
            tags=("magnifier",),
        )
        self.hide()

    def hide(self) -> None:
        self.canvas.itemconfigure("magnifier", state="hidden")

    def _position(self, x: int, y: int) -> tuple[int, int]:
        panel_x = (
            self.screen_width - self.panel_width - self.MARGIN
            if x < self.screen_width // 2
            else self.MARGIN
        )
        panel_y = (
            self.screen_height - self.panel_height - self.MARGIN
            if y < self.screen_height // 2
            else self.MARGIN
        )
        return panel_x, panel_y

    def update(
        self,
        frame: np.ndarray,
        x: int,
        y: int,
        start: tuple[int, int] | None = None,
    ) -> None:
        x = max(0, min(self.screen_width - 1, int(x)))
        y = max(0, min(self.screen_height - 1, int(y)))
        zoomed = build_magnifier_frame(frame, x, y)
        self.photo = self.photo_image_type(
            master=self.root,
            data=self.core.frame_to_ppm(zoomed),
            format="PPM",
        )

        panel_x, panel_y = self._position(x, y)
        image_x = panel_x + self.BORDER
        image_y = panel_y + self.BORDER
        image_right = image_x + self.image_size
        image_bottom = image_y + self.image_size

        self.canvas.coords(
            self.panel,
            panel_x,
            panel_y,
            panel_x + self.panel_width,
            panel_y + self.panel_height,
        )
        self.canvas.coords(self.image, image_x, image_y)
        self.canvas.itemconfigure(self.image, image=self.photo)

        count = MAGNIFIER_SOURCE_SIZE + 1
        for index in range(count):
            offset = index * MAGNIFIER_ZOOM
            self.canvas.coords(
                self.grid[index],
                image_x + offset,
                image_y,
                image_x + offset,
                image_bottom,
            )
            self.canvas.coords(
                self.grid[count + index],
                image_x,
                image_y + offset,
                image_right,
                image_y + offset,
            )

        center = MAGNIFIER_SOURCE_SIZE // 2
        center_left = image_x + center * MAGNIFIER_ZOOM
        center_top = image_y + center * MAGNIFIER_ZOOM
        self.canvas.coords(
            self.pixel,
            center_left,
            center_top,
            center_left + MAGNIFIER_ZOOM,
            center_top + MAGNIFIER_ZOOM,
        )

        text = f"X {x}   Y {y}"
        if start is not None:
            text += f"   {abs(x - start[0])} × {abs(y - start[1])}"
        self.canvas.coords(
            self.label,
            panel_x + self.panel_width // 2,
            image_bottom + self.LABEL_HEIGHT // 2,
        )
        self.canvas.itemconfigure(self.label, text=text)
        self.canvas.itemconfigure("magnifier", state="normal")
        self.canvas.tag_raise("magnifier")


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
        events: queue.SimpleQueue[SelectionEvent] = queue.SimpleQueue()
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
        canvas = tk.Canvas(
            root,
            cursor="crosshair",
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
                    0, 0, image=photo, anchor="nw"
                )
                canvas.tag_lower(state["background"])
            canvas.background_photo = photo
            state["frame"] = frame

        render_preview(desktop_frame)
        notice_width = min(760, max(420, screen_width - 40))
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
                "拖动框选 · 放大镜像素对齐 · Esc 取消 · 可切换 i3 工作区 / "
                "Drag to select · pixel magnifier · Esc cancels"
            ),
            fill="white",
            font=("Sans", 13, "bold"),
        )
        magnifier = PixelMagnifier(
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

        def update_magnifier(x: int, y: int) -> None:
            if state["refreshing"]:
                return
            x = max(0, min(screen_width - 1, int(x)))
            y = max(0, min(screen_height - 1, int(y)))
            state["pointer"] = (x, y)
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
                x, y, x, y, outline="#22d3ee", width=1
            )
            update_magnifier(x, y)

        def on_drag(event) -> None:
            rectangle = state["rectangle"]
            start = state["start"]
            if isinstance(rectangle, int) and isinstance(start, tuple):
                x = max(0, min(screen_width - 1, int(event.x)))
                y = max(0, min(screen_height - 1, int(event.y)))
                canvas.coords(rectangle, start[0], start[1], x, y)
                update_magnifier(x, y)

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
                update_magnifier(event.x, event.y)

        def on_cancel(_event=None) -> None:
            state["cancelled"] = True
            root.quit()

        def show_overlay() -> None:
            root.deiconify()
            root.update_idletasks()
            try:
                set_window_non_focusable(root.winfo_id())
            except Exception:
                pass
            pointer = state["pointer"]
            assert isinstance(pointer, tuple)
            update_magnifier(pointer[0], pointer[1])

        def finish_workspace_refresh(serial: int, desktop: int | None) -> None:
            if serial != state["refresh_serial"]:
                return
            state["refresh_job"] = None
            try:
                current_before = read_current_desktop()
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
                current_after = read_current_desktop()
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
            magnifier.hide()
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

        canvas.bind("<Motion>", lambda event: update_magnifier(event.x, event.y))
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
