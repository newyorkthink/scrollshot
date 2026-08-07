#!/usr/bin/env python3
"""Capture-loop resilience and global stop control for ScrollShot."""

from __future__ import annotations

import select
import signal
import threading
import time
from pathlib import Path
from types import ModuleType
from typing import Callable

import cv2

BOTTOM_GRACE_DELAY = 1.0
MATCH_RETRY_DELAY = 0.30
MATCH_RETRY_ROUNDS = 2


class CaptureStopMonitor:
    """Reserve plain Esc during capture and expose it as a thread-safe stop request."""

    def __init__(self) -> None:
        from Xlib import X, XK, display, error

        self.X = X
        self.error = error
        self.display = display.Display()
        self.root = self.display.screen().root
        self.escape_keycode = self.display.keysym_to_keycode(
            XK.string_to_keysym("Escape")
        )
        if not self.escape_keycode:
            self.display.close()
            raise RuntimeError("X11 did not provide an Escape keycode")

        self.stop_event = threading.Event()
        self.grabbed_modifiers = self._grab_escape()
        if 0 not in self.grabbed_modifiers:
            self.display.close()
            raise RuntimeError("plain Escape is already grabbed by another X11 client")

        self.thread = threading.Thread(
            target=self._run,
            name="scrollshot-capture-stop",
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
            except self.error.BadAccess:
                continue
            grabbed.append(modifiers)
        return tuple(grabbed)

    @property
    def requested(self) -> bool:
        return self.stop_event.is_set()

    def wait(self, timeout: float) -> bool:
        return self.stop_event.wait(max(0.0, float(timeout)))

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
                        self.stop_event.set()
                        return
            except Exception:
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


def create_capture_runner(
    core: ModuleType,
    effective_min_overlap: Callable[[int, int], int],
) -> Callable[..., tuple[Path, int, int]]:
    """Return the packaged capture loop with adaptive overlap, retries, and Esc stop."""

    def run_capture(args) -> tuple[Path, int, int]:
        region = args.geometry if args.geometry is not None else core.select_region()
        args.min_overlap = effective_min_overlap(args.min_overlap, region.height)
        if args.min_overlap >= region.height - 8:
            raise core.CaptureError("--min-overlap must be smaller than the capture height")

        output = core.unique_output_path(args.output or core.default_output_path())
        debug_dir = args.debug_dir.expanduser().resolve() if args.debug_dir else None
        if debug_dir:
            debug_dir.mkdir(parents=True, exist_ok=True)

        controller = core.X11Controller()
        frames = []
        matches = []
        stable_rounds = 0
        stop_requested = False
        stop_monitor: CaptureStopMonitor | None = None

        def request_stop(_signum, _frame) -> None:
            nonlocal stop_requested
            stop_requested = True

        def should_stop() -> bool:
            return stop_requested or bool(stop_monitor and stop_monitor.requested)

        def wait_or_stop(seconds: float) -> bool:
            if should_stop():
                return True
            if stop_monitor is not None:
                stop_monitor.wait(seconds)
            else:
                time.sleep(max(0.0, float(seconds)))
            return should_stop()

        previous_sigint = signal.signal(signal.SIGINT, request_stop)
        try:
            controller.move_to_region(region)
            time.sleep(args.settle_delay)
            first = controller.capture(region)
            frames.append(first)
            if debug_dir:
                cv2.imwrite(str(debug_dir / "frame-000.png"), first)

            try:
                stop_monitor = CaptureStopMonitor()
            except Exception:
                stop_monitor = None

            for frame_index in range(1, args.max_frames):
                if should_stop():
                    break

                controller.move_to_region(region)
                controller.scroll_down(args.scroll_ticks)
                if wait_or_stop(args.delay):
                    break

                current = controller.capture(region)
                if debug_dir:
                    cv2.imwrite(str(debug_dir / f"frame-{frame_index:03d}.png"), current)

                previous = frames[-1]
                if core.frames_are_stable(previous, current):
                    stable_rounds += 1
                    if stable_rounds >= args.stable_rounds:
                        grace = max(BOTTOM_GRACE_DELAY, float(args.delay))
                        if wait_or_stop(grace):
                            break
                        late = controller.capture(region)
                        if core.frames_are_stable(current, late):
                            break
                        frames[-1] = late
                        stable_rounds = 0
                    continue

                stable_rounds = 0
                match = core.estimate_vertical_shift(
                    previous,
                    current,
                    min_overlap=args.min_overlap,
                    score_threshold=args.match_threshold,
                )

                retry_frame = current
                for _ in range(MATCH_RETRY_ROUNDS):
                    if match is not None or should_stop():
                        break
                    if wait_or_stop(max(MATCH_RETRY_DELAY, float(args.settle_delay))):
                        break
                    retry_frame = controller.capture(region)
                    match = core.estimate_vertical_shift(
                        previous,
                        retry_frame,
                        min_overlap=args.min_overlap,
                        score_threshold=args.match_threshold,
                    )

                if should_stop():
                    break
                if match is None:
                    break

                current = retry_frame if retry_frame is not current else current
                frames.append(current)
                matches.append(match)

            stitched = core.stitch_frames(frames, matches)
            core.save_png(output, stitched)
            return output, len(frames), stitched.shape[0]
        finally:
            signal.signal(signal.SIGINT, previous_sigint)
            if stop_monitor is not None:
                stop_monitor.close()
            try:
                controller.restore_pointer()
            finally:
                controller.close()

    return run_capture
