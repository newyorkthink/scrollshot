#!/usr/bin/env python3
"""Capture-loop resilience and global stop control for ScrollShot."""

from __future__ import annotations

import os
import select
import signal
import sys
import threading
import time
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Callable

import cv2

from selection_ui import read_current_desktop

BOTTOM_GRACE_DELAY = 1.0
MATCH_RETRY_DELAY = 0.30
MATCH_RETRY_ROUNDS = 2
MATCH_SCROLL_RECOVERY_ROUNDS = 2
MATCH_SCROLL_RECOVERY_MIN_HEIGHT = 160
SCROLL_TARGET_X_RATIO = 0.85
SCROLL_TARGET_Y_RATIO = 0.60


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


def _read_current_desktop_safely() -> int | None:
    """Return the current EWMH workspace when available without making capture depend on it."""

    try:
        return read_current_desktop()
    except Exception:
        return None


def _restore_system_subprocess_environment() -> None:
    """Restore the host library path before the launcher invokes system tools."""

    if not getattr(sys, "frozen", False):
        return

    # PyInstaller 会把自身目录放进 LD_LIBRARY_PATH。截图完成后恢复宿主机原值，
    # 避免后续 notify-send 等系统程序错误加载 AppImage 内的动态库。
    original = os.environ.get("LD_LIBRARY_PATH_ORIG")
    if original is not None:
        os.environ["LD_LIBRARY_PATH"] = original
    else:
        os.environ.pop("LD_LIBRARY_PATH", None)


