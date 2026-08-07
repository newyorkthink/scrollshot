#!/usr/bin/env python3
"""Runtime capture option adjustments for ScrollShot."""

from __future__ import annotations

MIN_RUNTIME_OVERLAP = 8
MATCHING_HEADROOM = 36


def effective_min_overlap(requested: int, region_height: int) -> int:
    """Cap overlap to a value supported by the selected capture height."""

    requested = int(requested)
    region_height = int(region_height)
    if requested < MIN_RUNTIME_OVERLAP:
        raise ValueError("requested overlap must be at least 8 pixels")
    if region_height <= 0:
        raise ValueError("capture height must be positive")

    supported = max(MIN_RUNTIME_OVERLAP, region_height - MATCHING_HEADROOM)
    return min(requested, supported)
