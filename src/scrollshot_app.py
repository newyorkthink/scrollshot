#!/usr/bin/env python3
"""ScrollShot AppImage 与本地安装共用的稳定启动入口。"""

from __future__ import annotations

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


def _notify_capture_saved(output: Path) -> None:
    """截图已成功保存时发送桌面通知；通知失败不能影响截图结果。"""

    notify_send = shutil.which("notify-send")
    if notify_send is None:
        return

    try:
        subprocess.run(
            [
                notify_send,
                "--app-name=ScrollShot",
                "--icon=camera-photo",
                "--expire-time=5000",
                "ScrollShot 截图已保存",
                f"保存位置：{output}",
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2.0,
        )
    except (OSError, subprocess.SubprocessError):
        return


# 稳定基线：先保存 core 原始实现，再按既定顺序叠加增强层。
# 不要调换下面几层的顺序；后层依赖前层提供的稳定回退行为。
_interactive_selector = create_select_region(core)
_core_estimate_vertical_shift = core.estimate_vertical_shift
_core_stitch_frames = core.stitch_frames
core.select_region = _interactive_selector

# 位移检测链：
# 原始匹配 -> 重复纹理结构校验 -> 浏览器 / 整窗 GUI 保守回退匹配。
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

# 捕获运行层统一处理自适应重叠、Esc 提前结束、工作区切换保护和底部判定。
_capture_runner = create_capture_runner(
    core,
    effective_min_overlap,
)


# 捕获函数完全结束并恢复指针后，再发送“已保存”通知。
def _run_capture_with_notification(args):
    result = _capture_runner(args)
    _notify_capture_saved(result[0])
    return result


core.run_capture = _run_capture_with_notification


if __name__ == "__main__":
    raise SystemExit(core.main())
