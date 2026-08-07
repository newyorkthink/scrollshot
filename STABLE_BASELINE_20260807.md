# ScrollShot 最终稳定基线笔记（2026-08-07）

本文档用于记录 ScrollShot 当前已经实际验证有效的行为、模块关系、维护边界和回归风险。后续修改应先以本文件为基线检查，不应因为代码看起来“可以简化”就重排、合并或删除已经验证有效的逻辑。

## 1. 稳定基线

功能验证锚点：

`27b9925e375ef4a4818ca648e16a1596aa0b5dc5`

该锚点包含此前已经完成的浏览器、PDF/整窗 GUI、i3/EWMH、`Esc`、拼接恢复和桌面通知修复。

2026-08-07 最终整理阶段只做以下维护工作：

- 整理中英文 README。
- 建立本稳定基线笔记。
- 补充最终装配入口的维护注释。
- 将稳定基线笔记加入 GitHub Actions 的纯文档忽略列表。
- 不改变已经实际验证有效的捕获、匹配、拼接、停止和通知行为。

## 2. 已实际验证的场景

### Dolphin / 设置类窗口

- 长列表可以连续向下滚动。
- 可以拼接为完整长图。
- 重复灰白行不会因为周期性内容造成明显的错误位移。
- 固定 UI 不应在每个拼接片段中反复出现。

### 浏览器 / 网页

- 长网页可以持续滚动。
- 主匹配暂时不可靠时会进入浏览器回退匹配。
- 固定侧栏和右侧滚动条已有专门处理。
- 捕获期间终端保持静默，不会因为输出日志而反过来污染截图区域。

### PDF / 整窗 GUI

- 双页/多页 PDF 整窗捕获可以继续滚动，不再因为一次重叠匹配失败就只截少量页面后停止。
- 单轮匹配暂时失败时，从最后一个已确认帧进行有限的小步滚动恢复。
- 多行拼接缝、固定视口边界和重复深色分隔线使用保守逻辑处理。
- 只有确认的帧进入最终拼接链。

### i3 / X11 交互

- 框选层不应抢走普通窗口焦点。
- 只抓取无修饰键的 `Esc`；`Alt+1`、`Alt+A` 等 i3 快捷键仍应可用。
- 框选阶段允许切换 EWMH 工作区，并在切换稳定后刷新预览。
- 捕获开始后如果工作区发生变化，应停止当前捕获并保存已经确认的部分，避免不同工作区画面混入同一张长图。

### 桌面通知

- PNG 保存成功后自动通知。
- 普通终端直接启动时通知正常。
- 从启动器启动时通知正常。
- 已验证 Dunst 可以收到通知，但实现不依赖 Dunst 专有接口。
- 通知走系统 `notify-send` 和 `org.freedesktop.Notifications`。
- 如果启动器没有传入 `DBUS_SESSION_BUS_ADDRESS` / `XDG_RUNTIME_DIR`，会尝试标准的 `/run/user/$UID/bus`。
- PyInstaller/AppImage 的动态库环境在调用宿主机通知程序时按既定逻辑处理。
- 通知失败不得影响已经保存成功的 PNG。

## 3. 用户侧运行方式

### AppImage

在 **Linux X11 图形终端**执行：

```bash
# 为 AppImage 添加执行权限
chmod +x scrollshot.AppImage

# 启动 ScrollShot
./scrollshot.AppImage
```

### Kando

Kando 只负责启动 ScrollShot，不需要额外添加通知命令。

如果当前入口是 `/usr/local/bin/scrollshot`，在 **Kando 的运行程序/命令动作**中填写：

```text
/usr/local/bin/scrollshot
```

不要在该命令后追加 `&& notify-send ...`。通知属于 ScrollShot 保存成功后的内部行为，不应放到 Kando 动作中重复实现。

## 4. 停止行为必须保持一致

| 场景 | 当前稳定行为 |
| --- | --- |
| 框选阶段按 `Esc` | 取消框选，不保存 |
| 捕获阶段按 `Esc` | 停止继续滚动，保存已确认部分 |
| 捕获阶段终端 `Ctrl+C` | 停止继续滚动，保存已确认部分 |
| 捕获阶段切换工作区 | 停止当前捕获，保存已确认部分 |
| 检测到底部 | 正常结束并保存 |
| 单轮匹配失败 | 先按既定重试和小步恢复流程处理 |
| 恢复后仍无法可靠匹配 | 结束并保存当前已确认结果 |
| 通知失败 | 不影响 PNG 保存结果 |

不要把“单轮 `match is None`”重新简化成直接结束捕获；这会重新引入 PDF/重复版式滚动到一半就停止的问题。

## 5. 稳定装配顺序

`src/scrollshot_app.py` 是最终装配入口。

当前顺序：

```text
create_select_region
  -> core 原始 estimate_vertical_shift
  -> create_structural_estimator
  -> create_fallback_estimator
  -> core 原始 stitch_frames
  -> create_resilient_stitcher
  -> create_seam_cleaning_stitcher
  -> create_capture_runner
  -> 保存成功后的 _notify_capture_saved
```

这个顺序是稳定基线的一部分。

不要在没有完整回归检查的情况下：

- 调换结构校验与回退匹配的顺序。
- 绕过 `create_resilient_stitcher`。
- 把 seam cleanup 提前到原始/稳健拼接之前。
- 删除 capture runtime 的底部宽限、重试或小步恢复。
- 将通知放到 PNG 保存之前。
- 因为两个模块都处理 PyInstaller/宿主环境就擅自合并或删除其中一段已验证逻辑。

## 6. 模块职责

