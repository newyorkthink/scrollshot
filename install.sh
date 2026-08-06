#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${HOME}/.local/bin"
TARGET="${INSTALL_DIR}/scrollshot"

# 安装 ScrollShot 在 Kali Linux 下运行所需的 Python 与 X11 依赖
sudo apt-get install -y python3 python3-numpy python3-opencv python3-xlib python3-tk

# 创建当前用户的本地可执行文件目录
install -d -m 0755 "${INSTALL_DIR}"

# 安装 ScrollShot 主程序，不覆盖仓库中的源文件
install -m 0755 "${SCRIPT_DIR}/src/scrollshot.py" "${TARGET}"

# 检查安装后的程序是否能够正常启动并输出版本
"${TARGET}" --version

printf '\n安装完成：%s\n' "${TARGET}"
printf '启动命令：scrollshot\n'
printf '如果终端找不到命令，请确认 ~/.local/bin 已加入 PATH。\n'
