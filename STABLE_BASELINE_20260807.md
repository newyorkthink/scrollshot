# ScrollShot 最终稳定基线笔记（2026-08-09）

> 文件名 `STABLE_BASELINE_20260807.md` 沿用既有路径，避免为了纯文档整理改变 GitHub Actions 的 `paths-ignore` 和稳定链接；文档内容以 2026-08-09 的最终实测状态为准。

本文档记录 ScrollShot 当前已经实际验证有效的行为、模块关系、维护边界和回归风险。后续修改应先以本文件为基线检查，不应因为代码看起来“可以简化”就重排、合并或删除已经验证有效的逻辑。

## 1. 最终稳定基线

已实际验证的运行逻辑锚点：

`0c290f2920818c55da5e3860310007096b0a0908`

该锚点是在此前浏览器、PDF/整窗 GUI、i3/EWMH、`Esc`、拼接恢复和启动器通知稳定基线上，最终加入浏览器安全滚轮落点后的版本。

最终状态已经实际确认：

- Dolphin 长列表滚动截图正常。
- 浏览器长网页滚动截图正常。
- YouTube 播放页带视频的长截图已经实际完成，页面可以持续向下滚动，不再因为鼠标位于中央视频而把滚轮变成播放器控制。
- 滚轮发送前将指针移动到选区横向约 85%、纵向约 60% 的右侧偏中下安全位置，避开中央视频和顶部常见悬浮小视频。
- 安全滚轮逻辑继续通过既有 `controller.move_to_region()` 接口工作，不要求测试桩或其他 Controller 实现新增 `move_pointer()`。
- PDF/整窗 GUI 可以持续滚动，不再因单轮匹配失败过早停止。
- 框选、全局 `Esc`、i3/EWMH 工作区切换行为正常。
- 捕获阶段 `Esc` / `Ctrl+C` / 工作区切换的停止与保存语义正常。
- 普通终端启动后桌面通知正常。
- Kando 仅执行 `/usr/local/bin/scrollshot` 时，截图保存后的桌面通知也已经实际验证正常。
- `latest` 标签下的 `src/capture_runtime.py` 与当前稳定修正版一致，说明发布的 `latest` AppImage 已包含该运行逻辑。

中间提交 `d1119117ebbe9123a8371d6f1ea8338bbbfab9c1` 因直接调用 `controller.move_pointer()` 破坏既有测试 Controller 接口而被单元测试拦截，不属于稳定基线。当前锚点 `0c290f2920818c55da5e3860310007096b0a0908` 保留原接口并已通过后续构建发布与实际截图验证。

后续纯 README / 稳定笔记整理不改变这个已验证运行逻辑，也不应为了文档整理重新生成一个未经实际验证的新 AppImage。

## 2. 已实际验证的场景

### Dolphin / 设置类窗口

- 长列表可以连续向下滚动。
- 可以拼接为完整长图。
- 重复灰白行不会因为周期性内容造成明显的错误位移。
- 固定 UI 不应在每个拼接片段中反复出现。

### 浏览器 / 网页

- 长网页可以持续滚动。
- YouTube 播放页已经用最终版本完成实际长截图验证。
- 主匹配暂时不可靠时会进入浏览器回退匹配。
- 固定侧栏和右侧滚动条已有专门处理。
- 正常滚动和匹配失败后的 1 格恢复滚动都使用同一套安全滚轮落点。
- 安全落点为选区横向约 85%、纵向约 60%，目的是避开网页中央常见的视频、地图、画布以及顶部两角悬浮小视频。
- 安全落点通过构造 1×1 临时目标区域继续调用 `move_to_region()`，真实截图区域、滚动量、匹配和拼接均不改变。
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
- Kando 启动时通知已经实际验证正常。
- 已验证 Dunst 可以收到通知，但实现不依赖 Dunst 专有接口。
- 通知走宿主机 `notify-send` 和 `org.freedesktop.Notifications`。
- 通知调用不会依赖启动器继承下来的 `DBUS_SESSION_BUS_ADDRESS`。
- 调用宿主机通知程序前会清理 `LD_LIBRARY_PATH`、`LD_LIBRARY_PATH_ORIG` 和 `LD_PRELOAD`，避免 Kando/AppImage/PyInstaller 的动态库环境污染系统 `notify-send`。
- 通知 session bus 优先从有效的 `$XDG_RUNTIME_DIR/bus` 构造；无效时回退到 `/run/user/$UID/bus`。
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

该写法已经实际验证有效。不要在命令后追加 `&& notify-send ...`；通知属于 ScrollShot 保存成功后的内部行为，不应在 Kando 动作中重复实现。

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
  -> create_capture_runner（安全滚轮落点 / Esc / 工作区保护 / 匹配恢复）
  -> 保存成功后的 _notify_capture_saved
