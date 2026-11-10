#!/usr/bin/env python3
"""Regression tests for safe Windows branding cleanup and verification."""

import base64
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bot  # noqa: E402


class _Channel:
    def __init__(self, rc=0):
        self.rc = rc

    def recv_exit_status(self):
        return self.rc


class _Stream:
    def __init__(self, data=b"", rc=0):
        self.data = data
        self.channel = _Channel(rc)

    def read(self):
        return self.data


class _WindowsSSH:
    def __init__(self, branding_ready=True):
        self.branding_ready = branding_ready
        self.commands = []

    def exec_command(self, command, timeout=None):
        self.commands.append(command)
        branding = "1" if self.branding_ready else "0"
        error = "" if self.branding_ready else "BRANDING_ERROR:cleanup failed\n"
        output = (
            "OS:Microsoft Windows 11 Enterprise LTSC\n"
            "PORT22:1\n"
            "PORT22022:1\n"
            "PORTCUSTOM:1\n"
            "RDP_ENABLED:1\n"
            f"BRANDING_READY:{branding}\n"
            "BRANDING_NAME:ITIL\n"
            f"{error}"
            "DISK_READY:1\n"
            "DISK_STATE:ALREADY_MAX\n"
            "PASSWORD_READY:1\n"
        ).encode()
        return None, _Stream(output), _Stream()

    def close(self):
        pass


class WindowsBrandingTests(unittest.TestCase):
    def test_script_is_scoped_backed_up_and_idempotent(self):
        script = bot._windows_branding_powershell()
        self.assertEqual(bot.WINDOWS_BRAND_NAME, "ITIL")
        self.assertIn("branding-before-ITIL.json", script)
        self.assertIn("Manufacturer' -Value $brandName", script)
        self.assertIn("RegisteredOwner' -Value $brandName", script)
        self.assertIn("RegisteredOrganization' -Value $brandName", script)
        self.assertIn("TranscodedWallpaper", script)
        self.assertIn("(?i)teddysun", script)
        self.assertIn("BRANDING_READY:$brandingReady", script)
        self.assertNotIn("__REINSTALLOS_BRAND_NAME__", script)
        for forbidden in ("bcdedit", "bootmgr", "slmgr", "WinSxS", "System32\\drivers"):
            self.assertNotIn(forbidden, script)

    def test_finalizer_embeds_and_requires_branding_success(self):
        ssh = _WindowsSSH(branding_ready=True)
        with patch.object(bot, "_connect_with_credentials", return_value=ssh), patch.object(
            bot, "detect_remote_os_sync", return_value="windows"
        ), patch.object(bot, "find_working_ssh_port_sync", return_value=(443, "")):
            ok, error, detected = bot.verify_windows_install_sync(
                "203.0.113.10", preferred_port=443
            )

        self.assertTrue(ok, error)
        self.assertIn("Windows 11 Enterprise LTSC", detected)
        encoded = ssh.commands[-1].rsplit(" ", 1)[-1]
        script = base64.b64decode(encoded).decode("utf-16le")
        self.assertIn("branding-before-ITIL.json", script)
        self.assertIn('Write-Output "BRANDING_NAME:ITIL"', script)
        self.assertNotIn("__REINSTALLOS_BRANDING_BLOCK__", script)

        failed_ssh = _WindowsSSH(branding_ready=False)
        with patch.object(
            bot, "_connect_with_credentials", return_value=failed_ssh
        ), patch.object(bot, "detect_remote_os_sync", return_value="windows"), patch.object(
            bot, "find_working_ssh_port_sync", return_value=(443, "")
        ):
            ok, error, _ = bot.verify_windows_install_sync(
                "203.0.113.10", preferred_port=443
            )
        self.assertFalse(ok)
        self.assertIn("Branding Windows belum dapat dibersihkan", error)


if __name__ == "__main__":
    unittest.main(verbosity=2)
