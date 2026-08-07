#!/usr/bin/env python3
"""Pointer-following crosshair magnifier helpers for ScrollShot."""

from __future__ import annotations

from types import ModuleType

import selection_ui as baseline

MAGNIFIER_OFFSET = 28


def position_floating_panel(
    pointer_x: int,
    pointer_y: int,
    panel_width: int,
    panel_height: int,
    screen_width: int,
    screen_height: int,
    *,
    offset: int = MAGNIFIER_OFFSET,
    margin: int = 8,
) -> tuple[int, int]:
    """Place a panel beside the pointer and flip it at screen edges."""

    pointer_x = int(pointer_x)
    pointer_y = int(pointer_y)
    panel_width = max(1, int(panel_width))
    panel_height = max(1, int(panel_height))
    screen_width = max(1, int(screen_width))
    screen_height = max(1, int(screen_height))
    offset = max(0, int(offset))
    margin = max(0, int(margin))

    panel_x = pointer_x + offset
    panel_y = pointer_y + offset
    if panel_x + panel_width + margin > screen_width:
        panel_x = pointer_x - panel_width - offset
    if panel_y + panel_height + margin > screen_height:
        panel_y = pointer_y - panel_height - offset

    maximum_x = max(margin, screen_width - panel_width - margin)
    maximum_y = max(margin, screen_height - panel_height - margin)
    return (
        max(margin, min(maximum_x, panel_x)),
        max(margin, min(maximum_y, panel_y)),
    )


class PointerMagnifier(baseline.PixelMagnifier):
    """Pixel magnifier that follows the pointer and marks its center axes."""

    MARGIN = 8

    def __init__(
        self,
        canvas,
        root,
        core: ModuleType,
        photo_image_type,
        screen_width: int,
        screen_height: int,
    ) -> None:
        super().__init__(
            canvas,
            root,
            core,
            photo_image_type,
            screen_width,
            screen_height,
        )
        self.center_vertical = canvas.create_line(
            0,
            0,
            1,
            1,
            fill="#38bdf8",
            width=2,
            tags=("magnifier",),
        )
        self.center_horizontal = canvas.create_line(
            0,
            0,
            1,
            1,
            fill="#38bdf8",
            width=2,
            tags=("magnifier",),
        )
        self.hide()

    def _position(self, x: int, y: int) -> tuple[int, int]:
        return position_floating_panel(
            x,
            y,
            self.panel_width,
            self.panel_height,
            self.screen_width,
            self.screen_height,
            offset=MAGNIFIER_OFFSET,
            margin=self.MARGIN,
        )

    def update(self, frame, x: int, y: int, start=None) -> None:
        super().update(frame, x, y, start)

        x = max(0, min(self.screen_width - 1, int(x)))
        y = max(0, min(self.screen_height - 1, int(y)))
        panel_x, panel_y = self._position(x, y)
        image_x = panel_x + self.BORDER
        image_y = panel_y + self.BORDER
        image_right = image_x + self.image_size
        image_bottom = image_y + self.image_size
        center = baseline.MAGNIFIER_SOURCE_SIZE // 2
        center_x = image_x + center * baseline.MAGNIFIER_ZOOM + baseline.MAGNIFIER_ZOOM // 2
        center_y = image_y + center * baseline.MAGNIFIER_ZOOM + baseline.MAGNIFIER_ZOOM // 2

        self.canvas.coords(
            self.center_vertical,
            center_x,
            image_y,
            center_x,
            image_bottom,
        )
        self.canvas.coords(
            self.center_horizontal,
            image_x,
            center_y,
            image_right,
            center_y,
        )
        self.canvas.itemconfigure("magnifier", state="normal")
        self.canvas.tag_raise(self.center_vertical)
        self.canvas.tag_raise(self.center_horizontal)
        self.canvas.tag_raise(self.pixel)
        self.canvas.tag_raise(self.label)
