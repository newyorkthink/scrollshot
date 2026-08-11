#!/usr/bin/env python3
"""补齐 Alacritty + Lazygit 向上滚动，同时保持既有终端分流不变。"""

from __future__ import annotations

from pathlib import Path
from types import ModuleType
from typing import Callable

import terminal_scroll as _base


class _TerminalLazygitBridge(_base.TmuxScrollBridge):
    """仅把向上的 Lazygit 特判从 Kitty 扩展到 Kitty/Alacritty。"""

    def _kitty_lazygit_state(self, controller):
        # 原实现只用 KITTY_CLASS_MARKERS，导致 Alacritty + Lazygit 在
        # --scroll-up 时错误进入 tmux copy-mode，Lazygit 自身视口不再滚动。
        # 向下路径仍由 terminal_scroll.py 自己判断 Kitty，不受这里影响。
        terminal_pid = self._terminal_pid_under_pointer(
            controller,
            _base.TERMINAL_CLASS_MARKERS,
        )
        if terminal_pid is None:
            return None

        state = self._pane_state_for_pid(terminal_pid)
        if state is None or state.pane_mode == "copy-mode" or not state.alternate_on:
            return None

        command = self._run(
            "display-message",
            "-t",
            state.pane_id,
            "-p",
            "#{pane_current_command}",
            allow_failure=True,
        )
        if not command or Path(command.strip()).name.casefold() != "lazygit":
            return None
        return state


def configure_terminal_scrolling(
    core: ModuleType,
    capture_runner: Callable,
) -> Callable:
    """使用现有稳定终端实现，只扩展 Lazygit 向上的终端识别范围。"""

    original_bridge = _base.TmuxScrollBridge
    _base.TmuxScrollBridge = _TerminalLazygitBridge
    try:
        # configure_terminal_scrolling 会在这里创建 bridge 实例；返回后的
        # capture closure 持有该实例，因此可以立即恢复模块全局类引用。
        return _base.configure_terminal_scrolling(core, capture_runner)
    finally:
        _base.TmuxScrollBridge = original_bridge
