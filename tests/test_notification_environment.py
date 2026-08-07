#!/usr/bin/env python3
"""Regression tests for launcher-safe desktop notification environment handling."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import scrollshot_app


class NotificationEnvironmentTests(unittest.TestCase):
    """Keep launcher/AppImage environment pollution out of host notify-send."""

    def test_rebuilds_session_bus_and_removes_launcher_library_paths(self) -> None:
        launcher_environment = {
            "PATH": "/usr/bin:/bin",
            "XDG_RUNTIME_DIR": "/run/user/1000",
            "DBUS_SESSION_BUS_ADDRESS": "unix:path=/tmp/kando-private-bus",
            "LD_LIBRARY_PATH": "/tmp/.mount_Kando/usr/lib",
            "LD_LIBRARY_PATH_ORIG": "/tmp/.mount_Kando/usr/lib",
            "LD_PRELOAD": "/tmp/.mount_Kando/usr/lib/libfake.so",
        }

        with (
            mock.patch.dict(os.environ, launcher_environment, clear=True),
            mock.patch.object(scrollshot_app.os, "getuid", return_value=1000),
            mock.patch.object(
                scrollshot_app.Path,
                "is_socket",
                autospec=True,
                side_effect=lambda path: str(path) == "/run/user/1000/bus",
            ),
        ):
            environment = scrollshot_app._notification_environment()

        self.assertEqual(
            environment["DBUS_SESSION_BUS_ADDRESS"],
            "unix:path=/run/user/1000/bus",
        )
        self.assertEqual(environment["XDG_RUNTIME_DIR"], "/run/user/1000")
        self.assertNotIn("LD_LIBRARY_PATH", environment)
        self.assertNotIn("LD_LIBRARY_PATH_ORIG", environment)
        self.assertNotIn("LD_PRELOAD", environment)

    def test_falls_back_from_invalid_launcher_runtime_dir(self) -> None:
        launcher_environment = {
            "PATH": "/usr/bin:/bin",
            "XDG_RUNTIME_DIR": "/tmp/kando-runtime",
            "DBUS_SESSION_BUS_ADDRESS": "unix:path=/tmp/kando-private-bus",
        }

        with (
            mock.patch.dict(os.environ, launcher_environment, clear=True),
            mock.patch.object(scrollshot_app.os, "getuid", return_value=1000),
            mock.patch.object(
                scrollshot_app.Path,
                "is_socket",
                autospec=True,
                side_effect=lambda path: str(path) == "/run/user/1000/bus",
            ),
        ):
            environment = scrollshot_app._notification_environment()

        self.assertEqual(environment["XDG_RUNTIME_DIR"], "/run/user/1000")
        self.assertEqual(
            environment["DBUS_SESSION_BUS_ADDRESS"],
            "unix:path=/run/user/1000/bus",
        )


if __name__ == "__main__":
    unittest.main()
