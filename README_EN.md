# ScrollShot

<p align="center">
  <img src="assets/scrollshot.svg" width="128" height="128" alt="ScrollShot logo">
</p>

[中文](README.md)

ScrollShot is a scrolling screenshot AppImage for **Linux X11**. It automatically scrolls browsers, settings dialogs, PDF viewers, and other scrollable areas, detects overlap, and stitches captured frames into a PNG.

The repository treats the implementation that completed long Dolphin lists, browser pages, and full-window PDF captures as the stable baseline. Future changes should preserve the current selection, i3 workspace switching, `Esc`, magnifier, browser/PDF fallback matching, and stitching behavior.

## Features

- Select any rectangular area with the mouse
- Show full-screen horizontal and vertical crosshair guides that follow the pointer
- Keep the pixel-grid magnifier beside the pointer and automatically flip it at screen edges
- Highlight the center pixel and show live X/Y coordinates plus selection dimensions
- Switch i3 or other EWMH workspaces during selection; rapid switches are debounced and the preview refreshes after the workspace settles
- Keep the overlay non-focusable and grab only unmodified `Esc`, leaving i3 shortcuts such as `Alt+1` and `Alt+A` available
- Cancel with a global X11 `Esc` listener that does not depend on overlay keyboard focus
- Display a desktop preview during selection without relying on window transparency
- Adapt the internal minimum overlap to short selections instead of failing with `--min-overlap must be smaller than the capture height`
- Detect scrolling content separately from fixed headers and footers and keep fixed regions only once
- Use a conservative browser fallback matcher when the primary matcher is unreliable, reducing premature stops after real scrolling
- When one overlap round is temporarily ambiguous, taller selections continue with small recovery scrolls from the last confirmed frame instead of ending immediately on one PDF/repetitive-layout mismatch
- Detect fixed browser sidebars and the right-edge scrollbar so they are not repeatedly appended to the long image
- Provide fallback matching for PDF/full-window GUI captures and handle multi-row seams, fixed viewport borders, and repeated dark separator lines
- Apply structural verification to repetitive striped or table-like layouts to reduce periodic false matches near the page bottom
- Stay silent during active capture so terminal output cannot feed back into the selected area
- Detect the end of the page automatically and stop when no reliable scrolling motion remains
- Press `Esc` during capture, or `Ctrl+C` in the launching terminal, to stop early and save the confirmed portion
- If the workspace changes after capture starts, stop the current capture and save the confirmed portion instead of mixing another workspace into the image
- Send a desktop notification with the final PNG path after a successful save; notification failure does not affect the screenshot file
- Avoid overwriting existing output files

## Requirements

- x86_64 Linux
- An X11 graphical session
- Native Wayland sessions are not supported
- Desktop notifications use the system `notify-send` client and the Freedesktop Notifications standard; they are not tied to Dunst and work with compatible services such as Dunst, GNOME, KDE Plasma, and Xfce

## Download the stable AppImage

The repository maintains a single GitHub Release: `latest`. After a build-related change on `main` passes all checks, the same `latest` Release is updated and older Releases are removed.

Download from [Latest Release](https://github.com/newyorkthink/scrollshot/releases/latest):

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

1. After launch, use i3 workspace shortcuts to move to the target workspace. After rapid switching stops for about 0.2 seconds, the preview refreshes to the final workspace.
2. Use the full-screen crosshair for alignment while the magnifier remains beside the pointer.
3. Drag to select the actual scrolling area; the magnifier shows X/Y coordinates and selection width/height in real time.
4. Do not move or cover the target after releasing the mouse button.
5. ScrollShot scrolls, detects fixed regions, and stitches the frames. Browsers and PDF/full-window GUI captures use conservative fallback paths when the primary match is unreliable; one temporary mismatch gets small recovery scroll attempts before capture is allowed to stop.
6. The PNG is saved to `~/Pictures/` by default, and a desktop notification shows the final path after a successful save.

Press `Esc` during selection to cancel regardless of keyboard focus. After capture starts, press `Esc` or `Ctrl+C` in the launching terminal to stop early and save the confirmed portion. Changing the i3/EWMH workspace during capture also stops the current capture and saves the confirmed portion so frames from different workspaces are not mixed.

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
# Show the complete command-line help
./scrollshot.AppImage --help
```

## Notes

- The center of the selected area must accept mouse-wheel input.
- Selecting the actual scrolling content is recommended. Fixed headers, fixed footers, browser sidebars, and the right-edge scrollbar are supported, but unrelated windows should not be included.
- PDF/full-window GUI captures conservatively clean fixed viewport borders and known stitch seams; continuous animation or unusual overlays can still reduce matching reliability.
- Do not change zoom, switch tabs, or move the target during capture.
- Video, continuous animation, and large flashing areas may reduce matching reliability.
- Short selections automatically lower the internal overlap requirement; when no reliable motion can be detected, ScrollShot keeps the confirmed single frame or partial result instead of failing on the default overlap value.
- A non-scrollable area stops after the image remains unchanged and is saved as a single frame.
- The desktop notification is an additional post-save hint. If `notify-send` or the notification daemon is unavailable, the PNG itself is unaffected.
- Before launching the system `notify-send`, the AppImage restores the host library search path modified by PyInstaller so the notification client does not accidentally load bundled AppImage libraries.

## GitHub Actions

The `Build ScrollShot AppImage` workflow runs on build-related changes to `main`. README-only or LICENSE-only changes do not spend a full AppImage build.

It performs:

1. Python syntax checks and unit tests.
2. Xvfb selection-preview, full-screen crosshair, pointer-following magnifier, Alt-shortcut availability, rapid workspace switching, focus-preservation, and global `Esc` tests.
3. Fixed-header, fixed-footer, repetitive-layout, browser/PDF fallback stitching, and short-region regression tests.
4. PyInstaller build and AppDir assembly, including desktop-file, icon, and launcher checks.
5. AppImage creation with `appimagetool`.
6. Execution of the AppImage itself and verification of the stitched result.
7. SHA-256 generation.
8. Removal of older Releases and update of the single `latest` Release.

## License

MIT
