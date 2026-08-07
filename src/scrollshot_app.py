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
from capture_runtime import create_capture_runner
from fallback_match import create_fallback_estimator
from resilient_stitch import create_resilient_stitcher
from seam_cleanup import create_seam_cleaning_stitcher
from selection_guides import create_select_region
from structural_match import create_structural_estimator

_interactive_selector = create_select_region(core)
_core_estimate_vertical_shift = core.estimate_vertical_shift
_core_stitch_frames = core.stitch_frames
core.select_region = _interactive_selector

_structural_estimator = create_structural_estimator(
    core,
    _core_estimate_vertical_shift,
)
core.estimate_vertical_shift = create_fallback_estimator(
    core,
    _structural_estimator,
)

_resilient_stitcher = create_resilient_stitcher(
    core,
    _core_stitch_frames,
)
core.stitch_frames = create_seam_cleaning_stitcher(
    core,
    _resilient_stitcher,
)

core.run_capture = create_capture_runner(
    core,
    effective_min_overlap,
)


if __name__ == "__main__":
    raise SystemExit(core.main())
