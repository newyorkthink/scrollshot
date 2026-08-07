# ScrollShot

<p align="center">
  <img src="assets/scrollshot.svg" width="128" height="128" alt="ScrollShot logo">
</p>

[English](README_EN.md)

ScrollShot 是面向 **Linux X11** 的滚动截图 AppImage，可对浏览器、设置窗口和其他可滚动区域进行自动滚动、重叠检测与 PNG 拼接。

## 主要功能

- 鼠标框选任意矩形区域
- 框选期间显示贯穿屏幕的十字定位线，横线和竖线实时跟随鼠标移动
- 像素网格放大镜显示在鼠标附近，到达屏幕边缘时自动翻转位置，不再固定在屏幕角落
- 放大镜标记中心像素并实时显示 X/Y 坐标与选区宽高
- 框选期间可使用 i3 等 EWMH 窗口管理器的工作区快捷键切换工作区；连续切换时延迟到工作区稳定后再刷新预览
- 框选层明确设置为不接收键盘焦点，并且只抓取无修饰键的 `Esc`，不占用 `Alt+1`、`Alt+A` 等 i3 快捷键
- `Esc` 通过 X11 全局按键监听取消，不依赖框选窗口是否获得焦点
- 框选时显示桌面预览，不依赖窗口透明效果
- 根据最终框选高度自动缩小内部最小重叠值，较矮选区不会再直接报 `--min-overlap must be smaller than the capture height`
- 自动识别滚动内容与固定页头、固定页脚
- 固定区域只保留一次，避免工具栏和按钮重复出现在结果中
- 捕获期间不持续向终端输出日志，避免终端内容反过来干扰截图
- 自动识别页面底部
- 无可靠滚动位移时停止，不把局部闪烁误判为整页滚动
- 输出文件自动避让同名文件，不覆盖已有截图
- `Ctrl+C` 可提前停止并保存已经完成的部分

## 运行环境

- x86_64 Linux
- X11 图形会话
- 不支持原生 Wayland 会话

## 获取 AppImage

从 [Releases](https://github.com/newyorkthink/scrollshot/releases/latest) 下载：

- [scrollshot.AppImage](https://github.com/newyorkthink/scrollshot/releases/download/continuous/scrollshot.AppImage)
- [scrollshot.AppImage.sha256](https://github.com/newyorkthink/scrollshot/releases/download/continuous/scrollshot.AppImage.sha256)

`continuous` Release 会在 `main` 分支构建和测试通过后自动更新，固定下载链接保持不变。

## 基本使用

在 **Linux X11 图形终端**执行：

```bash
# 为 AppImage 添加执行权限
chmod +x scrollshot.AppImage

# 启动框选滚动截图
./scrollshot.AppImage
```

操作顺序：

1. 启动后可先使用 i3 工作区快捷键切换到目标工作区；连续切换结束约 0.2 秒后，框选预览会刷新到最终工作区。
2. 移动鼠标时通过全屏十字线定位，放大镜会始终显示在鼠标附近。
3. 拖动框选实际需要滚动的区域；放大镜实时显示 X/Y 坐标、选区宽度和高度。
4. 松开鼠标后不要移动窗口或遮挡框选区域。
5. 程序自动滚动、识别固定区域并拼接。
6. PNG 默认保存到 `~/Pictures/`。

框选期间无论当前键盘焦点位于哪里，按 `Esc` 都会取消。捕获过程中可在启动命令的终端按 `Ctrl+C`，程序会保存已经完成的部分。

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
# 页面滚动动画较慢时增加等待时间
./scrollshot.AppImage --delay 0.8
```

```bash
# 保存每一张原始帧，用于排查特殊窗口
./scrollshot.AppImage --debug-dir ./scrollshot-debug
```

```bash
# 显示完整命令行帮助
./scrollshot.AppImage --help
```

## 使用注意

- 框选中心必须位于能够响应鼠标滚轮的内容上。
- 建议框选实际滚动内容；程序可以处理固定页头和页脚，但不应包含无关窗口。
- 捕获期间不要改变缩放比例、切换标签页或移动目标窗口。
- 视频、持续动画和大面积闪烁内容可能影响重叠检测。
- 很矮的选区会自动降低内部重叠要求；无法可靠识别滚动位移时会保存已确认的单帧或部分结果，不再因默认重叠值直接退出。
- 无法滚动的区域会在画面保持不变后自动停止并保存单帧结果。

## GitHub Actions

`Build ScrollShot AppImage` 工作流在 `main` 分支每次产生提交后自动运行，包括只修改 README 的提交。

工作流会执行：

1. Python 语法检查和单元测试。
2. Xvfb 框选预览、全屏十字线、跟随鼠标的像素放大镜、`Alt` 快捷键可用性、快速工作区切换、焦点保持与全局 `Esc` 测试。
3. 固定页头、固定页脚滚动窗口测试，并验证较矮选区不会触发默认最小重叠错误。
4. PyInstaller 构建和 AppDir 组装。
5. 使用 `appimagetool` 生成 `scrollshot.AppImage`。
6. 运行 AppImage 本体并检查滚动拼接结果。
7. 更新 `continuous` Release 和 SHA-256 校验文件。

## License

MIT
