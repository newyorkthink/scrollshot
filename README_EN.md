# ScrollShot

<p align="center">
  <img src="assets/scrollshot.svg" width="128" height="128" alt="ScrollShot logo">
</p>

[中文](README.md)

ScrollShot is a scrolling screenshot AppImage for **Linux X11**. It automatically scrolls browsers, Dolphin/settings-style windows, PDF viewers, regular terminals, and terminal TUIs, detects overlap, and stitches confirmed frames into a PNG.

> **Final stable baseline: 2026-08-11**
>
> Earlier full terminal validation anchor: `016d8b677e49a81e129fb5139c6cbeed287525e4`; current final code baseline: `53297e7d43560ddbd14ce5956d2b4c4098204e82`.
>
> `58bc73c35401f6128e4cb27789d3d48816956b00` extends Lazygit's upward application-level `K` path to both Alacritty and Kitty. `53297e7d...` fixes pointer restoration after interactive region selection.
>
> The existing Dolphin, browser, YouTube, PDF/full-window GUI, i3/EWMH, `Esc`/`Ctrl+C`, workspace protection, Kando notification, and browser-safe wheel-target behavior remain unchanged. Historical deep maintenance notes are in [`STABLE_BASELINE_20260807.md`](STABLE_BASELINE_20260807.md).

## Final validated state

### GUI / browser / PDF

- Long Dolphin lists can be continuously scrolled and stitched.
- Browser/web captures can continue through long content while fixed sidebars and the right-edge scrollbar are not repeatedly appended.
- A YouTube watch page has been manually captured as a long screenshot; the center video no longer receives wheel input instead of the page.
- Browser wheel input uses a safe interior point near X=85%, Y=60% to avoid center-page videos, maps, canvases, and common top-corner floating videos.
- PDF/full-window GUI captures use limited small-step recovery instead of ending after a single ambiguous overlap round.
- i3/EWMH workspace shortcuts remain available during selection.
- `Esc`, terminal `Ctrl+C`, and workspace changes keep the established stop-and-save semantics.
- Successful PNG saves automatically send a desktop notification.
- Dunst notifications have been manually validated from both a normal terminal and Kando while the implementation remains Freedesktop-standard based.

### Terminal / tmux / Lazygit

Target matrix:

| Scenario | Downward capture | Upward capture |
| --- | --- | --- |
| Alacritty + tmux shell | Supported | Supported |
| Alacritty + tmux + Lazygit | Supported | Supported |
| Kitty + tmux shell | Supported | Supported |
| Kitty + tmux + Lazygit | Supported | Supported |

The terminal implementation intentionally keeps separate validated paths instead of forcing one synthetic-input mechanism onto every terminal:

- **Alacritty downward** keeps the established X11 wheel path.
- **Kitty downward in tmux copy mode** uses tmux `scroll-down` in small steps.
- **Kitty + Lazygit downward** stays inside Lazygit and sends Lazygit's small-step `J` binding through tmux.
- **Normal terminal upward capture** enters tmux copy mode before the first frame, then uses tmux `scroll-up`; acquisition order is reversed before final stitching.
- **Alacritty / Kitty + Lazygit upward** does not enter copy mode; it sends Lazygit's small-step `K` binding through tmux so the application viewport remains active.

ScrollShot **does not require `ydotool`, membership in the Linux `input` group, a uinput daemon, or root privileges**.

### Pointer restoration

- Interactive mode records the real pointer position before region selection starts.
- Capture may still move the pointer to the established safe wheel target while scrolling.
- When capture ends, the pointer is restored to the **pre-selection** position instead of the bottom-right corner where the drag selection ended.
- `--geometry` skips interactive selection and keeps the previous controller behavior.

### Background activity and memory

- ScrollShot has no persistent background service or daemon.
- The temporary `Esc` listener thread exists only inside the active ScrollShot process and is closed at the end of capture.
- tmux commands and `notify-send` are short-lived child processes, not persistent services.
- Captured frames stay in memory until final stitching; memory usage therefore scales with region size and frame count, and is reclaimed by the operating system when ScrollShot exits.

## Download the stable AppImage

The repository maintains one GitHub Release: `latest`. After a build-related change on `main` passes the configured checks, the same `latest` Release is updated.