| 文件 | 稳定职责 |
| --- | --- |
| `src/scrollshot.py` | 核心数据结构、X11 截图、基础位移检测、基础拼接、参数解析、PNG 保存 |
| `src/selection_ui.py` | X11 框选层、全局 `Esc`、工作区变化监听、基础像素放大镜 |
| `src/pointer_guides.py` | 跟随鼠标的放大镜定位、中心轴辅助 |
| `src/selection_guides.py` | 将最终十字线/放大镜行为叠加到框选层 |
| `src/capture_options.py` | 根据选区高度调整最小重叠值 |
| `src/structural_match.py` | 重复条纹/表格等周期布局的结构校验 |
| `src/fallback_match.py` | 浏览器、PDF、整窗 GUI 的保守回退位移匹配 |
| `src/resilient_stitch.py` | 固定侧栏、滚动条、PDF 固定边界等稳健拼接 |
| `src/seam_cleanup.py` | 只在已知拼接点附近进行保守深色缝清理 |
| `src/capture_runtime.py` | 捕获循环、`Esc`/`Ctrl+C`、工作区保护、底部判定、匹配重试和小步恢复 |
| `src/scrollshot_app.py` | 按稳定顺序装配所有增强层，并在成功保存后发送桌面通知 |
| `packaging/AppRun` | AppImage 最外层启动入口；保持简单，不重复实现截图或通知逻辑 |
| `.github/workflows/build.yml` | 静态检查、X11 回归、AppImage 构建/自测、SHA-256 和 `latest` Release |

## 7. 通知链路

通知保持以下原则：

1. 截图先成功写入 PNG。
2. 捕获运行层完成清理并返回结果。
3. `scrollshot_app.py` 调用 `_notify_capture_saved()`。
4. 使用宿主机 `notify-send`。
5. 优先保留现有 `DBUS_SESSION_BUS_ADDRESS`。
6. 没有该变量时先检查 `$XDG_RUNTIME_DIR/bus`。
7. 启动器连 `XDG_RUNTIME_DIR` 也没有提供时，再检查 `/run/user/$UID/bus`。
8. 任何通知异常都吞掉，不改变截图成功返回值。

这一链路已经解决“终端手动 `notify-send` 正常，但从启动器运行 ScrollShot 没通知”的问题。

## 8. 匹配失败恢复链路

当正常滚动后当前帧与最后一个已确认帧无法匹配时：

1. 先按既定时间等待并重新截图。
2. 最多执行既定次数的普通匹配重试。
3. 对较高选区，如果仍无法匹配，再执行有限次数的 1 格滚轮小步恢复。
4. 每次恢复仍以最后一个已确认帧作为锚点。
5. 只有恢复帧得到可靠匹配后才加入 `frames` / `matches`。
6. 恢复失败才结束本次捕获并保存已确认结果。

该逻辑是 PDF/整窗 GUI 稳定性的关键部分，不要删除。

## 9. GitHub Actions 与 Actions 分钟

当前仓库只维护 `main`，最终稳定修改直接提交到 `main`。

工作流规则：

- 代码、测试、打包或 workflow 修改会触发 `Build ScrollShot AppImage`。
- `README.md`、`README_EN.md`、`LICENSE`、`STABLE_BASELINE_20260807.md` 的纯文档修改不触发完整构建。
- `concurrency.cancel-in-progress: true` 保持同一仓库只保留最新构建。
- 构建通过后更新唯一的 `latest` Release。
- 不应通过连续小提交反复触发 Actions 来试错。

修改 workflow 前必须检查：

- YAML 语法。
- `push` / `workflow_dispatch` 触发条件。
- `paths-ignore`。
- `contents: write` 权限。
- PyInstaller 入口仍为 `src/scrollshot_app.py`。
- AppDir 路径和 `packaging/AppRun`。
- Xvfb 测试命令。
- AppImage 文件名 `scrollshot.AppImage`。
- SHA-256 生成。
- `latest` Release 更新逻辑。

## 10. 已知边界

当前稳定版本仍有明确边界：

- 只支持 X11，不支持原生 Wayland。
- 滚动输入发送到选区中心，因此选区中心必须能够接收滚轮。
- 持续视频、强动画、大面积闪烁、非常规覆盖层可能降低匹配可靠性。
- 极端特殊的网页/PDF 布局仍可能需要 `--debug-dir` 收集原始帧后再针对性分析。
- 通知依赖宿主机 `notify-send` 和可用的 Freedesktop 通知服务；缺失时截图本身不受影响。

## 11. 后续修改前检查清单

任何后续代码修改前，至少检查：

- 是否触碰已经验证的捕获/匹配/拼接顺序。
- 是否改变 `Esc`、`Ctrl+C` 或工作区切换语义。
- 是否把 `match is None` 改回立即退出。
- 是否可能重复固定侧栏、滚动条或 PDF 固定边界。
- 是否可能重新引入拼接黑线。
- 是否影响 Kando/其他启动器下的 D-Bus 通知。
- 是否改变 `LD_LIBRARY_PATH` / `LD_LIBRARY_PATH_ORIG` 处理。
- 是否导致 README-only/笔记-only 修改触发 Actions。
- 是否修改了无关文件。
- 是否在提交前完成完整 diff 检查。

## 12. 回归时的处理原则

如果后续版本出现回归：

1. 先与本稳定基线逐项比较，不要同时改多个无关算法。
2. 保留已经确认有效的命令、参数、模块顺序和停止语义。
3. 优先定位新改动对稳定链路的影响。
4. 一次性完成静态检查和完整 diff 后再提交。
5. 不使用用户真实环境进行无意义的反复试错。