def _move_to_scroll_target(controller, region) -> None:
    """Move the pointer to a browser-safe interior point before wheel input."""

    # 浏览器中央常见视频、地图、画布等会截获滚轮，顶部两角也可能有悬浮小视频。
    # 保持既有 move_to_region() 调用接口，只构造一个 1x1 临时指针目标区域，
    # 让其中心精确落在选区右侧偏中下位置；真实截图区域、滚动量和拼接流程不变。
    target_x = region.x + min(region.width - 1, int(region.width * SCROLL_TARGET_X_RATIO))
    target_y = region.y + min(region.height - 1, int(region.height * SCROLL_TARGET_Y_RATIO))
    target_region = SimpleNamespace(x=target_x, y=target_y, width=1, height=1)
    controller.move_to_region(target_region)


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
        capture_desktop = _read_current_desktop_safely()
        workspace_invalidated = False
        scroll_up = bool(getattr(args, "scroll_up", False))

        def request_stop(_signum, _frame) -> None:
            nonlocal stop_requested
            stop_requested = True

        def should_stop() -> bool:
            return stop_requested or bool(stop_monitor and stop_monitor.requested)

        def workspace_changed() -> bool:
            nonlocal workspace_invalidated
            if workspace_invalidated or capture_desktop is None:
                return workspace_invalidated
            current_desktop = _read_current_desktop_safely()
            if current_desktop is not None and current_desktop != capture_desktop:
                workspace_invalidated = True
            return workspace_invalidated

        def wait_or_stop(seconds: float) -> bool:
            if should_stop():
                return True
            if stop_monitor is not None:
                stop_monitor.wait(seconds)
            else:
                time.sleep(max(0.0, float(seconds)))
            return should_stop()

        def send_scroll(ticks: int) -> None:
            if scroll_up:
                core.scroll_up(controller, ticks)
            else:
                controller.scroll_down(ticks)

        def estimate_match(previous, current):
            # 向上抓取终端历史时，截图时间顺序与最终文档顺序相反。
            # 交换匹配输入即可继续复用已经验证的“向下滚动”匹配链。
            match_previous, match_current = (
                (current, previous) if scroll_up else (previous, current)
            )
            return core.estimate_vertical_shift(
                match_previous,
                match_current,
                min_overlap=args.min_overlap,
                score_threshold=args.match_threshold,
            )

        previous_sigint = signal.signal(signal.SIGINT, request_stop)
        try:
            _move_to_scroll_target(controller, region)
            time.sleep(args.settle_delay)
            if workspace_changed():
                raise core.CaptureError("workspace changed before capture started")
            first = controller.capture(region)
            if workspace_changed():
                raise core.CaptureError("workspace changed while capturing the first frame")
            frames.append(first)
            if debug_dir:
                cv2.imwrite(str(debug_dir / "frame-000.png"), first)

            try:
                stop_monitor = CaptureStopMonitor()
            except Exception:
                stop_monitor = None

            for frame_index in range(1, args.max_frames):
                if should_stop() or workspace_changed():
                    break

                _move_to_scroll_target(controller, region)
                send_scroll(args.scroll_ticks)
                if wait_or_stop(args.delay) or workspace_changed():
                    break

                current = controller.capture(region)
                if workspace_changed():
                    break
                if debug_dir:
                    cv2.imwrite(str(debug_dir / f"frame-{frame_index:03d}.png"), current)

                previous = frames[-1]
                if core.frames_are_stable(previous, current):
                    stable_rounds += 1
                    if stable_rounds >= args.stable_rounds:
                        grace = max(BOTTOM_GRACE_DELAY, float(args.delay))
                        if wait_or_stop(grace) or workspace_changed():
                            break
                        late = controller.capture(region)
                        if workspace_changed():
                            break
                        if core.frames_are_stable(current, late):
                            break
                        frames[-1] = late
                        stable_rounds = 0
                    continue

                stable_rounds = 0
                match = estimate_match(previous, current)

                retry_frame = current
                for _ in range(MATCH_RETRY_ROUNDS):
                    if match is not None or should_stop() or workspace_changed():
                        break
                    if wait_or_stop(max(MATCH_RETRY_DELAY, float(args.settle_delay))) or workspace_changed():
                        break
                    retry_frame = controller.capture(region)
                    if workspace_changed():
                        break
                    match = estimate_match(previous, retry_frame)

                # PDF 双页/整窗等重复布局可能让某一轮重叠匹配暂时无解。
                # 不立即结束整次截图；仅在较高选区里小步继续滚动两次，
                # 始终用最后一个已确认帧做锚点，匹配成功后再接入拼接链。
                if (
                    match is None
                    and region.height >= MATCH_SCROLL_RECOVERY_MIN_HEIGHT
                    and not should_stop()
                    and not workspace_changed()
                ):
                    for recovery_index in range(MATCH_SCROLL_RECOVERY_ROUNDS):
                        _move_to_scroll_target(controller, region)
                        send_scroll(1)
                        if wait_or_stop(args.delay) or workspace_changed():
                            break

                        recovery_frame = controller.capture(region)
                        if workspace_changed():
                            break
                        if debug_dir:
                            cv2.imwrite(
                                str(
                                    debug_dir
                                    / f"frame-{frame_index:03d}-recovery-{recovery_index + 1}.png"
                                ),
                                recovery_frame,
                            )

                        match = estimate_match(previous, recovery_frame)
                        if match is not None:
                            retry_frame = recovery_frame
                            break

                        if core.frames_are_stable(retry_frame, recovery_frame):
                            retry_frame = recovery_frame
                            break
                        retry_frame = recovery_frame

                if should_stop() or workspace_changed():
                    break
                if match is None:
                    break

                current = retry_frame if retry_frame is not current else current
                frames.append(current)
                matches.append(match)

            # 终端向上抓取时，采集顺序是“底部 -> 顶部”；最终图片仍应保持
            # 正常阅读顺序“顶部 -> 底部”。反转已确认帧和对应匹配即可继续
            # 复用现有稳健拼接/拼接缝清理链，不改动这些稳定算法。
            stitch_frames = list(reversed(frames)) if scroll_up else frames
            stitch_matches = list(reversed(matches)) if scroll_up else matches
            stitched = core.stitch_frames(stitch_frames, stitch_matches)
            core.save_png(output, stitched)

            # 后续启动入口会调用系统 notify-send；冻结环境先恢复宿主机动态库路径。
            _restore_system_subprocess_environment()
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
