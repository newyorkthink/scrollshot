# ScrollShot

<p align="center">
  <img src="assets/scrollshot.svg" width="128" height="128" alt="ScrollShot logo">
</p>

[中文](README.md)

ScrollShot is a scrolling screenshot AppImage for **Linux X11**. It automatically scrolls browsers, Dolphin/settings-style windows, PDF viewers, regular terminals, and terminal TUIs, detects overlap, and stitches confirmed frames into a PNG.

> **Final stable baseline: 2026-08-11**
>
> The manually validated runtime anchor is `016d8b677e49a81e129fb5139c6cbeed287525e4`.
>
> This anchor preserves the validated Dolphin, browser, YouTube, PDF/full-window GUI, i3/EWMH, `Esc`/`Ctrl+C`, workspace protection, Kando notification, and browser-safe wheel-target behavior, and finishes bidirectional terminal capture for **Alacritty / Kitty + tmux + Lazygit**.
>
> The final documentation cleanup changes README/baseline notes only and intentionally leaves the manually validated runtime untouched. Detailed maintenance notes are in [`STABLE_BASELINE_20260807.md`](STABLE_BASELINE_20260807.md).

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

Final manual validation matrix from 2026-08-11:

| Scenario | Downward capture | Upward capture |
| --- | --- | --- |
| Alacritty + tmux shell | Validated | Validated |
| Alacritty + tmux + Lazygit | Validated | Validated |
| Kitty + tmux shell | Validated | Validated |
| Kitty + tmux + Lazygit | Validated | Validated |

The terminal implementation intentionally keeps separate validated paths instead of forcing one synthetic-input mechanism onto every terminal:

- **Alacritty downward** keeps the established X11 wheel path.
- **Kitty downward in tmux copy mode** uses tmux `scroll-down` in small steps.
- **Kitty + Lazygit downward** stays inside Lazygit and sends Lazygit's small-step `J` binding through tmux.
- **Normal terminal upward capture** enters tmux copy mode before the first frame, then uses tmux `scroll-up`; acquisition order is reversed before final stitching.
- **Kitty + Lazygit upward** does not enter copy mode; it sends Lazygit's small-step `K` binding through tmux so the application viewport remains active.

ScrollShot **does not require `ydotool`, membership in the Linux `input` group, a uinput daemon, or root privileges**.

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

`--scroll-up` is the validated terminal/tmux mode; it is not a generic reverse-scrolling mode for browsers, Dolphin, or PDF viewers.

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
- `--scroll-up` currently targets the manually validated Alacritty / Kitty + tmux cases and requires a resolvable active tmux client.
- Kitty's dedicated downward tmux path takes over only when the pane is already in copy mode; otherwise the existing X11 fallback remains.
- Kitty + Lazygit uses Lazygit's default small-step `K` / `J` bindings. User remapping of those bindings requires a corresponding ScrollShot update and retest.
- No dependency on `ydotool`, the `input` group, uinput daemons, or root privileges.
- GUI wheel input normally uses the safe target near X=85%, Y=60% of the selected region.
- Video, continuous animation, large flashing regions, or unusual overlays may still reduce overlap reliability.
- Desktop notification requires a host `notify-send` client and a working Freedesktop notification service; notification failure never affects the PNG.

## Stable architecture

The final wrapper order lives in `src/scrollshot_app.py`; **do not casually reorder it**:

```text
selection layer
  -> original shift matcher
  -> repetitive-layout structural verification
  -> browser / PDF / full-window GUI fallback matcher
  -> original stitcher
  -> resilient stitching
  -> conservative seam cleanup
  -> capture runtime (safe wheel target / Esc / workspace protection / match recovery)
  -> terminal routing layer (Alacritty / Kitty / tmux / Lazygit / --scroll-up)
  -> post-save desktop notification
```

See [`STABLE_BASELINE_20260807.md`](STABLE_BASELINE_20260807.md) for the canonical Chinese maintenance notes, module responsibilities, and regression constraints.

## GitHub Actions

`Build ScrollShot AppImage` runs for build-related changes on `main`. `README.md`, `README_EN.md`, `STABLE_BASELINE_20260807.md`, and License-only changes do not trigger a full AppImage build.

The workflow performs Python syntax checks, unit tests, X11/Xvfb regression checks, PyInstaller/AppImage assembly, AppImage self-testing, SHA-256 generation, and update of the single `latest` Release.

Automated tests do not replace real Kitty/Alacritty/tmux/Lazygit interaction testing; the final 2026-08-11 terminal matrix was manually validated in the real environment.

## License

MIT