```

这个顺序是稳定基线的一部分。

不要在没有完整回归检查的情况下：

- 调换结构校验与回退匹配的顺序。
- 绕过 `create_resilient_stitcher`。
- 把 seam cleanup 提前到原始/稳健拼接之前。
- 删除 capture runtime 的底部宽限、重试或小步恢复。
- 把浏览器滚轮落点改回选区正中心。
- 绕过既有 `move_to_region()` 接口直接要求 Controller 提供新的指针移动接口。
- 将通知放到 PNG 保存之前。
- 删除启动器通知环境清理和 session bus 重建逻辑。
- 因为两个模块都处理 PyInstaller/宿主环境就擅自合并或删除其中一段已验证逻辑。

## 6. 模块职责

| 文件 | 稳定职责 |
| --- | --- |
| `src/scrollshot.py` | 核心数据结构、X11 截图、基础位移检测、基础拼接、参数解析、PNG 保存，以及既有 `X11Controller` 指针/滚轮基础接口 |
| `src/selection_ui.py` | X11 框选层、全局 `Esc`、工作区变化监听、基础像素放大镜 |
| `src/pointer_guides.py` | 跟随鼠标的放大镜定位、中心轴辅助 |
| `src/selection_guides.py` | 将最终十字线/放大镜行为叠加到框选层 |
| `src/capture_options.py` | 根据选区高度调整最小重叠值 |
| `src/structural_match.py` | 重复条纹/表格等周期布局的结构校验 |
| `src/fallback_match.py` | 浏览器、PDF、整窗 GUI 的保守回退位移匹配 |
| `src/resilient_stitch.py` | 固定侧栏、滚动条、PDF 固定边界等稳健拼接 |
| `src/seam_cleanup.py` | 只在已知拼接点附近进行保守深色缝清理 |
| `src/capture_runtime.py` | 捕获循环、安全滚轮落点、`Esc`/`Ctrl+C`、工作区保护、底部判定、匹配重试和小步恢复；必须保持既有 `move_to_region()` Controller 接口 |
| `src/scrollshot_app.py` | 按稳定顺序装配所有增强层；清理启动器通知环境并在成功保存后发送桌面通知 |
| `tests/test_capture_runtime.py` | 回归捕获运行层底部宽限等行为，同时保护既有 Controller 调用接口 |
| `tests/test_capture_workspace.py` | 回归工作区切换保护和缺失 EWMH 支持时的捕获行为，同时保护既有 Controller 调用接口 |
| `tests/test_notification_environment.py` | 模拟 Kando/启动器错误 D-Bus 与动态库环境，回归检查 session bus 重建和环境清理 |
| `packaging/AppRun` | AppImage 最外层启动入口；保持简单，不重复实现截图或通知逻辑 |
| `.github/workflows/build.yml` | 静态检查、单元测试、X11 回归、AppImage 构建/自测、SHA-256 和 `latest` Release |

## 7. 最终通知链路

通知必须保持以下顺序和原则：

1. 截图先成功写入 PNG。
2. 捕获运行层完成清理并返回保存结果。
3. `scrollshot_app.py` 调用 `_notify_capture_saved()`。
4. 从当前环境复制出通知子进程环境。
5. 清除 `LD_LIBRARY_PATH`、`LD_LIBRARY_PATH_ORIG` 和 `LD_PRELOAD`，不让 Kando/AppImage/PyInstaller 的动态库环境污染宿主机程序。
6. 不信任启动器继承下来的 `DBUS_SESSION_BUS_ADDRESS`。
7. 如果 `$XDG_RUNTIME_DIR/bus` 是有效 socket，则据此重建 `DBUS_SESSION_BUS_ADDRESS`。
8. 如果该路径无效，则检查 `/run/user/$UID/bus` 并据此重建。
9. 优先调用宿主机常见位置的 `notify-send`，再回退到 `PATH` 查找。
10. 任何通知异常都吞掉，不改变截图成功返回值。

这一链路已经实际解决“终端运行 ScrollShot 有通知，但 Kando 运行没有通知”的问题，并已完成 Kando 实测确认。

## 8. 匹配失败恢复与安全滚动链路

正常滚动：

1. 使用原始真实选区计算安全滚轮坐标：横向约 85%、纵向约 60%。
2. 构造 1×1 临时目标区域。
3. 继续调用既有 `controller.move_to_region()`，不改变 Controller 接口。
4. 按 `args.scroll_ticks` 发送滚轮。
5. 等待、截图、匹配并只接纳可靠帧。

当正常滚动后当前帧与最后一个已确认帧无法匹配时：

1. 先按既定时间等待并重新截图。
2. 最多执行既定次数的普通匹配重试。
3. 对较高选区，如果仍无法匹配，再执行有限次数的 1 格滚轮小步恢复。
4. 小步恢复也必须先使用同一安全滚轮落点。
5. 每次恢复仍以最后一个已确认帧作为锚点。
6. 只有恢复帧得到可靠匹配后才加入 `frames` / `matches`。
7. 恢复失败才结束本次捕获并保存已确认结果。

该链路同时是浏览器视频页和 PDF/整窗 GUI 稳定性的关键部分，不要拆分成不同的未经验证滚动实现。

## 9. GitHub Actions 与 Actions 分钟

当前仓库只维护 `main`，最终稳定修改直接提交到 `main`。

工作流规则：

- 代码、测试、打包或 workflow 修改会触发 `Build ScrollShot AppImage`。
- `README.md`、`README_EN.md`、`LICENSE`、`STABLE_BASELINE_20260807.md` 的纯文档修改不触发完整构建。
- `concurrency.cancel-in-progress: true` 保持同一仓库只保留最新构建。
- 构建通过后更新唯一的 `latest` Release。
- 不应通过连续小提交反复触发 Actions 来试错。

本轮浏览器安全滚动修改中，第一次实现 `d1119117...` 被现有单元测试正确拦截：`test_capture_runtime.py` 和 `test_capture_workspace.py` 的模拟 Controller 只实现稳定接口 `move_to_region()`。最终锚点 `0c290f292...` 恢复该接口契约，并将安全目标包装成 1×1 临时区域。

当前 `latest` 标签下 `src/capture_runtime.py` 的 blob 与最终修正版一致，因此发布资产已经包含最终逻辑。之后的 README/稳定笔记整理属于 `paths-ignore`，不需要再次消耗 Actions 构建分钟。

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
- 滚动输入发送到选区横向约 85%、纵向约 60% 的安全位置；该位置仍必须能够把滚轮传给实际滚动容器。如果特殊控件恰好覆盖并截获该点，页面仍可能无法滚动。
- 顶部固定/悬浮小视频通常不会在最终拼接图中被每轮大量重复追加，但持续视频、强动画、大面积闪烁、非常规覆盖层仍可能降低重叠匹配可靠性。
- 极端特殊的网页/PDF 布局仍可能需要 `--debug-dir` 收集原始帧后再针对性分析。
- 通知依赖宿主机 `notify-send` 和可用的 Freedesktop 通知服务；缺失时截图本身不受影响。

## 11. 后续修改前检查清单

任何后续代码修改前，至少检查：

- 是否触碰已经验证的捕获/匹配/拼接顺序。
- 是否改变 `Esc`、`Ctrl+C` 或工作区切换语义。
- 是否把 `match is None` 改回立即退出。
- 是否可能重复固定侧栏、滚动条或 PDF 固定边界。
- 是否可能重新引入拼接黑线。
- 是否把浏览器滚轮位置重新放回中央视频常见区域。
- 是否保持横向约 85%、纵向约 60% 的安全滚轮策略。
- 是否继续通过 `move_to_region()` 与 Controller 交互，避免再次新增未经测试桩实现的接口依赖。
- 是否正常滚动和 1 格恢复滚动都使用同一安全目标。
- 是否影响 Kando/其他启动器下的 D-Bus 通知。
- 是否重新信任启动器继承的 `DBUS_SESSION_BUS_ADDRESS`。
- 是否删除 `LD_LIBRARY_PATH` / `LD_LIBRARY_PATH_ORIG` / `LD_PRELOAD` 清理。
- 是否破坏 `/run/user/$UID/bus` 回退。
- 是否导致 README-only/笔记-only 修改触发 Actions。
- 是否修改了无关文件。
- 是否在提交前完成完整 diff 检查。

## 12. 回归时的处理原则

如果后续版本出现回归：

1. 先与本稳定基线逐项比较，不要同时改多个无关算法。
2. 保留已经确认有效的命令、参数、模块顺序、Controller 接口和停止语义。
3. 浏览器滚动异常先检查安全落点是否仍为约 X=85%、Y=60%，以及该点是否被网页特殊控件截获，不要先改拼接算法。
4. PDF/重复版式问题优先检查既定匹配重试和 1 格恢复链路，不要把 `match is None` 改成直接结束。
5. 通知问题优先运行 `tests/test_notification_environment.py` 并核对真实 session bus，不要先改截图逻辑。
6. 一次性完成静态检查和完整 diff 后再提交。
7. 不使用用户真实环境进行无意义的反复试错。

## 13. 最终结论

`0c290f2920818c55da5e3860310007096b0a0908` 作为当前已实际验证的运行逻辑稳定锚点保留。

该锚点已经具备：Dolphin、浏览器、YouTube 视频页、PDF/整窗 GUI、i3/EWMH、`Esc`/`Ctrl+C`、工作区保护、Kando/普通终端通知、固定侧栏/滚动条处理、匹配失败恢复，以及浏览器安全滚轮落点。`latest` Release 已包含该运行逻辑。

后续若只是 README 或维护笔记调整，应保持 `latest` AppImage 不变；只有真正需要修改代码时，才重新走完整 Actions 构建和实际回归验证。
