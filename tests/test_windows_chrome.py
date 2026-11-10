#!/usr/bin/env python3
"""Regression tests for scoped Chrome installation on Windows 11 LTSC 2024."""

import base64
import gzip
import inspect
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bot  # noqa: E402


class _Channel:
    def recv_exit_status(self):
        return 0


class _Stream:
    def __init__(self, data=b""):
        self.data = data
        self.channel = _Channel()

    def read(self):
        return self.data


class _WindowsSSH:
    def __init__(self, chrome_ready=True):
        self.chrome_ready = chrome_ready
        self.commands = []
        self.timeouts = []

    def exec_command(self, command, timeout=None):
        self.commands.append(command)
        self.timeouts.append(timeout)
        chrome = "1" if self.chrome_ready else "0"
        error = "" if self.chrome_ready else "CHROME_ERROR:signature rejected\n"
        version = "CHROME_VERSION:140.0.7339.0\n" if self.chrome_ready else ""
        output = (
            "OS:Microsoft Windows 11 Enterprise LTSC\n"
            "PORT22:1\n"
            "PORT22022:1\n"
            "PORTCUSTOM:1\n"
            "RDP_ENABLED:1\n"
            "BRANDING_READY:1\n"
            "BRANDING_NAME:ITIL\n"
            "CHROME_REQUESTED:1\n"
            f"CHROME_READY:{chrome}\n"
            f"{version}"
            f"{error}"
            "DISK_READY:1\n"
            "DISK_STATE:ALREADY_MAX\n"
            "PASSWORD_READY:1\n"
        ).encode()
        return None, _Stream(output), _Stream()

    def close(self):
        pass


class WindowsChromeTests(unittest.TestCase):
    def test_scope_is_only_newest_ltsc_option(self):
        newest = bot.WINDOWS_OPTIONS["win11ltsc"]["name"]
        self.assertTrue(bot._windows_requires_chrome(newest))
        for key, option in bot.WINDOWS_OPTIONS.items():
            if key != "win11ltsc":
                self.assertFalse(
                    bot._windows_requires_chrome(option["name"]),
                    f"Chrome unexpectedly enabled for {key}",
                )
        self.assertFalse(bot._windows_requires_chrome(""))
        old_start, old_finish = bot._windows_chrome_powershell_blocks(False)
        self.assertNotIn(bot.CHROME_ENTERPRISE_MSI_URL, old_start + old_finish)
        self.assertNotIn("DownloadFileTaskAsync", old_start + old_finish)
        self.assertIn("CHROME_REQUESTED:0", old_finish)

        monitor_source = inspect.getsource(bot.monitor_reinstall_job)
        self.assertIn("_windows_requires_chrome(current.get(\"os_name\", \"\"))", monitor_source)

    def test_script_downloads_official_msi_early_and_verifies_google(self):
        start, finish = bot._windows_chrome_powershell_blocks(True)
        self.assertIn(bot.CHROME_ENTERPRISE_MSI_URL, start)
        self.assertIn("$chromeRequested = 1", start)
        self.assertIn("DownloadFileTaskAsync", start)
        self.assertIn("$env:ProgramFiles", start)
        self.assertNotIn("ProgramFiles(x86)", start)
        self.assertIn("Get-AuthenticodeSignature", finish)
        self.assertIn("CN=Google LLC", finish)
        self.assertIn("/qn /norestart", finish)
        self.assertIn("@(0, 1641, 3010)", finish)
        self.assertIn("Google Chrome.lnk", finish)
        self.assertIn("CommonDesktopDirectory", finish)
        self.assertIn('Write-Output "CHROME_READY:$chromeReady"', finish)
        self.assertIn('Write-Output "CHROME_VERSION:$chromeVersion"', finish)
        self.assertNotIn("__REINSTALLOS_CHROME_MSI_URL__", start)

    def test_finalizer_requires_chrome_ready_and_version_when_requested(self):
        ssh = _WindowsSSH(chrome_ready=True)
        with patch.object(bot, "_connect_with_credentials", return_value=ssh), patch.object(
            bot, "detect_remote_os_sync", return_value="windows"
        ), patch.object(bot, "find_working_ssh_port_sync", return_value=(443, "")):
            ok, error, detected = bot.verify_windows_install_sync(
                "203.0.113.10", preferred_port=443, install_chrome=True
            )

        self.assertTrue(ok, error)
        self.assertIn("Windows 11 Enterprise LTSC", detected)
        self.assertEqual(ssh.timeouts[-1], 600)
        command = ssh.commands[-1]
        self.assertLess(len(command), 32767)
        encoded = command.rsplit(" ", 1)[-1]
        wrapper = base64.b64decode(encoded).decode("utf-16le")
        payload = re.search(r"FromBase64String\('([^']+)'\)", wrapper).group(1)
        script = gzip.decompress(base64.b64decode(payload)).decode("utf-8")
        self.assertLess(script.index("DownloadFileTaskAsync"), script.index("Resize-Partition"))
        self.assertLess(script.index("Resize-Partition"), script.index("GetAwaiter().GetResult()"))
        self.assertNotIn("__REINSTALLOS_CHROME_START_BLOCK__", script)
        self.assertNotIn("__REINSTALLOS_CHROME_FINISH_BLOCK__", script)

        failed_ssh = _WindowsSSH(chrome_ready=False)
        with patch.object(
            bot, "_connect_with_credentials", return_value=failed_ssh
        ), patch.object(bot, "detect_remote_os_sync", return_value="windows"), patch.object(
            bot, "find_working_ssh_port_sync", return_value=(443, "")
        ):
            ok, error, _ = bot.verify_windows_install_sync(
                "203.0.113.10", preferred_port=443, install_chrome=True
            )
        self.assertFalse(ok)
        self.assertIn("Google Chrome belum siap", error)
        self.assertIn("signature rejected", error)


if __name__ == "__main__":
    unittest.main(verbosity=2)
