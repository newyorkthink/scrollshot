# ScrollShot

<p align="center">
  <img src="assets/scrollshot.svg" width="128" height="128" alt="ScrollShot logo">
</p>

[English](README_EN.md)

ScrollShot 是面向 **Linux X11** 的滚动截图 AppImage，可对浏览器、Dolphin/设置类窗口、PDF 阅读器、普通终端和终端 TUI 进行自动滚动、重叠检测与 PNG 拼接。

> **最终稳定基线：2026-08-11**
>
> 当前已实际验证的运行逻辑锚点为 `016d8b677e49a81e129fb5139c6cbeed287525e4`。
>
> 该锚点保留此前 Dolphin、浏览器、YouTube、PDF/整窗 GUI、i3/EWMH、`Esc`/`Ctrl+C`、工作区保护、Kando 通知和浏览器安全滚轮落点等稳定行为，并完成了 **Alacritty / Kitty + tmux + Lazygit 的双向滚动截图收尾**。
>
> 本次最终文档整理只更新 README 和稳定基线笔记，不修改已经实测通过的运行逻辑，因此不会为了“整理注释”重新生成一个未经实测的新 AppImage。详细维护笔记见 [`STABLE_BASELINE_20260807.md`](STABLE_BASELINE_20260807.md)。

## 已验证的最终状态

### GUI / 浏览器 / PDF

- Dolphin 长列表可以连续滚动并拼接成长图。
- 浏览器/网页长内容可以连续滚动，固定侧栏和右侧滚动条不会被反复拼接。
- YouTube 播放页已实际完成长截图：中央视频不会再因为滚轮落点而接管滚轮，页面可以持续向下滚动。
- 浏览器滚轮落点固定在选区右侧偏中下的安全位置（约 X=85%、Y=60%），用于避开中央视频、地图、画布以及顶部两角常见的悬浮小视频。
- PDF/整窗 GUI 可以持续滚动；单轮重叠匹配暂时失败时会进行小步恢复，不会因为一次匹配失败就提前结束。
- PDF/整窗 GUI 的多行拼接缝、固定视口边界和重复黑线已有保守处理。
- 框选期间可以使用 i3/EWMH 工作区快捷键切换工作区，`Esc` 不依赖框选层键盘焦点。
- 捕获期间按 `Esc` 或终端 `Ctrl+C` 会提前结束并保存已经确认的部分。
- 捕获期间切换工作区会停止当前捕获并保存已经确认的部分，避免把其他工作区画面拼入长图。
- PNG 成功保存后会自动发送桌面通知并显示最终保存路径。
- 普通终端和 Kando 启动均已实际验证可以收到 Dunst 通知；实现仍使用通用 Freedesktop Notifications 标准，不绑定 Dunst 专有接口。

### 终端 / tmux / Lazygit

2026-08-11 最终实测矩阵：

| 场景 | 向下滚动截图 | 向上滚动截图 |
| --- | --- | --- |
| Alacritty + tmux 普通终端 | 已验证 | 已验证 |
| Alacritty + tmux + Lazygit | 已验证 | 已验证 |
| Kitty + tmux 普通终端 | 已验证 | 已验证 |
| Kitty + tmux + Lazygit | 已验证 | 已验证 |

终端最终实现不是“一种输入方式强行兼容所有终端”，而是保留已经实测有效的分流：

- **Alacritty 普通向下**：继续使用原来的 X11 滚轮路径。
- **Kitty 普通向下**：当目标 pane 已处于 tmux copy-mode 时，直接通过 tmux `scroll-down` 小步滚动；否则保留原 X11 回退路径。
- **Kitty + Lazygit 向下**：保持 Lazygit 本身运行，不进入 copy-mode，通过 tmux 向 Lazygit 发送其小步下滚键 `J`。
- **普通终端向上**：在第一帧截图前先进入 tmux copy-mode，再通过 tmux `scroll-up` 小步向上滚动，最后按反向采集顺序重新拼接为正常阅读顺序。
- **Kitty + Lazygit 向上**：不进入 tmux copy-mode，直接通过 tmux 向 Lazygit 发送其小步上滚键 `K`，避免冻结 Lazygit 自己的滚动视口。

**不需要也不应为 ScrollShot 安装 `ydotool`，不需要把当前用户加入 Linux `input` 组，也不需要额外的 uinput/输入守护进程。**

## 获取稳定 AppImage

仓库只维护一个 GitHub Release：`latest`。有效代码构建和测试通过后，会更新同一个 `latest` Release，不保留旧 Release。

