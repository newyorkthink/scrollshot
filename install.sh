#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_BIN_DIR="${HOME}/.local/bin"
INSTALL_LIB_DIR="${HOME}/.local/lib/scrollshot"
TARGET="${INSTALL_BIN_DIR}/scrollshot"

# 使用 apt 安装源码运行所需的 Python 与 X11 依赖
sudo apt-get install -y python3 python3-numpy python3-opencv python3-xlib python3-tk

# 创建当前用户的可执行文件目录与 ScrollShot 模块目录
install -d -m 0755 "${INSTALL_BIN_DIR}" "${INSTALL_LIB_DIR}"

# 安装 ScrollShot 核心模块、捕获参数模块、指针辅助模块与 X11 框选模块
install -m 0644 "${SCRIPT_DIR}/src/scrollshot.py" "${INSTALL_LIB_DIR}/scrollshot.py"
install -m 0644 "${SCRIPT_DIR}/src/capture_options.py" "${INSTALL_LIB_DIR}/capture_options.py"
install -m 0644 "${SCRIPT_DIR}/src/pointer_guides.py" "${INSTALL_LIB_DIR}/pointer_guides.py"
install -m 0644 "${SCRIPT_DIR}/src/selection_ui.py" "${INSTALL_LIB_DIR}/selection_ui.py"
install -m 0644 "${SCRIPT_DIR}/src/selection_guides.py" "${INSTALL_LIB_DIR}/selection_guides.py"

# 安装结构匹配、浏览器回退匹配、稳健拼接与拼接线清理模块
install -m 0644 "${SCRIPT_DIR}/src/structural_match.py" "${INSTALL_LIB_DIR}/structural_match.py"
install -m 0644 "${SCRIPT_DIR}/src/fallback_match.py" "${INSTALL_LIB_DIR}/fallback_match.py"
install -m 0644 "${SCRIPT_DIR}/src/resilient_stitch.py" "${INSTALL_LIB_DIR}/resilient_stitch.py"
install -m 0644 "${SCRIPT_DIR}/src/seam_cleanup.py" "${INSTALL_LIB_DIR}/seam_cleanup.py"

# 安装捕获运行控制模块，提供浏览器加载重试与滚动过程中 Esc 提前结束保存
install -m 0644 "${SCRIPT_DIR}/src/capture_runtime.py" "${INSTALL_LIB_DIR}/capture_runtime.py"

# 安装启动入口，运行时自动加载 ~/.local/lib/scrollshot 中的模块
install -m 0755 "${SCRIPT_DIR}/src/scrollshot_app.py" "${TARGET}"

# 检查安装后的程序是否能够正常启动并输出版本
"${TARGET}" --version

printf '\n安装完成：%s\n' "${TARGET}"
printf '启动命令：scrollshot\n'
printf '如果终端找不到命令，请确认 ~/.local/bin 已加入 PATH。\n'
