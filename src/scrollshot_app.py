#!/usr/bin/env python3
"""Packaged and locally installed ScrollShot entry point."""

from __future__ import annotations

import sys
from pathlib import Path

local_library = Path(__file__).resolve().parent.parent / "lib" / "scrollshot"
if local_library.is_dir():
    sys.path.insert(0, str(local_library))

import scrollshot as core
from selection_ui import create_select_region

core.select_region = create_select_region(core)


if __name__ == "__main__":
    raise SystemExit(core.main())
