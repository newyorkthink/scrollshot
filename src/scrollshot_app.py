#!/usr/bin/env python3
"""Packaged and locally installed ScrollShot entry point."""

from __future__ import annotations

import sys
from pathlib import Path

local_library = Path(__file__).resolve().parent.parent / "lib" / "scrollshot"
if local_library.is_dir():
    sys.path.insert(0, str(local_library))

import scrollshot as core
from capture_options import effective_min_overlap
from selection_guides import create_select_region
from structural_match import create_structural_estimator

_interactive_selector = create_select_region(core)
_core_run_capture = core.run_capture
_core_estimate_vertical_shift = core.estimate_vertical_shift
core.select_region = _interactive_selector
core.estimate_vertical_shift = create_structural_estimator(
    core,
    _core_estimate_vertical_shift,
)


def run_capture_with_adaptive_overlap(args):
    """Adjust overlap after the final region height is known, then capture."""

    if args.geometry is not None:
        args.min_overlap = effective_min_overlap(
            args.min_overlap,
            args.geometry.height,
        )
        return _core_run_capture(args)

    selector = core.select_region

    def select_and_adjust():
        region = selector()
        args.min_overlap = effective_min_overlap(args.min_overlap, region.height)
        return region

    core.select_region = select_and_adjust
    try:
        return _core_run_capture(args)
    finally:
        core.select_region = selector


core.run_capture = run_capture_with_adaptive_overlap


if __name__ == "__main__":
    raise SystemExit(core.main())