- [Latest Release](https://github.com/newyorkthink/scrollshot/releases/latest)
- [scrollshot.AppImage](https://github.com/newyorkthink/scrollshot/releases/latest/download/scrollshot.AppImage)
- [scrollshot.AppImage.sha256](https://github.com/newyorkthink/scrollshot/releases/latest/download/scrollshot.AppImage.sha256)

## Basic usage

Run in a **Linux X11 graphical terminal**:

```bash
# Make the AppImage executable
chmod +x scrollshot.AppImage

# Start normal downward scrolling capture
./scrollshot.AppImage
```

For terminal upward capture:

```bash
# Capture terminal history upward and stitch it back into reading order
./scrollshot.AppImage --scroll-up
```

With the system entry point:

```text
/usr/local/bin/scrollshot
/usr/local/bin/scrollshot --scroll-up
```

`--scroll-up` is the Alacritty / Kitty + tmux terminal mode; it is not a generic reverse-scrolling mode for browsers, Dolphin, or PDF viewers.

## Kando / other launchers

Kando only needs to start ScrollShot. Do not append an extra `notify-send` command.

Recommended separate actions:

```text
# Normal scrolling capture
/usr/local/bin/scrollshot

# Terminal upward capture
/usr/local/bin/scrollshot --scroll-up
```

The notification is sent internally after a successful save.

## Stop and save semantics

- **`Esc` during selection**: cancel selection; no screenshot is saved.
- **`Esc` during capture**: stop scrolling and save the confirmed portion.
- **Terminal `Ctrl+C` during capture**: stop scrolling and save the confirmed portion.
- **Workspace change during capture**: stop and save the confirmed portion.
- **Detected bottom / no further reliable match**: finish and save the current result.
- **Notification unavailable**: the PNG is still saved.

## Common options

```bash
# Set the output path
./scrollshot.AppImage --output ./web-page.png

# Use a fixed region
./scrollshot.AppImage --geometry 100,120,1200,800

# Set wheel events per round
./scrollshot.AppImage --scroll-ticks 3

# Increase delay for slow scrolling animations
./scrollshot.AppImage --delay 0.8

# Terminal upward capture
./scrollshot.AppImage --scroll-up

# Save raw frames for troubleshooting
./scrollshot.AppImage --debug-dir ./scrollshot-debug

# Show help
./scrollshot.AppImage --help
```

## Requirements and limitations

- x86_64 Linux.
- X11 graphical session only; native Wayland is not supported.
- `--scroll-up` targets Alacritty / Kitty + tmux and requires a resolvable active tmux client.
- Kitty's dedicated downward tmux path takes over only when the pane is already in copy mode; otherwise the existing X11 fallback remains.
- Alacritty / Kitty + Lazygit routing relies on Lazygit's default small-step `K` / `J` bindings. User remapping of those bindings requires a corresponding ScrollShot update and retest.
- No dependency on `ydotool`, the `input` group, uinput daemons, or root privileges.
- GUI wheel input normally uses the safe target near X=85%, Y=60% of the selected region.
- Video, continuous animation, large flashing regions, or unusual overlays may still reduce overlap reliability.
- Desktop notification requires a host `notify-send` client and a working Freedesktop notification service; notification failure never affects the PNG.

## Stable architecture

The final wrapper order lives in `src/scrollshot_app.py`; **do not casually reorder it**:

```text
selection layer / pre-selection pointer capture
  -> original shift matcher
  -> repetitive-layout structural verification
  -> browser / PDF / full-window GUI fallback matcher
  -> original stitcher
  -> resilient stitching
  -> conservative seam cleanup
  -> capture runtime (safe wheel target / Esc / workspace protection / match recovery)
  -> terminal routing layer (Alacritty / Kitty / tmux / Lazygit / --scroll-up)
  -> pointer restoration
  -> post-save desktop notification
```

The base terminal routing lives in `src/terminal_scroll.py`; the Alacritty / Kitty + Lazygit upward detection extension lives in `src/terminal_scroll_lazygit.py`. See [`STABLE_BASELINE_20260807.md`](STABLE_BASELINE_20260807.md) for the historical Chinese maintenance notes and regression constraints.

## Final maintenance rules

The earlier `016d8b677e49a81e129fb5139c6cbeed287525e4` anchor completed the real-environment bidirectional terminal regression. The current code baseline `53297e7d43560ddbd14ce5956d2b4c4098204e82` adds only the targeted Alacritty+Lazygit upward and pre-selection pointer restoration fixes after that baseline.

- Do not force Alacritty, Kitty, tmux copy mode, and Lazygit onto one unified input path.
- Do not reintroduce `ydotool`, Linux `input` group access, uinput daemons, or root privileges.
- Do not reintroduce the synthetic keyboard path that previously produced `AAAAA` in terminals.
- Do not casually change the browser-safe X=85%, Y=60% wheel target.
- Do not reorder the capture/matching/stitching layers.
- Terminal routing changes require regression of four terminal/content combinations in both directions: 8 scenarios total.
- Pointer changes require confirmation that capture restores to the **pre-selection** pointer position.

## GitHub Actions

`Build ScrollShot AppImage` runs for build-related changes on `main`. `README.md`, `README_EN.md`, `STABLE_BASELINE_20260807.md`, and License-only changes do not trigger a full AppImage build.

The workflow performs Python syntax checks, unit tests, X11/Xvfb regression checks, PyInstaller/AppImage assembly, AppImage self-testing, SHA-256 generation, and update of the single `latest` Release.

Automated tests do not replace real Kitty/Alacritty/tmux/Lazygit interaction testing; terminal-routing changes should still be confirmed against the 8-direction matrix.

## License

MIT
