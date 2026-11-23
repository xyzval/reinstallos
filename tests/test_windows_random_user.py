#!/usr/bin/env python3
"""Regression tests for stable random Windows login accounts."""

import base64
import gzip
import re
import sys
import tempfile
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
    def __init__(self, final_username="K7P4M2", disable_output=False):
        self.final_username = final_username
        self.disable_output = disable_output
        self.commands = []
        self.closed = False

    def exec_command(self, command, timeout=None):
        self.commands.append(command)
        if self.disable_output:
            output = (
                f"FINAL_USER:{self.final_username}\n"
                "FINAL_USER_ENABLED:1\n"
                "FINAL_USER_ADMIN:1\n"
                "FINAL_USER_RDP:1\n"
                "ADMINISTRATOR_DISABLED:1\n"
                "RDP_ENABLED:1\n"
                "RDP_LISTENING:1\n"
            ).encode()
        else:
            output = (
                "OS:Microsoft Windows 11 Enterprise LTSC\n"
                "PORT22:1\n"
                "PORT22022:1\n"
                "PORTCUSTOM:1\n"
                "RDP_ENABLED:1\n"
                "BRANDING_READY:1\n"
                "BRANDING_NAME:ITIL\n"
                "CHROME_REQUESTED:0\n"
                "CHROME_READY:1\n"
                "DISK_READY:1\n"
                "DISK_STATE:ALREADY_MAX\n"
                "PASSWORD_READY:1\n"
                f"FINAL_USER:{self.final_username}\n"
                "FINAL_USER_READY:1\n"
            ).encode()
        return None, _Stream(output), _Stream()

    def close(self):
        self.closed = True


def _decode_gzip_command(command):
    encoded = command.rsplit(" ", 1)[-1]
    wrapper = base64.b64decode(encoded).decode("utf-16le")
    payload = re.search(r"FromBase64String\('([^']+)'\)", wrapper).group(1)
    return gzip.decompress(base64.b64decode(payload)).decode("utf-8")


class WindowsRandomUserTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_vps_file = bot.VPS_FILE
        self.old_jobs_file = bot.JOBS_FILE
        bot.VPS_FILE = str(Path(self.temp.name) / "vps.json")
        bot.JOBS_FILE = str(Path(self.temp.name) / "jobs.json")
        bot.save_vps_list(1001, [{
            "vps_ip": "203.0.113.10",
            "vps_port": 443,
            "vps_user": "root",
            "vps_pass": "source-password",
        }])
        bot.save_reinstall_jobs({})

    def tearDown(self):
        bot.VPS_FILE = self.old_vps_file
        bot.JOBS_FILE = self.old_jobs_file
        self.temp.cleanup()

    def test_username_is_short_unambiguous_stable_and_persisted_in_job(self):
        data = {
            "vps_ip": "203.0.113.10",
            "vps_port": 443,
            "vps_user": "root",
            "vps_pass": "source-password",
            "os_name": bot.WINDOWS_OPTIONS["win11ltsc"]["name"],
            "os_type": "windows",
            "os_cmd": bot.WINDOWS_OPTIONS["win11ltsc"]["cmd"],
            "os_engine": "",
            "lang": "en",
        }
        first = bot.ensure_windows_login_user(1001, data)
        second = bot.ensure_windows_login_user(1001, dict(data))

        self.assertEqual(first, second)
        self.assertTrue(bot.is_managed_windows_username(first))
        self.assertEqual(len(first), 6)
        self.assertNotRegex(first, r"[IO01]")
        saved = bot.load_vps_list(1001)[0]
        self.assertEqual(saved["windows_login_user"], first)

        job = bot.create_reinstall_job(1001, 22, 33, data)
        self.assertEqual(job["windows_login_user"], first)
        self.assertNotIn("vps_pass", job)

    def test_manually_created_managed_user_is_adopted(self):
        data = {
            "vps_ip": "203.0.113.10",
            "vps_port": 443,
            "vps_user": "8GCRNS",
            "vps_pass": bot.WINDOWS_INSTALL_PASSWORD,
            "os_type": "windows",
        }
        self.assertEqual(bot.ensure_windows_login_user(1001, data), "8GCRNS")
        self.assertEqual(
            bot.load_vps_list(1001)[0]["windows_login_user"], "8GCRNS"
        )

    def test_finalizer_verifies_new_user_before_disabling_sid_500(self):
        ssh = _WindowsSSH("K7P4M2")
        with patch.object(bot, "_connect_with_credentials", return_value=ssh) as connect, patch.object(
            bot, "detect_remote_os_sync", return_value="windows"
        ), patch.object(
            bot, "find_working_ssh_port_sync", side_effect=[(443, ""), (443, "")]
        ) as finder, patch.object(
            bot, "disable_windows_bootstrap_admin_sync", return_value=(True, "")
        ) as disable:
            ok, error, detected = bot.verify_windows_install_sync(
                "203.0.113.10",
                preferred_port=443,
                final_username="K7P4M2",
            )

        self.assertTrue(ok, error)
        self.assertIn("Enterprise LTSC", detected)
        self.assertEqual(connect.call_args_list[0].args[2:4], ("K7P4M2", "digicore"))
        self.assertEqual(finder.call_count, 2)
        self.assertEqual(finder.call_args_list[0].args[1:3], ("K7P4M2", "digicore"))
        disable.assert_called_once_with("203.0.113.10", 443, "K7P4M2")
        script = _decode_gzip_command(ssh.commands[-1])
        self.assertIn("$finalAccount = 'K7P4M2'", script)
        self.assertIn("S-1-5-32-544", script)
        self.assertIn("S-1-5-32-555", script)
        self.assertNotIn("__REINSTALLOS_FINAL_USERNAME__", script)

    def test_failed_fresh_login_never_disables_administrator(self):
        ssh = _WindowsSSH("K7P4M2")
        with patch.object(bot, "_connect_with_credentials", return_value=ssh), patch.object(
            bot, "detect_remote_os_sync", return_value="windows"
        ), patch.object(
            bot, "find_working_ssh_port_sync", return_value=(0, "authentication failed")
        ), patch.object(bot, "disable_windows_bootstrap_admin_sync") as disable:
            ok, error, _ = bot.verify_windows_install_sync(
                "203.0.113.10",
                preferred_port=443,
                final_username="K7P4M2",
            )

        self.assertFalse(ok)
        self.assertIn("Akun final gagal diverifikasi", error)
        disable.assert_not_called()

    def test_sid_500_disable_is_verified_from_replacement_account(self):
        ssh = _WindowsSSH("K7P4M2", disable_output=True)
        with patch.object(bot, "_connect_with_credentials", return_value=ssh) as connect, patch.object(
            bot, "detect_remote_os_sync", return_value="windows"
        ):
            ok, error = bot.disable_windows_bootstrap_admin_sync(
                "203.0.113.10", 443, "K7P4M2"
            )

        self.assertTrue(ok, error)
        connect.assert_called_once_with(
            "203.0.113.10", 443, "K7P4M2", "digicore", timeout=15
        )
        script = _decode_gzip_command(ssh.commands[-1])
        self.assertIn("-500$", script)
        self.assertIn('/active:no', script)
        self.assertIn("ADMINISTRATOR_DISABLED", script)

    def test_completed_job_updates_saved_credentials_to_random_user(self):
        job = {
            "user_id": "1001",
            "vps_ip": "203.0.113.10",
            "vps_port": 443,
            "os_type": "windows",
            "windows_login_user": "K7P4M2",
        }
        bot.update_vps_credentials_after_reinstall(job, verified_port=443)
        saved = bot.load_vps_list(1001)[0]
        self.assertEqual(saved["vps_user"], "K7P4M2")
        self.assertEqual(saved["vps_pass"], "digicore")
        self.assertEqual(saved["windows_login_user"], "K7P4M2")
        self.assertEqual(saved["vps_port"], 443)


if __name__ == "__main__":
    unittest.main(verbosity=2)
