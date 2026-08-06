# ScrollShot

ScrollShot 是面向 **Linux X11** 的滚动截图工具，适用于 Kali Linux、i3wm、浏览器和普通可滚动窗口。

程序执行后拖动鼠标框选区域，ScrollShot 会将鼠标移动到区域中心，自动向下滚动，检测相邻画面的重叠部分，并将新出现的内容拼接为一张 PNG。

## 主要功能

- 鼠标框选任意矩形区域
- 自动发送向下滚轮事件
- 多锚点重叠检测，降低重复图案造成的错误拼接
- 自动识别页面底部
- 匹配失败时停止继续滚动，保留此前已确认的结果
- 输出文件自动避让同名文件，不覆盖已有截图
- 支持固定坐标区域，便于接入 Kando、i3 快捷键或脚本
- `Ctrl+C` 可提前停止并保存当前已完成的拼接结果

## 运行环境

- Kali Linux 或其他带 X11 的 Linux 发行版
- i3wm、Xfce、KDE X11 等桌面环境
- 不支持原生 Wayland 会话

## Kali Linux 安装

在 **Kali Linux 终端**执行：

```bash
# 克隆 ScrollShot 仓库
git clone https://github.com/newyorkthink/scrollshot.git

# 进入 ScrollShot 仓库目录
cd scrollshot

# 安装 Kali Linux 依赖并将程序安装到 ~/.local/bin/scrollshot
./install.sh

# 检查 ScrollShot 是否安装完成
~/.local/bin/scrollshot --version
```

`install.sh` 只安装运行依赖并复制主程序，不会删除用户文件。若终端无法直接识别 `scrollshot`，需要确认 `~/.local/bin` 已加入 `PATH`。

## 基本使用

在 **Kali Linux 的 X11 图形终端**执行：

```bash
# 启动框选并自动完成滚动截图
scrollshot
```

操作顺序：

1. 拖动鼠标框选需要滚动截图的内容区域。
2. 松开鼠标后不要操作目标窗口。
3. 程序自动滚动、检测重叠并拼接。
4. 检测到页面底部后，PNG 默认保存到 `~/Pictures/`。

按 `Esc` 取消框选。捕获过程中可在启动命令的终端按 `Ctrl+C`，程序会保存已经完成的部分。

## 常用参数

在 **Kali Linux 终端**执行：

```bash
# 指定输出文件；文件已存在时会自动生成带序号的新文件名
scrollshot --output ~/Pictures/web-page.png
```

```bash
# 使用固定截图区域，跳过鼠标框选
scrollshot --geometry 100,120,1200,800
```

```bash
# 页面滚动动画较慢时增加每轮等待时间
scrollshot --delay 0.8
```

```bash
# 单次滚动距离过大时减少每轮滚轮次数
scrollshot --scroll-ticks 4
```

```bash
# 保存每一张原始帧，用于排查特殊网页的匹配问题
scrollshot --debug-dir ~/Pictures/scrollshot-debug
```

查看完整参数：

```bash
# 显示 ScrollShot 的完整命令行帮助
scrollshot --help
```

## Kando 与 i3wm

Kando 的“运行命令”动作可直接使用：

```text
scrollshot
```

固定区域也可使用：

```text
scrollshot --geometry 100,120,1200,800
```

在 i3 配置中绑定快捷键时，执行的同样是 `scrollshot` 命令。

## GitHub Actions 构建

仓库中的 `Build Linux executable` 工作流只支持手动触发，不会因普通提交自动运行，避免无效消耗 Actions 时间。

手动运行后会执行：

1. 安装隔离构建环境。
2. 运行拼接算法单元测试。
3. 使用 PyInstaller 构建 `scrollshot` x86_64 单文件程序。
4. 在 Xvfb 虚拟 X11 环境中完成实际截图检查。
5. 上传程序和 SHA-256 校验文件，Artifact 保留 14 天。

## 工作原理

每轮捕获后，ScrollShot 从新画面的多个纵向位置提取纹理锚点，并在上一帧中搜索对应区域。多个锚点检测到一致位移后，只追加新帧底部真正新增的像素。画面连续多轮基本不变时，程序判定已到达页面底部。

## 使用注意

- 框选区域中心必须位于能够响应鼠标滚轮的内容上。
- 捕获期间不要移动目标窗口、改变缩放比例或遮挡截图区域。
- 视频、持续动画、大面积闪烁内容可能影响重叠检测。
- 固定在页面底部的悬浮工具栏可能被重复带入拼接图，建议框选时避开该区域。
- 浏览器启用平滑滚动且动画时间较长时，可增加 `--delay`。

## 开发检查

在已经安装 NumPy 和 OpenCV 的开发环境中执行：

```bash
# 运行全部拼接算法单元测试
python3 -m unittest discover -s tests -v
```

```bash
# 检查主程序 Python 语法
python3 -m py_compile src/scrollshot.py
```

## License

MIT
