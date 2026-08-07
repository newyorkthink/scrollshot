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

# 安装 ScrollShot 核心模块与 X11 框选模块
install -m 0644 "${SCRIPT_DIR}/src/scrollshot.py" "${INSTALL_LIB_DIR}/scrollshot.py"
install -m 0644 "${SCRIPT_DIR}/src/selection_ui.py" "${INSTALL_LIB_DIR}/selection_ui.py"

# 安装启动入口，运行时自动加载 ~/.local/lib/scrollshot 中的模块
install -m 0755 "${SCRIPT_DIR}/src/scrollshot_app.py" "${TARGET}"

# 检查安装后的程序是否能够正常启动并输出版本
"${TARGET}" --version

printf '\n安装完成：%s\n' "${TARGET}"
printf '启动命令：scrollshot\n'
printf '如果终端找不到命令，请确认 ~/.local/bin 已加入 PATH。\n'
