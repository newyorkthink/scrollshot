# ScrollShot

<p align="center">
  <img src="assets/scrollshot.svg" width="128" height="128" alt="ScrollShot logo">
</p>

[中文](README.md)

ScrollShot is a scrolling screenshot AppImage for **Linux X11**. It automatically scrolls browsers, Dolphin/settings-style windows, PDF viewers, and other scrollable regions, detects overlap, and stitches the confirmed frames into a PNG.

> **Final stable baseline: 2026-08-07**
>
> The validated runtime anchor is `b5b22693197010e6b30490df6f2a2300f9c93b11`. This version has been manually validated for Dolphin, browser, PDF/full-window GUI, i3/EWMH, `Esc`/`Ctrl+C`, workspace protection, and desktop notifications when launched both from a normal terminal and from Kando.
>
> Later documentation-only cleanup does not change this validated runtime behavior. Detailed maintenance notes: [`STABLE_BASELINE_20260807.md`](STABLE_BASELINE_20260807.md).

## Validated stable state

- Long Dolphin lists can be continuously scrolled and stitched.
- Browser/web captures can continue through long content while fixed sidebars and the right-edge scrollbar are not repeatedly appended.
- PDF/full-window GUI captures continue through temporary ambiguous overlap rounds by using limited small-step recovery instead of ending after a single failed match.
- PDF/full-window GUI stitching includes conservative handling for multi-row seams, fixed viewport borders, and repeated dark separator lines.
- i3/EWMH workspace shortcuts remain available during selection, and `Esc` does not depend on the overlay owning keyboard focus.
- During capture, `Esc` or terminal `Ctrl+C` stops further scrolling and saves the confirmed portion.
- Changing workspaces during capture stops and saves the confirmed portion instead of mixing another workspace into the image.
- A successful PNG save automatically sends a desktop notification containing the final path.
- Dunst notifications have been manually validated from both a normal terminal and Kando; the implementation still uses the generic Freedesktop Notifications standard and is not tied to Dunst-specific APIs.

## Download the stable AppImage

The repository maintains one GitHub Release: `latest`. After a build-related change on `main` passes the configured checks, the same `latest` Release is updated and older Releases are removed.

