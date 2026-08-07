# ScrollShot

[中文](README.md)

ScrollShot is a scrolling screenshot AppImage for **Linux X11**. It automatically scrolls browsers, settings dialogs, and other scrollable areas, detects overlap, and stitches the captured frames into a PNG.

## Features

- Select any rectangular area with the mouse
- Use a pixel-grid magnifier during selection, with the center pixel highlighted and live X/Y coordinates plus selection dimensions
- Switch i3 or other EWMH workspaces during selection; rapid switches are debounced and the preview refreshes only after the workspace settles
- Mark the overlay as non-focusable and grab only unmodified `Esc`, leaving i3 shortcuts such as `Alt+1` and `Alt+A` available
- Cancel with a global X11 `Esc` listener that does not depend on overlay keyboard focus
- Display a desktop preview during selection without relying on window transparency
- Detect scrolling content separately from fixed headers and footers
- Keep fixed toolbars and buttons only once in the final image
- Stay silent during active capture so terminal output cannot feed back into the selected area
- Detect the end of the page automatically
- Stop when no reliable scrolling motion is found instead of treating local changes as page movement
- Avoid overwriting existing output files
- Save the completed portion when interrupted with `Ctrl+C`

## Requirements

- x86_64 Linux
- An X11 graphical session
- Native Wayland sessions are not supported

## Download

Download from [Releases](https://github.com/newyorkthink/scrollshot/releases/latest):

- [scrollshot.AppImage](https://github.com/newyorkthink/scrollshot/releases/download/continuous/scrollshot.AppImage)
- [scrollshot.AppImage.sha256](https://github.com/newyorkthink/scrollshot/releases/download/continuous/scrollshot.AppImage.sha256)

The `continuous` release is updated automatically after the latest `main` build passes all tests. The download URLs remain unchanged.

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
2. Use the magnifier to align with exact edge pixels, then drag to select the area that actually scrolls.
3. The magnifier shows the current X/Y coordinates and, while dragging, the selection width and height.
4. Do not move or cover the target after releasing the mouse button.
5. ScrollShot scrolls, detects fixed regions, and stitches the frames.
6. The PNG is saved to `~/Pictures/` by default.

Press `Esc` to cancel selection regardless of keyboard focus. During capture, press `Ctrl+C` in the launching terminal to save the completed portion.

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
- Selecting the actual scrolling content is recommended. Fixed headers and footers are supported, but unrelated windows should not be included.
- Do not change zoom, switch tabs, or move the target during capture.
- Video, continuous animation, and large flashing areas may reduce matching reliability.
- A non-scrollable area stops after the image remains unchanged and is saved as a single frame.

## GitHub Actions

The `Build ScrollShot AppImage` workflow runs for every commit pushed to `main`, including README-only changes.

It performs:

1. Python syntax checks and unit tests.
2. Xvfb selection-preview, pixel-magnifier, Alt-shortcut availability, rapid workspace switching, focus-preservation, and global `Esc` tests.
3. Fixed-header and fixed-footer scrolling-window tests.
4. PyInstaller build and AppDir assembly.
5. AppImage creation with `appimagetool`.
6. Execution of the AppImage itself and verification of the stitched result.
7. Update of the `continuous` release and SHA-256 file.

## License

MIT
