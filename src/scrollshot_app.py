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
    """为宿主机通知程序构造不受 AppImage/PyInstaller 污染的会话环境。"""

    environment = os.environ.copy()

    # 稳定通知基线：PyInstaller 会修改 LD_LIBRARY_PATH。调用宿主机 notify-send
    # 时必须恢复原值，否则系统程序可能误加载 AppImage 内的动态库并静默失败。
    if getattr(sys, "frozen", False):
        original_library_path = environment.get("LD_LIBRARY_PATH_ORIG")
        if original_library_path:
            environment["LD_LIBRARY_PATH"] = original_library_path
        else:
            environment.pop("LD_LIBRARY_PATH", None)

    # 启动器可能不传 DBUS_SESSION_BUS_ADDRESS 或 XDG_RUNTIME_DIR。
    # 已有 session bus 地址始终优先保留；否则先用 XDG_RUNTIME_DIR，
    # 再回退到 Linux 用户会话的标准 /run/user/$UID/bus。
    if not environment.get("DBUS_SESSION_BUS_ADDRESS"):
        runtime_dir_value = environment.get("XDG_RUNTIME_DIR")
        runtime_dir = (
            Path(runtime_dir_value)
            if runtime_dir_value
            else Path("/run/user") / str(os.getuid())
        )
        session_bus = runtime_dir / "bus"
        if session_bus.is_socket():
            environment.setdefault("XDG_RUNTIME_DIR", str(runtime_dir))
            environment["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path={session_bus}"

    return environment


def _find_notify_send(environment: dict[str, str]) -> str | None:
    """优先按用户 PATH 查找 notify-send，再兼容常见系统安装位置。"""

    notify_send = shutil.which("notify-send", path=environment.get("PATH"))
    if notify_send is not None:
        return notify_send

    for candidate in (
        Path("/usr/bin/notify-send"),
        Path("/usr/local/bin/notify-send"),
        Path("/bin/notify-send"),
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


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