- [Latest Release](https://github.com/newyorkthink/scrollshot/releases/latest)
- [scrollshot.AppImage](https://github.com/newyorkthink/scrollshot/releases/latest/download/scrollshot.AppImage)
- [scrollshot.AppImage.sha256](https://github.com/newyorkthink/scrollshot/releases/latest/download/scrollshot.AppImage.sha256)

GitHub 自动生成的 `Source code (zip)` 和 `Source code (tar.gz)` 属于 Release 固有项目，不能从资产列表中隐藏。

## 基本使用

在 **Linux X11 图形终端**执行：

```bash
# 为 AppImage 添加执行权限
chmod +x scrollshot.AppImage

# 启动普通向下滚动截图
./scrollshot.AppImage
```

操作顺序：

1. 启动后可先使用 i3/EWMH 工作区快捷键切换到目标工作区；连续切换停止约 0.2 秒后，框选预览刷新到最终工作区。
2. 移动鼠标时使用全屏十字线和跟随鼠标的像素放大镜定位。
3. 拖动框选实际需要滚动的区域。
4. 松开鼠标后不要移动、遮挡目标窗口，也不要改变缩放比例或标签页。
5. ScrollShot 自动滚动、匹配和拼接；浏览器/PDF/整窗 GUI 使用既定的稳定匹配与恢复链，终端根据 Alacritty/Kitty/tmux/Lazygit 状态进入对应的已验证分流。
6. PNG 默认保存到 `~/Pictures/`，保存成功后自动发送桌面通知。

## 终端向上截图

`--scroll-up` 专门用于当前已经验证的 **Alacritty / Kitty + tmux** 终端场景。

在 **Linux X11 图形终端**执行：

```bash
# 从当前底部位置开始向上采集终端历史，并最终按正常阅读顺序拼接
./scrollshot.AppImage --scroll-up
```

如果使用系统入口：

```bash
# 普通向下滚动截图
/usr/local/bin/scrollshot

# 终端向上滚动截图
/usr/local/bin/scrollshot --scroll-up
```

注意：终端向上模式依赖目标终端中已经运行的 tmux client；它不是浏览器/Dolphin/PDF 的通用“反向滚动”模式。

## Kando / 其他启动器

Kando 只需要启动 ScrollShot 本身，不需要在命令后面额外拼接 `notify-send`。

如果可执行入口已经位于 `/usr/local/bin/scrollshot`，建议保留两个独立动作：

```text
# 普通滚动截图
/usr/local/bin/scrollshot

# 终端向上滚动截图
/usr/local/bin/scrollshot --scroll-up
```

如果使用 AppImage 绝对路径，则直接替换为实际 AppImage 路径即可。

截图完成后的通知由 ScrollShot 自己发送。通知实现使用系统 `notify-send` 和 `org.freedesktop.Notifications`，兼容 Dunst、GNOME、KDE Plasma、Xfce 等实现该标准的通知服务。

## 操作语义

- **框选阶段 `Esc`**：取消本次框选，不保存截图。
- **捕获阶段 `Esc`**：停止继续滚动，保存已经确认的部分。
- **启动终端 `Ctrl+C`**：停止继续滚动，保存已经确认的部分。
- **捕获阶段切换工作区**：停止当前捕获并保存已经确认的部分。
- **检测到页面底部/无法继续可靠匹配**：结束捕获并保存当前结果。
- **通知不可用**：PNG 仍然正常保存，通知失败不会改变截图结果。

## 主要功能

- 鼠标框选任意矩形区域。
- 全屏十字定位线实时跟随鼠标。
- 像素网格放大镜跟随鼠标，并在屏幕边缘自动翻转位置。
- 放大镜显示 X/Y 坐标和选区宽高。
- 框选期间支持 i3/EWMH 工作区切换与延迟刷新。
- 框选层不抢键盘焦点，只抓取无修饰键的 `Esc`，不占用 `Alt+1`、`Alt+A` 等 i3 快捷键。
- 根据选区高度自动调整内部最小重叠值，支持较矮选区。
- 区分滚动内容与固定页头、固定页脚。
- 滚轮发送前自动移动到选区约 X=85%、Y=60% 的安全位置，降低浏览器视频/地图/画布截获滚轮的概率。
- 浏览器主匹配失败时使用保守回退匹配。
- 单轮匹配暂时失败时，从最后一个已确认帧进行有限的小步滚动恢复。
- 识别浏览器固定侧栏和右侧滚动条，避免重复拼接。
- PDF/整窗 GUI 使用既定回退匹配，并处理固定视口边界和拼接线。
- 对重复条纹、表格行等布局进行结构特征校验。
- 捕获期间保持静默，避免终端输出反过来进入截图区域。
- 自动避让同名输出文件，不覆盖已有截图。
- 支持 Alacritty / Kitty + tmux 终端向上截图。
- 针对 Kitty 的 XInput2/传统 X11 滚轮差异，使用 tmux/Lazygit 应用层滚动分流，不引入额外输入守护程序。

## 常用参数

在 **Linux X11 图形终端**执行：

```bash
# 指定输出文件；同名文件存在时自动生成带序号的新文件名
./scrollshot.AppImage --output ./web-page.png
```

```bash
# 使用固定坐标区域，跳过鼠标框选
./scrollshot.AppImage --geometry 100,120,1200,800
```

```bash
# 调整每轮滚轮次数；默认值为 3
./scrollshot.AppImage --scroll-ticks 3
```

```bash
# 页面滚动动画较慢时增加每轮等待时间
./scrollshot.AppImage --delay 0.8
```

```bash
# 终端向上滚动截图
./scrollshot.AppImage --scroll-up
```

```bash
# 保存每一张原始帧，用于排查特殊窗口
./scrollshot.AppImage --debug-dir ./scrollshot-debug
```

```bash
# 显示完整命令行帮助
./scrollshot.AppImage --help
```

## 运行环境与限制

- x86_64 Linux。
- X11 图形会话；不支持原生 Wayland 会话。
- 终端双向模式按当前实测基线面向 **Alacritty / Kitty + tmux**；`--scroll-up` 需要目标终端存在可解析的活动 tmux client。
- Kitty 普通向下的 tmux 专用路径只在 pane 已处于 copy-mode 时接管；其他状态保持既有 X11 回退逻辑。
- Kitty + Lazygit 双向滚动依赖 Lazygit 当前默认的小步滚动键 `K` / `J`；如果用户以后自行重映射 Lazygit 对应键位，需要同步调整 ScrollShot。
- 不依赖 `ydotool`、`input` 组、uinput daemon 或 root 权限。
- GUI 滚动输入默认发送到选区横向约 85%、纵向约 60% 的安全落点；该位置仍必须能够把滚轮传给目标滚动容器。如果某个特殊网页控件恰好覆盖并截获该位置，滚动仍可能受影响。
- 建议只框选实际滚动内容，不要包含无关窗口。
- 视频、持续动画、大面积闪烁或非常规覆盖层仍可能影响重叠检测；顶部固定/悬浮视频通常不会被后续片段大量重复追加，但动态画面仍可能降低匹配可靠性。
- 桌面通知依赖宿主机存在 `notify-send` 和可用的 Freedesktop 通知服务；通知失败不影响 PNG。
- 调用宿主机 `notify-send` 前会清理启动器/AppImage 继承的 `LD_LIBRARY_PATH`、`LD_LIBRARY_PATH_ORIG` 和 `LD_PRELOAD`；通知 D-Bus 地址会从有效的 `$XDG_RUNTIME_DIR/bus` 重新构造，无效时回退到 `/run/user/$UID/bus`。

## 稳定架构

最终装配顺序保存在 `src/scrollshot_app.py`，后层依赖前层的保守回退行为，**不要随意重排**：

```text
框选层
  -> 原始位移匹配
  -> 重复布局结构校验
  -> 浏览器 / PDF / 整窗 GUI 回退匹配
  -> 原始拼接
  -> 稳健拼接（固定侧栏 / 滚动条 / PDF 固定边界）
  -> 拼接缝保守清理
  -> 捕获运行层（安全滚轮落点 / Esc / 工作区保护 / 底部判定 / 匹配恢复）
  -> 终端滚动分流层（Alacritty / Kitty / tmux / Lazygit / --scroll-up）
  -> 保存成功后的桌面通知
```

各模块职责、终端分流中文维护说明和维护禁区见 [`STABLE_BASELINE_20260807.md`](STABLE_BASELINE_20260807.md)。

## 最终稳定维护原则

当前 `016d8b677e49a81e129fb5139c6cbeed287525e4` 已完成真实环境双向终端回归验证，因此后续维护应遵守：

- 不为了“统一实现”把 Alacritty、Kitty、tmux copy-mode 和 Lazygit 强行改成同一种输入方式。
- 不重新引入 `ydotool`、用户 `input` 组权限或其他外部输入守护程序。
- 不重新使用曾导致终端出现 `AAAAA` 的模拟键盘注入方案。
- 不改变已经验证有效的浏览器 X=85%、Y=60% 安全滚轮位置。
- 不改变捕获/匹配/拼接装配顺序。
- 修改终端路径时必须同时回归四个组合的向上和向下，总计 8 个方向场景。
- README/稳定笔记整理不应修改运行代码，也不应无意义消耗 GitHub Actions 构建分钟。

## GitHub Actions

`Build ScrollShot AppImage` 在 `main` 分支发生有效构建相关修改时运行。`README.md`、`README_EN.md`、`STABLE_BASELINE_20260807.md` 和 License 的纯文档修改不会触发完整 AppImage 构建。

工作流会执行：

1. Python 语法检查和单元测试，其中包含捕获运行接口、工作区保护、终端滚动分流，以及启动器/Kando 风格环境污染下的通知 session bus 回归检查。
2. Xvfb 框选预览、全屏十字线、像素放大镜、Alt 快捷键可用性、快速工作区切换、焦点保持和全局 `Esc` 测试。
3. 固定页头/页脚、重复布局、浏览器/PDF 回退拼接和较矮选区回归测试。
4. PyInstaller 构建和 AppDir 组装，检查桌面文件、图标与启动入口。
5. 使用 `appimagetool` 生成 `scrollshot.AppImage`。
6. 运行 AppImage 本体并检查滚动拼接结果。
7. 生成 SHA-256 校验文件。
8. 更新唯一的 `latest` Release。

自动测试不能替代真实 Kitty/Alacritty/tmux/Lazygit 交互回归；2026-08-11 的最终终端矩阵已经由真实环境逐项验证。

## License

MIT