- [Latest Release](https://github.com/newyorkthink/scrollshot/releases/latest)
- [scrollshot.AppImage](https://github.com/newyorkthink/scrollshot/releases/latest/download/scrollshot.AppImage)
- [scrollshot.AppImage.sha256](https://github.com/newyorkthink/scrollshot/releases/latest/download/scrollshot.AppImage.sha256)

GitHub-generated `Source code (zip)` and `Source code (tar.gz)` entries are built-in Release items and cannot be hidden from the asset list.

## Basic usage

Run in a **Linux X11 graphical terminal**:

```bash
# Make the AppImage executable
chmod +x scrollshot.AppImage

# Start an interactive scrolling capture
./scrollshot.AppImage
```

Procedure:

1. After launch, i3/EWMH workspace shortcuts can be used to reach the target workspace. After rapid switching settles for about 0.2 seconds, the selection preview refreshes to the final workspace.
2. Use the full-screen crosshair and pointer-following pixel magnifier for alignment.
3. Drag to select the actual scrolling region.
4. After releasing the mouse button, do not move or cover the target, change zoom, or switch tabs.
5. ScrollShot automatically scrolls, matches, and stitches. Browsers and PDF/full-window GUI captures use the established conservative fallback paths when needed.
6. The PNG is saved to `~/Pictures/` by default, then a desktop notification is sent automatically.

## Kando / other launchers

A launcher only needs to start ScrollShot itself. Do not append a separate `notify-send` command.

If the executable entry is `/usr/local/bin/scrollshot`, put this in Kando's run-command action:

```text
/usr/local/bin/scrollshot
```

When using an AppImage directly, use its actual absolute path instead.

This launch path has been manually validated: after the PNG is saved, ScrollShot **automatically sends the notification**. It uses the system `notify-send` client and `org.freedesktop.Notifications`, so it remains compatible with Dunst, GNOME, KDE Plasma, Xfce, and other implementations of that standard.

## Stop and save semantics

- **`Esc` during selection**: cancel selection; no screenshot is saved.
- **`Esc` during capture**: stop scrolling and save the confirmed portion.
- **Terminal `Ctrl+C` during capture**: stop scrolling and save the confirmed portion.
- **Workspace change during capture**: stop and save the confirmed portion.
- **Detected page bottom / no further reliable match**: finish and save the current result.
- **Notification unavailable**: the PNG is still saved; notification failure never changes the screenshot result.

## Features

- Select any rectangular region with the mouse.
- Full-screen crosshair guides follow the pointer.
- A pixel-grid magnifier follows the pointer and flips at screen edges.
- The magnifier shows X/Y coordinates and live selection dimensions.
- i3/EWMH workspace switching remains available during selection with delayed preview refresh.
- The overlay stays non-focusable and grabs only unmodified `Esc`, leaving shortcuts such as `Alt+1` and `Alt+A` available.
- Internal overlap is adapted to the selected height so short selections remain supported.
- Scrolling content is separated from fixed headers and footers.
- A conservative browser fallback matcher is used when the primary matcher is unreliable.
- A temporary failed overlap round can use limited small-step recovery from the last confirmed frame.
- Fixed browser sidebars and the right-edge scrollbar are detected to avoid repeated append artifacts.
- PDF/full-window GUI captures use established fallback matching and conservative fixed-border/seam handling.
- Repetitive striped or table-like layouts receive structural verification.
- Active capture remains quiet so terminal output cannot feed back into the selected area.
- Existing output files are never overwritten.

## Common options

Run in a **Linux X11 graphical terminal**:

```bash
# Set the output path; an indexed filename is used if it already exists
./scrollshot.AppImage --output ./web-page.png
```

```bash
# Use a fixed region and skip mouse selection
./scrollshot.AppImage --geometry 100,120,1200,800
```

```bash
# Set wheel events per capture round; the default is 3
./scrollshot.AppImage --scroll-ticks 3
```

```bash
# Increase the wait time for slowly animated scrolling
./scrollshot.AppImage --delay 0.8
```

```bash
# Save every raw frame for troubleshooting
./scrollshot.AppImage --debug-dir ./scrollshot-debug
```

```bash
# Show complete command-line help
./scrollshot.AppImage --help
```

## Requirements and limitations

- x86_64 Linux.
- An X11 graphical session; native Wayland sessions are not supported.
- The center of the selected region must accept mouse-wheel input.
- Select the actual scrolling content and avoid unrelated windows.
- Video, continuous animation, large flashing areas, or unusual overlays may reduce overlap reliability.
- Desktop notification requires a host `notify-send` client and a working Freedesktop notification service; notification failure does not affect the PNG.
- Before calling the host `notify-send`, ScrollShot removes launcher/AppImage-provided `LD_LIBRARY_PATH`, `LD_LIBRARY_PATH_ORIG`, and `LD_PRELOAD`; the notification D-Bus address is rebuilt from a valid `$XDG_RUNTIME_DIR/bus`, with `/run/user/$UID/bus` as the fallback.

## Stable architecture

The final wrapper order lives in `src/scrollshot_app.py`. Later layers rely on the conservative fallback behavior of earlier layers, so **do not casually reorder them**:

```text
selection layer
  -> original shift matcher
  -> repetitive-layout structural verification
  -> browser / PDF / full-window GUI fallback matcher
  -> original stitcher
  -> resilient stitching (fixed sidebars / scrollbar / PDF fixed borders)
  -> conservative seam cleanup
  -> capture runtime (Esc / workspace protection / bottom detection / match recovery)
  -> post-save desktop notification
```

See [`STABLE_BASELINE_20260807.md`](STABLE_BASELINE_20260807.md) for module responsibilities and maintenance constraints.

## GitHub Actions

`Build ScrollShot AppImage` runs for build-related changes on `main`. README, License, and stable-baseline-note-only changes do not trigger a full AppImage build.

The workflow performs:

1. Python syntax checks and unit tests, including a launcher/Kando-style notification-environment regression test for session-bus reconstruction.
2. Xvfb selection-preview, full-screen crosshair, pointer-following magnifier, Alt-shortcut availability, rapid workspace switching, focus-preservation, and global `Esc` tests.
3. Fixed-header/footer, repetitive-layout, browser/PDF fallback-stitching, and short-region regression tests.
4. PyInstaller build and AppDir assembly, including desktop-file, icon, and launcher checks.
5. AppImage creation with `appimagetool`.
6. Execution of the AppImage itself and verification of a stitched result.
7. SHA-256 generation.
8. Update of the single `latest` Release.

## License

MIT
