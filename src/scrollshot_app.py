#!/usr/bin/env python3
"""ScrollShot 最终稳定启动入口（AppImage 与源码安装共用）。

2026-08-07 稳定基线：保持框选、位移匹配、稳健拼接、捕获运行控制和
Freedesktop 桌面通知的既定装配顺序。后层依赖前层的保守回退行为，
没有完整回归检查时不要重排、合并或绕过这些包装层。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# 本地 install.sh 会把辅助模块安装到 ~/.local/lib/scrollshot。
# AppImage / PyInstaller 环境不存在该目录时保持原有导入路径，不额外注入。
local_library = Path(__file__).resolve().parent.parent / "lib" / "scrollshot"
if local_library.is_dir():
    sys.path.insert(0, str(local_library))

import scrollshot as core
from capture_options import effective_min_overlap
from capture_runtime import create_capture_runner
from fallback_match import create_fallback_estimator
from resilient_stitch import create_resilient_stitcher
from seam_cleanup import create_seam_cleaning_stitcher
from selection_guides import create_select_region
from structural_match import create_structural_estimator


def _notification_environment() -> dict[str, str]:
    """为宿主机通知程序构造独立于启动器/AppImage 的用户会话环境。"""

    environment = os.environ.copy()

    # notify-send 是宿主机程序，不应继承 Kando/AppImage/PyInstaller 注入的动态库路径。
    # 这里直接清理，而不是恢复 LD_LIBRARY_PATH_ORIG；后者本身也可能来自上层启动器。
    for variable in ("LD_LIBRARY_PATH", "LD_LIBRARY_PATH_ORIG", "LD_PRELOAD"):
        environment.pop(variable, None)

    # 不信任启动器继承下来的 DBUS_SESSION_BUS_ADDRESS。
    # 优先根据有效的 XDG_RUNTIME_DIR 重新构造；如果它不存在或无 bus，
    # 再使用 Linux 用户会话常见的 /run/user/$UID/bus。
    runtime_dirs: list[Path] = []
    runtime_dir_value = environment.get("XDG_RUNTIME_DIR")
    if runtime_dir_value:
        runtime_dirs.append(Path(runtime_dir_value))

    standard_runtime_dir = Path("/run/user") / str(os.getuid())
    if standard_runtime_dir not in runtime_dirs:
        runtime_dirs.append(standard_runtime_dir)

    for runtime_dir in runtime_dirs:
        session_bus = runtime_dir / "bus"
        if not session_bus.is_socket():
            continue
        environment["XDG_RUNTIME_DIR"] = str(runtime_dir)
        environment["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={session_bus}"
        break

    return environment


def _find_notify_send(environment: dict[str, str]) -> str | None:
    """优先使用宿主机系统 notify-send，再回退到用户 PATH。"""

    # 先检查宿主机常见系统位置，避免启动器/AppImage 修改 PATH 后命中其内部程序。
    for candidate in (
        Path("/usr/bin/notify-send"),
        Path("/bin/notify-send"),
        Path("/usr/local/bin/notify-send"),
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)

    return shutil.which("notify-send", path=environment.get("PATH"))


def _notify_capture_saved(output: Path) -> None:
    """通过 Freedesktop notify-send 发送保存完成通知；失败不影响截图结果。"""

    environment = _notification_environment()
    notify_send = _find_notify_send(environment)
    if notify_send is None:
        return

    try:
        # 只使用 notify-send 最基础、兼容性最高的标题和正文参数。
        # 不绑定 Dunst；任何实现 org.freedesktop.Notifications 的通知服务均可接收。
        subprocess.run(
            [
                notify_send,
                "ScrollShot",
                f"Saved: {output}",
            ],
            check=False,
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3.0,
        )
    except (OSError, subprocess.SubprocessError):
        return


def _host_input_environment() -> dict[str, str]:
    """为宿主机输入工具清理 AppImage/PyInstaller 动态库环境。"""

    environment = os.environ.copy()
    for variable in ("LD_LIBRARY_PATH", "LD_LIBRARY_PATH_ORIG", "LD_PRELOAD"):
        environment.pop(variable, None)
    return environment


def _find_ydotool(environment: dict[str, str]) -> str | None:
    """优先使用宿主机 ydotool，避免命中 AppImage 内部路径。"""

    for candidate in (
        Path("/usr/bin/ydotool"),
        Path("/bin/ydotool"),
        Path("/usr/local/bin/ydotool"),
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)

    return shutil.which("ydotool", path=environment.get("PATH"))


def _window_classes_under_pointer(controller) -> tuple[str, ...]:
    """读取指针下 X11 客户端及其父窗口的 WM_CLASS。"""

    try:
        pointer = controller.root.query_pointer()
        window = getattr(pointer, "child", None)
    except Exception:
        return ()

    classes: list[str] = []
    visited: set[int] = set()
    while window is not None:
        marker = id(window)
        if marker in visited:
            break
        visited.add(marker)

        try:
            wm_class = window.get_wm_class()
        except Exception:
            wm_class = None
        if wm_class:
            classes.extend(str(value).casefold() for value in wm_class if value)

        if window == controller.root:
            break
        try:
            window = window.query_tree().parent
        except Exception:
            break

    return tuple(classes)


def _is_kitty_target(controller) -> bool:
    """仅在实际指针目标属于 Kitty 时切换到真实 uinput 滚轮。"""

    return any("kitty" in value for value in _window_classes_under_pointer(controller))


def _ydotool_wheel(ticks: int, *, upward: bool) -> None:
    """通过宿主机 ydotoold/uinput 发送真实纵向滚轮事件。"""

    ticks = max(1, int(ticks))
    environment = _host_input_environment()
    ydotool = _find_ydotool(environment)
    if ydotool is None:
        raise core.CaptureError(
            "Kitty scrolling requires host ydotool and a running ydotoold"
        )

    # Linux REL_WHEEL：正值向上，负值向下。
    delta = ticks if upward else -ticks
    try:
        result = subprocess.run(
            [
                ydotool,
                "mousemove",
                "--wheel",
                "-x",
                "0",
                "-y",
                str(delta),
            ],
            check=False,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=3.0,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise core.CaptureError(
            "Kitty scrolling requires a running ydotoold with /dev/uinput access"
        ) from exc

    if result.returncode != 0:
        detail = (result.stderr or "").strip()
        message = "Kitty scrolling requires a running ydotoold with /dev/uinput access"
        if detail:
            message = f"{message}: {detail}"
        raise core.CaptureError(message)


def _scroll_up(controller, ticks: int) -> None:
    """终端向上模式：Kitty 用 uinput；其他 X11 目标继续使用 Button 4。"""

    if _is_kitty_target(controller):
        _ydotool_wheel(ticks, upward=True)
        return

    # 保留 Alacritty 等现有 X11 终端可接受的传统 Button 4 路径。
    for _ in range(ticks):
        controller.xtest.fake_input(controller.display, controller.X.ButtonPress, 4)
        controller.xtest.fake_input(controller.display, controller.X.ButtonRelease, 4)
    controller.display.sync()


# 普通向下滚动保持现有已验证实现；仅 Kitty 目标切换到真实 uinput 滚轮。
_core_scroll_down = core.X11Controller.scroll_down


def _scroll_down(controller, ticks: int) -> None:
    """Kitty 使用 uinput 向下滚动，其他窗口逐字保留既有 scroll_down 行为。"""

    if _is_kitty_target(controller):
        _ydotool_wheel(ticks, upward=False)
        return
    _core_scroll_down(controller, ticks)


core.X11Controller.scroll_down = _scroll_down


# 终端历史截图是独立的附加模式；默认向下滚动参数和行为保持不变。
# 参数只在最终装配入口扩展，因此 AppImage 与 install.sh 安装入口都可直接使用。
_core_build_parser = core.build_parser


def _build_parser_with_scroll_up():
    parser = _core_build_parser()
    parser.add_argument(
        "--scroll-up",
        action="store_true",
        help="scroll upward for terminal history and stitch the result top-to-bottom",
    )
    return parser


core.build_parser = _build_parser_with_scroll_up
core.scroll_up = _scroll_up


# 最终稳定装配顺序（2026-08-07）：
# 1. 框选层。
# 2. 原始位移匹配 -> 重复布局结构校验 -> 浏览器/PDF/整窗 GUI 回退匹配。
# 3. 原始拼接 -> 稳健拼接 -> 已知拼接点的保守清理。
# 4. 捕获运行层。
# 5. PNG 保存成功后的桌面通知。
# 后层依赖前层提供的稳定回退行为，不要调换下面几层的顺序。
_interactive_selector = create_select_region(core)
_core_estimate_vertical_shift = core.estimate_vertical_shift
_core_stitch_frames = core.stitch_frames
core.select_region = _interactive_selector

# 位移检测链：
# 原始匹配 -> 重复纹理结构校验 -> 浏览器 / PDF / 整窗 GUI 保守回退匹配。
_structural_estimator = create_structural_estimator(
    core,
    _core_estimate_vertical_shift,
)
core.estimate_vertical_shift = create_fallback_estimator(
    core,
    _structural_estimator,
)

# 拼接链：
# 原始拼接 -> 浏览器固定侧栏 / 滚动条 / PDF GUI 固定边界处理
# -> 已知拼接点的保守黑线清理。
_resilient_stitcher = create_resilient_stitcher(
    core,
    _core_stitch_frames,
)
core.stitch_frames = create_seam_cleaning_stitcher(
    core,
    _resilient_stitcher,
)

# 捕获运行层统一处理自适应重叠、Esc 提前结束、工作区切换保护、
# 底部判定、普通重试和 PDF/重复版式的小步恢复。
_capture_runner = create_capture_runner(
    core,
    effective_min_overlap,
)


# 只有捕获函数成功完成并返回保存路径后才发送“已保存”通知。
# 通知失败属于附加提示失败，不能改变截图成功结果。
def _run_capture_with_notification(args):
    result = _capture_runner(args)
    _notify_capture_saved(result[0])
    return result


core.run_capture = _run_capture_with_notification


if __name__ == "__main__":
    raise SystemExit(core.main())
