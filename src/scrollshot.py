#!/usr/bin/env python3
"""ScrollShot: automatic scrolling screenshots for Linux X11."""

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
        "Missing dependencies: numpy, opencv-python, python-xlib and tkinter.",
        file=sys.stderr,
    )
    raise SystemExit(3) from exc

VERSION = "0.2.0"
MIN_REGION_SIZE = 32
SELECTION_PREVIEW_BRIGHTNESS = 0.48


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
    content_top: int = 0
    content_bottom: int = 0
    alignment_error: float = 0.0


class SelectionCancelled(RuntimeError):
    pass


class CaptureError(RuntimeError):
    pass


def import_x11():
    try:
        from Xlib import X, display
        from Xlib.ext import xtest
    except ImportError as exc:
        raise CaptureError("python-xlib is required.") from exc
    return X, display, xtest


def parse_geometry(value: str) -> Region:
    parts = value.split(",")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("geometry must be X,Y,WIDTH,HEIGHT")
    try:
        x, y, width, height = (int(part.strip()) for part in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("geometry values must be integers") from exc
    if width < MIN_REGION_SIZE or height < MIN_REGION_SIZE:
        raise argparse.ArgumentTypeError(
            f"width and height must be at least {MIN_REGION_SIZE} pixels"
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
    raise CaptureError("unable to generate a unique output filename")


def decode_x11_image(data: bytes | str, width: int, height: int) -> np.ndarray:
    if width <= 0 or height <= 0:
        raise CaptureError("X11 returned invalid image dimensions")

    raw_data = data.encode("latin-1") if isinstance(data, str) else data
    pixel_count = width * height
    if len(raw_data) % pixel_count != 0:
        raise CaptureError("X11 returned an invalid image buffer")

    bytes_per_pixel = len(raw_data) // pixel_count
    raw = np.frombuffer(raw_data, dtype=np.uint8)
    if bytes_per_pixel == 4:
        frame = raw.reshape(height, width, 4)[:, :, :3]
    elif bytes_per_pixel == 3:
        frame = raw.reshape(height, width, 3)
    else:
        raise CaptureError(f"unsupported X11 pixel size: {bytes_per_pixel}")
    return np.ascontiguousarray(frame)


def build_selection_preview(frame: np.ndarray) -> np.ndarray:
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise CaptureError("selection preview requires a three-channel image")
    preview = np.clip(
        frame.astype(np.float32) * SELECTION_PREVIEW_BRIGHTNESS,
        0,
        255,
    ).astype(np.uint8)
    return np.ascontiguousarray(preview)


def frame_to_ppm(frame: np.ndarray) -> bytes:
    if frame.ndim != 3 or frame.shape[2] != 3:
        raise CaptureError("PPM preview requires a three-channel image")
    height, width = frame.shape[:2]
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    header = f"P6\n{width} {height}\n255\n".encode("ascii")
    return header + rgb.tobytes()


def capture_desktop_frame() -> np.ndarray:
    if not os.environ.get("DISPLAY"):
        raise CaptureError("DISPLAY is not set; X11 is required")
    X, display_module, _ = import_x11()
    x_display = display_module.Display()
    try:
        screen = x_display.screen()
        width = int(screen.width_in_pixels)
        height = int(screen.height_in_pixels)
        image = screen.root.get_image(
            0,
            0,
            width,
            height,
            X.ZPixmap,
            0xFFFFFFFF,
        )
        if image is None:
            raise CaptureError("X11 did not return the desktop image")
        return decode_x11_image(image.data, width, height)
    finally:
        x_display.close()


def select_region() -> Region:
    if not os.environ.get("DISPLAY"):
        raise CaptureError("DISPLAY is not set; X11 is required")
    try:
        import tkinter as tk
    except ImportError as exc:
        raise CaptureError("tkinter is required") from exc

    desktop_frame = capture_desktop_frame()
    screen_height, screen_width = desktop_frame.shape[:2]
    preview_ppm = frame_to_ppm(build_selection_preview(desktop_frame))

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
    root.geometry(f"{screen_width}x{screen_height}+0+0")
    canvas = tk.Canvas(root, cursor="crosshair", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    background_photo = tk.PhotoImage(data=preview_ppm, format="PPM")
    canvas.create_image(0, 0, image=background_photo, anchor="nw")
    canvas.background_photo = background_photo

    notice_width = min(560, max(360, screen_width - 40))
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
        text="拖动框选滚动区域 / Drag to select · Esc 取消 / Cancel",
        fill="white",
        font=("Sans", 14, "bold"),
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
            raise CaptureError("DISPLAY is not set; X11 is required")
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
            raise CaptureError("capture region is outside the X11 root window")
        image = self.root.get_image(
            region.x,
            region.y,
            region.width,
            region.height,
            self.X.ZPixmap,
            0xFFFFFFFF,
        )
        if image is None:
            raise CaptureError("X11 did not return image data")
        return decode_x11_image(image.data, region.width, region.height)


def to_gray(frame: np.ndarray) -> np.ndarray:
    return frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def frames_are_stable(
    previous: np.ndarray,
    current: np.ndarray,
    *,
    pixel_threshold: int = 8,
    changed_ratio_threshold: float = 0.004,
) -> bool:
    if previous.shape != current.shape:
        return False
    height, width = previous.shape[:2]
    mx, my = max(1, int(width * 0.05)), max(1, int(height * 0.03))
    previous_gray = to_gray(previous)[my : height - my, mx : width - mx]
    current_gray = to_gray(current)[my : height - my, mx : width - mx]
    difference = cv2.absdiff(previous_gray, current_gray)
    changed_ratio = float(np.mean(difference > pixel_threshold))
    return changed_ratio <= changed_ratio_threshold and float(np.median(difference)) <= 1.0


def _smooth_1d(values: np.ndarray, window: int) -> np.ndarray:
    if values.ndim != 1:
        raise ValueError("_smooth_1d expects one-dimensional input")
    window = max(1, min(int(window), len(values)))
    if window % 2 == 0:
        window = max(1, window - 1)
    if window == 1:
        return values.astype(np.float32, copy=True)
    kernel = np.full(window, 1.0 / window, dtype=np.float32)
    return np.convolve(values.astype(np.float32), kernel, mode="same")


def _largest_true_segment(mask: np.ndarray) -> tuple[int, int] | None:
    best: tuple[int, int] | None = None
    start: int | None = None
    for index, value in enumerate(mask.tolist() + [False]):
        if value and start is None:
            start = index
        elif not value and start is not None:
            if best is None or index - start > best[1] - best[0]:
                best = (start, index)
            start = None
    return best


def detect_motion_band(
    previous: np.ndarray,
    current: np.ndarray,
    *,
    minimum_ratio: float = 0.16,
) -> tuple[int, int] | None:
    """Return the largest vertically contiguous region that visibly changed."""

    if previous.shape != current.shape:
        return None
    height, width = previous.shape[:2]
    if height < 64 or width < 64:
        return None

    margin_x = max(6, int(width * 0.05))
    previous_gray = to_gray(previous)[:, margin_x : width - margin_x]
    current_gray = to_gray(current)[:, margin_x : width - margin_x]
    row_error = np.mean(
        cv2.absdiff(previous_gray, current_gray).astype(np.float32),
        axis=1,
    )
    smooth = _smooth_1d(row_error, max(7, height // 70))
    low = float(np.percentile(smooth, 10))
    high = float(np.percentile(smooth, 90))
    if high < 2.5:
        return None

    threshold = min(8.0, max(2.5, low + 0.20 * max(0.0, high - low)))
    mask = (smooth > threshold).astype(np.uint8).reshape(height, 1)

    close_size = max(9, int(height * 0.055))
    if close_size % 2 == 0:
        close_size += 1
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_CLOSE,
        np.ones((close_size, 1), dtype=np.uint8),
    )
    mask = cv2.morphologyEx(
        mask,
        cv2.MORPH_OPEN,
        np.ones((5, 1), dtype=np.uint8),
    ).ravel().astype(bool)

    segment = _largest_true_segment(mask)
    if segment is None:
        return None
    top, bottom = segment

    relaxed_threshold = max(1.5, threshold * 0.55)
    while top > 0 and smooth[top - 1] > relaxed_threshold:
        top -= 1
    while bottom < height and smooth[bottom] > relaxed_threshold:
        bottom += 1

    minimum_height = max(64, int(height * minimum_ratio))
    if bottom - top < minimum_height:
        return None
    return top, bottom


def _candidate_alignment(
    previous_gray: np.ndarray,
    current_gray: np.ndarray,
    shift: int,
    band: tuple[int, int],
) -> tuple[float, float, int] | None:
    height = previous_gray.shape[0]
    top, bottom = band
    compare_end = min(bottom, height - shift)
    compare_height = compare_end - top
    if compare_height < max(48, int((bottom - top) * 0.20)):
        return None

    previous_aligned = previous_gray[top + shift : compare_end + shift]
    current_aligned = current_gray[top:compare_end]
    previous_static = previous_gray[top:compare_end]

    step_y = max(1, compare_height // 300)
    step_x = max(1, previous_gray.shape[1] // 260)
    aligned_difference = cv2.absdiff(
        previous_aligned[::step_y, ::step_x],
        current_aligned[::step_y, ::step_x],
    )
    static_difference = cv2.absdiff(
        previous_static[::step_y, ::step_x],
        current_aligned[::step_y, ::step_x],
    )
    aligned_error = float(np.mean(aligned_difference))
    static_error = float(np.mean(static_difference))
    return aligned_error, static_error, compare_height


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

    band = detect_motion_band(previous, current)
    if band is None:
        return None
    content_top, content_bottom = band
    content_height = content_bottom - content_top
    if maximum_shift <= min_shift:
        return None

    margin_x = max(8, int(width * 0.08))
    previous_gray = cv2.GaussianBlur(
        to_gray(previous)[:, margin_x : width - margin_x],
        (3, 3),
        0,
    )
    current_gray = cv2.GaussianBlur(
        to_gray(current)[:, margin_x : width - margin_x],
        (3, 3),
        0,
    )

    template_height = min(140, max(40, content_height // 7))
    peak_threshold = max(0.50, score_threshold - 0.16)
    candidates: list[tuple[int, float]] = []

    for ratio in (0.10, 0.26, 0.42, 0.58, 0.74):
        template_y = content_top + int(max(0, content_height - template_height) * ratio)
        if template_y + template_height > content_bottom:
            continue
        template = current_gray[template_y : template_y + template_height]
        if float(np.std(template)) < 6.0:
            continue

        search_start = template_y + min_shift
        search_end = min(
            height,
            template_y + maximum_shift + template_height,
        )
        search = previous_gray[search_start:search_end]
        if search.shape[0] < template_height:
            continue

        scores = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED).ravel()
        kept = 0
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
            kept += 1
            if kept >= 6:
                break

    if not candidates:
        return None

    tolerance = max(4, int(height * 0.012))
    verified: list[tuple[float, float, int, float, int]] = []
    for shift, score in candidates:
        anchors = sum(1 for other_shift, _ in candidates if abs(other_shift - shift) <= tolerance)
        result = _candidate_alignment(previous_gray, current_gray, shift, band)
        if result is None:
            continue
        aligned_error, static_error, _compare_height = result

        if aligned_error > 30.0:
            continue
        improvement = static_error - aligned_error
        if improvement < 2.0 and aligned_error > 7.0:
            continue
        if anchors == 1 and score < max(0.84, score_threshold + 0.10):
            continue

        quality = aligned_error - min(12.0, max(0.0, improvement)) * 0.20
        verified.append((quality, aligned_error, shift, score, anchors))

    if not verified:
        return None

    _, aligned_error, shift, score, anchors = min(verified, key=lambda item: item[0])
    return ShiftMatch(
        shift=shift,
        score=score,
        anchors=anchors,
        content_top=content_top,
        content_bottom=content_bottom,
        alignment_error=aligned_error,
    )


def stitch_frames(
    frames: Sequence[np.ndarray],
    shifts: Sequence[int | ShiftMatch],
) -> np.ndarray:
    if not frames or len(shifts) != len(frames) - 1:
        raise ValueError("frame and shift counts do not match")
    width = frames[0].shape[1]
    height = frames[0].shape[0]
    if any(frame.shape[:2] != (height, width) for frame in frames):
        raise ValueError("all frames must have the same dimensions")

    if not shifts:
        return np.ascontiguousarray(frames[0])

    if all(isinstance(item, int) for item in shifts):
        pieces = [frames[0]]
        for frame, raw_shift in zip(frames[1:], shifts):
            shift = int(raw_shift)
            if shift <= 0 or shift > frame.shape[0]:
                raise ValueError("invalid shift")
            pieces.append(frame[-shift:])
        return np.ascontiguousarray(np.concatenate(pieces, axis=0))

    matches = [item for item in shifts if isinstance(item, ShiftMatch)]
    if len(matches) != len(shifts):
        raise ValueError("shifts must be all integers or all ShiftMatch objects")

    top = max(match.content_top for match in matches)
    bottom = min(match.content_bottom for match in matches)
    maximum_shift = max(match.shift for match in matches)
    if bottom - top <= maximum_shift + 24:
        raise ValueError("detected scrolling content band is too small")

    pieces = [frames[0][:top], frames[0][top:bottom]]
    for frame, match in zip(frames[1:], matches):
        if match.shift <= 0 or match.shift >= bottom - top:
            raise ValueError("invalid shift")
        pieces.append(frame[bottom - match.shift : bottom])
    pieces.append(frames[-1][bottom:])
    non_empty = [piece for piece in pieces if piece.size]
    return np.ascontiguousarray(np.concatenate(non_empty, axis=0))


def save_png(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.png")
    if not cv2.imwrite(str(temporary), image, [cv2.IMWRITE_PNG_COMPRESSION, 3]):
        raise CaptureError(f"unable to write temporary file: {temporary}")
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scrollshot",
        description="Automatic scrolling screenshots for Linux X11",
    )
    parser.add_argument("--version", action="version", version=f"ScrollShot {VERSION}")
    parser.add_argument("-o", "--output", type=Path, help="output PNG path")
    parser.add_argument("--geometry", type=parse_geometry, help="X,Y,WIDTH,HEIGHT")
    parser.add_argument("--scroll-ticks", type=int, default=3, metavar="N")
    parser.add_argument("--delay", type=float, default=0.55, metavar="SECONDS")
    parser.add_argument("--settle-delay", type=float, default=0.35, metavar="SECONDS")
    parser.add_argument("--max-frames", type=int, default=120, metavar="N")
    parser.add_argument("--min-overlap", type=int, default=80, metavar="PIXELS")
    parser.add_argument("--match-threshold", type=float, default=0.68, metavar="SCORE")
    parser.add_argument("--stable-rounds", type=int, default=2, metavar="N")
    parser.add_argument("--debug-dir", type=Path)
    return parser


def validate_arguments(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    checks = (
        (1 <= args.scroll_ticks <= 20, "--scroll-ticks must be between 1 and 20"),
        (0.05 <= args.delay <= 10, "--delay must be between 0.05 and 10"),
        (0 <= args.settle_delay <= 10, "--settle-delay must be between 0 and 10"),
        (2 <= args.max_frames <= 500, "--max-frames must be between 2 and 500"),
        (args.min_overlap >= 32, "--min-overlap must be at least 32"),
        (0.4 <= args.match_threshold <= 0.99, "--match-threshold must be between 0.4 and 0.99"),
        (1 <= args.stable_rounds <= 10, "--stable-rounds must be between 1 and 10"),
    )
    for valid, message in checks:
        if not valid:
            parser.error(message)


def run_capture(args: argparse.Namespace) -> tuple[Path, int, int]:
    region = args.geometry if args.geometry is not None else select_region()
    if args.min_overlap >= region.height - 8:
        raise CaptureError("--min-overlap must be smaller than the capture height")
    output = unique_output_path(args.output or default_output_path())
    debug_dir = args.debug_dir.expanduser().resolve() if args.debug_dir else None
    if debug_dir:
        debug_dir.mkdir(parents=True, exist_ok=True)

    controller = X11Controller()
    frames: list[np.ndarray] = []
    matches: list[ShiftMatch] = []
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

        for frame_index in range(1, args.max_frames):
            if stop_requested:
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
                if stable_rounds >= args.stable_rounds:
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
                break
            frames.append(current)
            matches.append(match)

        stitched = stitch_frames(frames, matches)
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
        print("Cancelled.")
        return 130
    except CaptureError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    print(f"Saved: {output}")
    print(f"Frames: {frame_count}; height: {height}px")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
