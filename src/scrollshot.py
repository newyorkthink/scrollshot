#!/usr/bin/env python3
"""ScrollShot：Linux X11 自动滚动截图工具。"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

try:
    import cv2
    import numpy as np
except ImportError as exc:
    print(
        "缺少依赖，请安装 python3-numpy python3-opencv python3-xlib python3-tk。",
        file=sys.stderr,
    )
    raise SystemExit(3) from exc

VERSION = "0.1.0"
MIN_REGION_SIZE = 32


@dataclass(frozen=True)
class Region:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class ShiftMatch:
    shift: int
    score: float
    anchors: int


class SelectionCancelled(RuntimeError):
    pass


class CaptureError(RuntimeError):
    pass


def import_x11():
    try:
        from Xlib import X, display
        from Xlib.ext import xtest
    except ImportError as exc:
        raise CaptureError("缺少 python3-xlib，请先安装该软件包。") from exc
    return X, display, xtest


def parse_geometry(value: str) -> Region:
    parts = value.split(",")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("区域格式必须为 X,Y,WIDTH,HEIGHT")
    try:
        x, y, width, height = (int(part.strip()) for part in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("区域参数必须全部为整数") from exc
    if width < MIN_REGION_SIZE or height < MIN_REGION_SIZE:
        raise argparse.ArgumentTypeError(
            f"区域宽度和高度必须至少为 {MIN_REGION_SIZE} 像素"
        )
    return Region(x, y, width, height)


def default_output_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return Path.home() / "Pictures" / f"scrollshot-{stamp}.png"


def unique_output_path(path: Path) -> Path:
    path = path.expanduser().resolve()
    if not path.exists():
        return path
    suffix = path.suffix or ".png"
    for index in range(1, 10000):
        candidate = path.with_name(f"{path.stem}-{index:02d}{suffix}")
        if not candidate.exists():
            return candidate
    raise CaptureError("无法生成唯一输出文件名，请更换输出目录。")


def select_region() -> Region:
    if not os.environ.get("DISPLAY"):
        raise CaptureError("未检测到 DISPLAY；只能在 X11 图形会话中运行。")
    try:
        import tkinter as tk
    except ImportError as exc:
        raise CaptureError("缺少 python3-tk，请先安装该软件包。") from exc

    _, display_module, _ = import_x11()
    x_display = display_module.Display()
    screen = x_display.screen()
    screen_width = screen.width_in_pixels
    screen_height = screen.height_in_pixels
    x_display.close()

    state: dict[str, object] = {
        "region": None,
        "cancelled": False,
        "start_x": 0,
        "start_y": 0,
        "rectangle": None,
    }
    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.28)
    root.geometry(f"{screen_width}x{screen_height}+0+0")
    canvas = tk.Canvas(root, background="black", cursor="crosshair", highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    canvas.create_text(
        screen_width // 2,
        36,
        text="拖动鼠标框选滚动区域；按 Esc 取消",
        fill="white",
        font=("Sans", 15, "bold"),
    )

    def on_press(event) -> None:
        state["start_x"] = max(0, min(screen_width - 1, int(event.x)))
        state["start_y"] = max(0, min(screen_height - 1, int(event.y)))
        old = state["rectangle"]
        if isinstance(old, int):
            canvas.delete(old)
        state["rectangle"] = canvas.create_rectangle(
            state["start_x"],
            state["start_y"],
            state["start_x"],
            state["start_y"],
            outline="white",
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
        x1, x2 = sorted((int(state["start_x"]), int(event.x)))
        y1, y2 = sorted((int(state["start_y"]), int(event.y)))
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(screen_width, x2), min(screen_height, y2)
        if x2 - x1 >= MIN_REGION_SIZE and y2 - y1 >= MIN_REGION_SIZE:
            state["region"] = Region(x1, y1, x2 - x1, y2 - y1)
            root.quit()

    def on_cancel(_event=None) -> None:
        state["cancelled"] = True
        root.quit()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.bind("<Escape>", on_cancel)
    root.focus_force()
    try:
        root.mainloop()
    finally:
        root.destroy()

    if state["cancelled"] or not isinstance(state["region"], Region):
        raise SelectionCancelled
    return state["region"]


class X11Controller:
    def __init__(self) -> None:
        if not os.environ.get("DISPLAY"):
            raise CaptureError("未检测到 DISPLAY；只能在 X11 图形会话中运行。")
        self.X, display_module, self.xtest = import_x11()
        self.display = display_module.Display()
        self.root = self.display.screen().root
        pointer = self.root.query_pointer()
        self.original_pointer = (int(pointer.root_x), int(pointer.root_y))

    def close(self) -> None:
        self.display.close()

    def move_pointer(self, x: int, y: int) -> None:
        self.xtest.fake_input(self.display, self.X.MotionNotify, x=x, y=y)
        self.display.sync()

    def move_to_region(self, region: Region) -> None:
        self.move_pointer(region.x + region.width // 2, region.y + region.height // 2)

    def restore_pointer(self) -> None:
        self.move_pointer(*self.original_pointer)

    def scroll_down(self, ticks: int) -> None:
        for _ in range(ticks):
            self.xtest.fake_input(self.display, self.X.ButtonPress, 5)
            self.xtest.fake_input(self.display, self.X.ButtonRelease, 5)
        self.display.sync()

    def capture(self, region: Region) -> np.ndarray:
        geometry = self.root.get_geometry()
        if (
            region.x < 0
            or region.y < 0
            or region.x + region.width > geometry.width
            or region.y + region.height > geometry.height
        ):
            raise CaptureError("截图区域超出 X11 根窗口范围。")
        image = self.root.get_image(
            region.x,
            region.y,
            region.width,
            region.height,
            self.X.ZPixmap,
            0xFFFFFFFF,
        )
        if image is None:
            raise CaptureError("X11 未返回截图数据。")

        # python-xlib 在部分 Python 版本中会返回 Latin-1 字符串。
        data = image.data.encode("latin-1") if isinstance(image.data, str) else image.data
        bytes_per_pixel = len(data) // (region.width * region.height)
        raw = np.frombuffer(data, dtype=np.uint8)
        if bytes_per_pixel == 4:
            frame = raw.reshape(region.height, region.width, 4)[:, :, :3]
        elif bytes_per_pixel == 3:
            frame = raw.reshape(region.height, region.width, 3)
        else:
            raise CaptureError(f"不支持每像素 {bytes_per_pixel} 字节的 X11 格式。")
        return np.ascontiguousarray(frame)


def to_gray(frame: np.ndarray) -> np.ndarray:
    return frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def frames_are_stable(
    previous: np.ndarray,
    current: np.ndarray,
    *,
    pixel_threshold: int = 8,
    changed_ratio_threshold: float = 0.005,
) -> bool:
    if previous.shape != current.shape:
        return False
    height, width = previous.shape[:2]
    mx, my = max(1, int(width * 0.06)), max(1, int(height * 0.04))
    previous_gray = to_gray(previous)[my : height - my, mx : width - mx]
    current_gray = to_gray(current)[my : height - my, mx : width - mx]
    difference = cv2.absdiff(previous_gray, current_gray)
    return (
        float(np.mean(difference > pixel_threshold)) <= changed_ratio_threshold
        and float(np.median(difference)) <= 1.0
    )


def _alignment_error(previous: np.ndarray, current: np.ndarray, shift: int) -> float:
    """使用完整重叠区域评估候选位移，避免周期性布局误匹配。"""

    height, width = previous.shape
    overlap = height - shift
    if overlap <= 0:
        return float("inf")

    # 忽略常见的固定页头、页脚，并降采样控制计算量。
    top = min(int(height * 0.08), max(0, overlap // 4))
    bottom = min(int(height * 0.04), max(0, overlap // 6))
    end = overlap - bottom
    if end - top < 32:
        top, end = 0, overlap

    previous_overlap = previous[shift + top : shift + end]
    current_overlap = current[top:end]
    step_y = max(1, previous_overlap.shape[0] // 320)
    step_x = max(1, width // 280)
    difference = cv2.absdiff(
        previous_overlap[::step_y, ::step_x],
        current_overlap[::step_y, ::step_x],
    )
    return float(np.mean(difference))


def estimate_vertical_shift(
    previous: np.ndarray,
    current: np.ndarray,
    *,
    min_overlap: int = 80,
    min_shift: int = 4,
    score_threshold: float = 0.68,
) -> ShiftMatch | None:
    if previous.shape != current.shape:
        return None
    height, width = previous.shape[:2]
    maximum_shift = height - min_overlap
    if height < min_overlap + min_shift + 32 or width < 64 or maximum_shift <= min_shift:
        return None

    margin_x = max(8, int(width * 0.08))
    previous_gray = cv2.GaussianBlur(
        to_gray(previous)[:, margin_x : width - margin_x], (3, 3), 0
    )
    current_gray = cv2.GaussianBlur(
        to_gray(current)[:, margin_x : width - margin_x], (3, 3), 0
    )
    template_height = min(160, max(48, height // 7))
    peak_threshold = max(0.50, score_threshold - 0.15)
    candidates: list[tuple[int, float]] = []

    for ratio in (0.16, 0.32, 0.48, 0.64, 0.76):
        template_y = int(height * ratio)
        if template_y + template_height >= height:
            continue
        template = current_gray[template_y : template_y + template_height]
        if float(np.std(template)) < 7.0:
            continue
        search_start = template_y + min_shift
        search_end = min(height, template_y + maximum_shift + template_height)
        search = previous_gray[search_start:search_end]
        if search.shape[0] < template_height:
            continue

        scores = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED).ravel()
        anchor_candidates = 0
        for index in np.argsort(scores)[::-1]:
            score = float(scores[index])
            if score < peak_threshold:
                break
            shift = search_start + int(index) - template_y
            if not min_shift <= shift <= maximum_shift:
                continue
            if any(abs(shift - existing) <= 3 for existing, _ in candidates):
                continue
            candidates.append((shift, score))
            anchor_candidates += 1
            # 每个锚点保留多个峰，周期性页面仍能包含真实位移。
            if anchor_candidates >= 6:
                break

    if not candidates:
        return None

    tolerance = max(4, int(height * 0.012))
    centers = sorted({shift for shift, _ in candidates})
    clusters: list[list[tuple[int, float]]] = []
    for center in centers:
        cluster = [item for item in candidates if abs(item[0] - center) <= tolerance]
        if cluster and cluster not in clusters:
            clusters.append(cluster)

    verified: list[tuple[float, int, float, int]] = []
    for cluster in clusters:
        shifts = np.array([shift for shift, _ in cluster], dtype=np.float64)
        scores = np.array([score for _, score in cluster], dtype=np.float64)
        shift = int(round(float(np.average(shifts, weights=scores))))
        if not min_shift <= shift <= maximum_shift:
            continue
        average_score = float(np.mean(scores))
        if len(cluster) == 1 and average_score < max(0.86, score_threshold + 0.12):
            continue
        error = _alignment_error(previous_gray, current_gray, shift)
        verified.append((error, shift, average_score, len(cluster)))

    if not verified:
        return None
    error, shift, score, anchors = min(verified, key=lambda item: item[0])
    if error > 32.0:
        return None
    return ShiftMatch(shift, score, anchors)


def stitch_frames(frames: Sequence[np.ndarray], shifts: Sequence[int]) -> np.ndarray:
    if not frames or len(shifts) != len(frames) - 1:
        raise ValueError("帧数量与位移数量不匹配。")
    width = frames[0].shape[1]
    if any(frame.shape[1] != width for frame in frames):
        raise ValueError("所有截图宽度必须一致。")
    pieces = [frames[0]]
    for frame, shift in zip(frames[1:], shifts):
        if shift <= 0 or shift > frame.shape[0]:
            raise ValueError("检测到无效位移。")
        pieces.append(frame[-shift:])
    return np.ascontiguousarray(np.concatenate(pieces, axis=0))


def save_png(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.png")
    if not cv2.imwrite(str(temporary), image, [cv2.IMWRITE_PNG_COMPRESSION, 3]):
        raise CaptureError(f"无法写入临时文件：{temporary}")
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scrollshot",
        description="Linux X11 自动滚动截图、重叠检测与 PNG 拼接工具",
    )
    parser.add_argument("--version", action="version", version=f"ScrollShot {VERSION}")
    parser.add_argument("-o", "--output", type=Path, help="输出 PNG 路径")
    parser.add_argument("--geometry", type=parse_geometry, help="X,Y,WIDTH,HEIGHT")
    parser.add_argument("--scroll-ticks", type=int, default=6, metavar="N")
    parser.add_argument("--delay", type=float, default=0.55, metavar="SECONDS")
    parser.add_argument("--settle-delay", type=float, default=0.35, metavar="SECONDS")
    parser.add_argument("--max-frames", type=int, default=80, metavar="N")
    parser.add_argument("--min-overlap", type=int, default=80, metavar="PIXELS")
    parser.add_argument("--match-threshold", type=float, default=0.68, metavar="SCORE")
    parser.add_argument("--stable-rounds", type=int, default=2, metavar="N")
    parser.add_argument("--debug-dir", type=Path)
    return parser


def validate_arguments(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    checks = (
        (1 <= args.scroll_ticks <= 30, "--scroll-ticks 必须位于 1 到 30"),
        (0.05 <= args.delay <= 10, "--delay 必须位于 0.05 到 10"),
        (0 <= args.settle_delay <= 10, "--settle-delay 必须位于 0 到 10"),
        (2 <= args.max_frames <= 500, "--max-frames 必须位于 2 到 500"),
        (args.min_overlap >= 32, "--min-overlap 不能小于 32"),
        (0.4 <= args.match_threshold <= 0.99, "--match-threshold 必须位于 0.4 到 0.99"),
        (1 <= args.stable_rounds <= 10, "--stable-rounds 必须位于 1 到 10"),
    )
    for valid, message in checks:
        if not valid:
            parser.error(message)


def run_capture(args: argparse.Namespace) -> tuple[Path, int, int]:
    region = args.geometry if args.geometry is not None else select_region()
    if args.min_overlap >= region.height - 8:
        raise CaptureError("--min-overlap 必须明显小于截图区域高度。")
    output = unique_output_path(args.output or default_output_path())
    debug_dir = args.debug_dir.expanduser().resolve() if args.debug_dir else None
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)

    controller = X11Controller()
    frames: list[np.ndarray] = []
    shifts: list[int] = []
    stable_rounds = 0
    stop_requested = False

    def request_stop(_signum, _frame) -> None:
        nonlocal stop_requested
        stop_requested = True

    previous_sigint = signal.signal(signal.SIGINT, request_stop)
    try:
        controller.move_to_region(region)
        time.sleep(args.settle_delay)
        first = controller.capture(region)
        frames.append(first)
        if debug_dir:
            cv2.imwrite(str(debug_dir / "frame-000.png"), first)
        print(
            f"开始捕获：{region.x},{region.y},{region.width},{region.height}；"
            "终端按 Ctrl+C 可提前保存。",
            flush=True,
        )

        for frame_index in range(1, args.max_frames):
            if stop_requested:
                print("收到停止请求，正在保存已完成结果。", flush=True)
                break
            controller.move_to_region(region)
            controller.scroll_down(args.scroll_ticks)
            time.sleep(args.delay)
            current = controller.capture(region)
            if debug_dir:
                cv2.imwrite(str(debug_dir / f"frame-{frame_index:03d}.png"), current)

            previous = frames[-1]
            if frames_are_stable(previous, current):
                stable_rounds += 1
                print(
                    f"第 {frame_index + 1} 帧：画面未变化 "
                    f"({stable_rounds}/{args.stable_rounds})",
                    flush=True,
                )
                if stable_rounds >= args.stable_rounds:
                    print("已检测到页面底部。", flush=True)
                    break
                continue

            stable_rounds = 0
            match = estimate_vertical_shift(
                previous,
                current,
                min_overlap=args.min_overlap,
                score_threshold=args.match_threshold,
            )
            if match is None:
                print("未找到可靠重叠区域，保存此前结果。", file=sys.stderr)
                break
            frames.append(current)
            shifts.append(match.shift)
            print(
                f"第 {frame_index + 1} 帧：新增 {match.shift} 像素，"
                f"置信度 {match.score:.3f}，锚点 {match.anchors}",
                flush=True,
            )
        else:
            print(f"已达到最大帧数 {args.max_frames}。", file=sys.stderr)

        stitched = stitch_frames(frames, shifts)
        save_png(output, stitched)
        return output, len(frames), stitched.shape[0]
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        try:
            controller.restore_pointer()
        finally:
            controller.close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    validate_arguments(parser, args)
    try:
        output, frame_count, height = run_capture(args)
    except SelectionCancelled:
        print("已取消。")
        return 130
    except CaptureError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("已中断。", file=sys.stderr)
        return 130
    print(f"完成：{output}")
    print(f"已拼接 {frame_count} 帧，最终高度 {height} 像素。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
