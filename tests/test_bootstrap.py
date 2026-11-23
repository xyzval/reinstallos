#!/usr/bin/env python3
"""Regression tests for per-user UpCloud bootstrap onboarding."""

import inspect
import os
import subprocess
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


class _HostKey:
    def __init__(self, value=b"stable-host-key"):
        self.value = value

    def asbytes(self):
        return self.value


class _Transport:
    def __init__(self, host_key=b"stable-host-key"):
        self.host_key = host_key

    def get_remote_server_key(self):
        return _HostKey(self.host_key)


class _SSH:
    def __init__(self, ready=False, host_key=b"stable-host-key"):
        self.ready = ready
        self.host_key = host_key
        self.commands = []
        self.closed = False

    def get_transport(self):
        return _Transport(self.host_key)

    def exec_command(self, command, timeout=None):
        self.commands.append(command)
        output = b"REINSTALLOS_PASSWORD_READY\n" if self.ready else b""
        return None, _Stream(output), _Stream()

    def close(self):
        self.closed = True


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_keys_dir = bot.SSH_KEYS_DIR
        self.old_vps_file = bot.VPS_FILE
        bot.SSH_KEYS_DIR = str(Path(self.temp.name) / "ssh_keys")
        bot.VPS_FILE = str(Path(self.temp.name) / "vps_data.json")

    def tearDown(self):
        bot.SSH_KEYS_DIR = self.old_keys_dir
        bot.VPS_FILE = self.old_vps_file
        self.temp.cleanup()

    def test_keys_are_stable_isolated_and_owner_only(self):
        first_path, first_public = bot.ensure_user_bootstrap_key(1001)
        same_path, same_public = bot.ensure_user_bootstrap_key(1001)
        second_path, second_public = bot.ensure_user_bootstrap_key(2002)

        self.assertEqual((first_path, first_public), (same_path, same_public))
        self.assertNotEqual(first_path, second_path)
        self.assertNotEqual(first_public, second_public)
        self.assertEqual(os.stat(bot.SSH_KEYS_DIR).st_mode & 0o777, 0o700)
        self.assertEqual(os.stat(Path(first_path).parent).st_mode & 0o777, 0o700)
        self.assertEqual(os.stat(first_path).st_mode & 0o777, 0o600)
        self.assertEqual(
            bot._load_private_key(first_path).get_base64(), first_public.split()[1]
        )

    def test_cloud_init_is_key_only_and_enables_22_and_443(self):
        private_path, public_key = bot.ensure_user_bootstrap_key(1001)
        cloud_init = bot.build_bootstrap_cloud_init(public_key)

        self.assertTrue(cloud_init.startswith("#cloud-config\n"))
        self.assertIn("Port 22\n      Port 443", cloud_init)
        self.assertIn("PermitRootLogin prohibit-password", cloud_init)
        self.assertIn("PasswordAuthentication no", cloud_init)
        self.assertNotIn(bot.LINUX_INSTALL_PASSWORD, cloud_init)
        self.assertNotIn(Path(private_path).read_text(), cloud_init)
        with self.assertRaises(ValueError):
            bot.build_bootstrap_cloud_init(public_key + "\nwrite_files: []")

    def test_key_marker_and_wizard_controls(self):
        parsed = bot.parse_vps_detail("203.0.113.10:443@root:KEY")
        self.assertEqual(parsed["auth_type"], "bootstrap_key")
        self.assertEqual(parsed["vps_pass"], "")
        ports = [
            button.callback_data
            for row in bot.get_wizard_port_keyboard().inline_keyboard
            for button in row
        ]
        methods = [
            button.callback_data
            for row in bot.get_wizard_auth_keyboard().inline_keyboard
            for button in row
        ]
        self.assertIn("wiz_port_443", ports)
        self.assertIn("wiz_auth_key", methods)

    def test_key_bootstrap_enables_and_verifies_password(self):
        private_path, _ = bot.ensure_user_bootstrap_key(1001)
        initial = _SSH(ready=True)
        verified = _SSH()
        password_attempts = []
        data = {
            "vps_ip": "203.0.113.10",
            "vps_port": 443,
            "vps_user": "root",
            "vps_pass": "",
            "auth_type": "bootstrap_key",
            "ssh_key_path": private_path,
        }

        def password_connect(ip, port, username, password, timeout=12, expected_host_key=""):
            password_attempts.append((ip, port, username, password))
            return verified

        with patch.object(bot, "_connect_with_key", return_value=initial), patch.object(
            bot, "_connect_with_credentials", side_effect=password_connect
        ), patch.object(bot, "detect_remote_os_sync", return_value="linux"):
            ok, error, prepared = bot.bootstrap_password_from_key_sync(data)

        self.assertTrue(ok, error)
        self.assertEqual(prepared["vps_pass"], bot.LINUX_INSTALL_PASSWORD)
        self.assertTrue(prepared["key_fallback"])
        self.assertEqual(prepared["ssh_key_path"], private_path)
        self.assertEqual(
            password_attempts,
            [("203.0.113.10", 443, "root", bot.LINUX_INSTALL_PASSWORD)],
        )
        script = initial.commands[-1]
        self.assertIn("Port 22\nPort 22022\nPort 443\nPermitRootLogin yes", script)
        self.assertIn("PasswordAuthentication yes", script)
        self.assertIn("00-reinstallos-access.conf", script)
        self.assertIn("rm -f /etc/ssh/sshd_config.d/00-reinstallos-bootstrap.conf", script)
        self.assertNotIn("Port 443\\nPermitRootLogin", script)
        syntax = subprocess.run(
            ["sh", "-n"], input=script, text=True, capture_output=True, check=False
        )
        self.assertEqual(syntax.returncode, 0, syntax.stderr)

    def test_saved_endpoint_retries_one_transient_reset(self):
        data = {
            "vps_ip": "203.0.113.10",
            "vps_port": 443,
            "vps_user": "Administrator",
            "vps_pass": bot.WINDOWS_INSTALL_PASSWORD,
            "auth_type": "password",
        }
        connected = _SSH()
        attempts = []

        def password_connect(ip, port, username, password, timeout=12, expected_host_key=""):
            attempts.append((ip, port, username, password))
            if len(attempts) == 1:
                raise ConnectionResetError("connection reset by peer")
            return connected

        with patch.object(
            bot, "_connect_with_credentials", side_effect=password_connect
        ), patch.object(bot, "detect_remote_os_sync", return_value="windows"), patch.object(
            bot._time, "sleep"
        ) as sleep:
            ssh, remote_os, port, username = bot.connect_target_sync(data)

        self.assertIs(ssh, connected)
        self.assertEqual((remote_os, port, username), ("windows", 443, "Administrator"))
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0], attempts[1])
        sleep.assert_called_once_with(0.75)

    def test_persistent_saved_endpoint_reset_uses_only_saved_identity_on_alternatives(self):
        data = {
            "vps_ip": "203.0.113.10",
            "vps_port": 443,
            "vps_user": "Administrator",
            "vps_pass": bot.WINDOWS_INSTALL_PASSWORD,
            "auth_type": "password",
            "ssh_host_key_sha256": bot._ssh_host_key_sha256(_SSH()),
        }
        attempts = []

        def password_connect(ip, port, username, password, timeout=12, expected_host_key=""):
            attempts.append((port, username, password, expected_host_key))
            raise ConnectionResetError("connection reset by peer")

        with patch.object(
            bot, "_connect_with_credentials", side_effect=password_connect
        ), patch.object(bot._time, "sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "port alternatif"):
                bot.connect_target_sync(data)

        self.assertEqual([item[0] for item in attempts], [443, 443, 443, 22, 22022])
        self.assertTrue(
            all(
                item[1] == "Administrator"
                and item[2] == bot.WINDOWS_INSTALL_PASSWORD
                and item[3] == data["ssh_host_key_sha256"]
                for item in attempts
            )
        )
        self.assertEqual(sleep.call_count, 2)
        self.assertNotIn(bot.WINDOWS_IMAGE_PASSWORD, [item[2] for item in attempts])
        self.assertNotIn(bot.LINUX_INSTALL_PASSWORD, [item[2] for item in attempts])

    def test_pinned_policy_rejects_mismatch_before_credentials(self):
        expected = bot._ssh_host_key_sha256(_SSH(host_key=b"expected"))
        policy = bot._PinnedHostKeyPolicy(expected)
        with self.assertRaisesRegex(bot._HostKeyMismatchError, "identitas host tidak cocok"):
            policy.missing_host_key(None, "203.0.113.10", _HostKey(b"unexpected"))

    def test_unreachable_saved_port_adopts_host_key_pinned_alternative(self):
        pinned = bot._ssh_host_key_sha256(_SSH())
        data = {
            "vps_ip": "203.0.113.10",
            "vps_port": 22022,
            "vps_user": "root",
            "vps_pass": "one-saved-secret",
            "auth_type": "password",
            "ssh_host_key_sha256": pinned,
        }
        attempts = []
        connected = _SSH()

        def password_connect(ip, port, username, password, timeout=12, expected_host_key=""):
            attempts.append((port, username, password, expected_host_key))
            if port == 22022:
                raise TimeoutError("timed out")
            return connected

        with patch.object(
            bot, "_connect_with_credentials", side_effect=password_connect
        ), patch.object(bot, "detect_remote_os_sync", return_value="linux"), patch.object(
            bot._time, "sleep"
        ):
            ssh, remote_os, port, username = bot.connect_target_sync(data)

        self.assertIs(ssh, connected)
        self.assertEqual((remote_os, port, username), ("linux", 22, "root"))
        self.assertEqual(data["vps_port"], 22)
        self.assertEqual([item[0] for item in attempts], [22022, 22022, 22022, 22])
        self.assertTrue(all(item[2] == "one-saved-secret" for item in attempts))
        self.assertTrue(all(item[3] == pinned for item in attempts))

    def test_unpinned_alternative_is_rejected_before_authentication(self):
        data = {
            "vps_ip": "203.0.113.10",
            "vps_port": 22022,
            "vps_user": "root",
            "vps_pass": "one-saved-secret",
            "auth_type": "password",
        }

        def password_connect(ip, port, username, password, timeout=12, expected_host_key=""):
            if port == 22022:
                raise TimeoutError("timed out")
            return _SSH()

        with patch.object(
            bot, "_connect_with_credentials", side_effect=password_connect
        ), patch.object(bot._time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "Identitas host belum tersimpan"):
                bot.connect_target_sync(data)

    def test_verified_alternative_is_persisted_per_user(self):
        original = {
            "vps_ip": "203.0.113.10",
            "vps_port": 22022,
            "vps_user": "root",
            "vps_pass": "secret",
        }
        other_user = dict(original)
        bot.save_vps_list(1001, [original])
        bot.save_vps_list(2002, [other_user])
        verified = dict(original)
        verified.update(
            vps_port=443,
            ssh_host_key_sha256="SHA256:verified-host-identity",
        )

        bot.persist_reinstall_preflight_endpoint(1001, 22022, verified)

        adopted = bot.load_vps_list(1001)[0]
        untouched = bot.load_vps_list(2002)[0]
        self.assertEqual(adopted["vps_port"], 443)
        self.assertEqual(
            adopted["ssh_host_key_sha256"], "SHA256:verified-host-identity"
        )
        self.assertEqual(untouched["vps_port"], 22022)
        self.assertNotIn("ssh_host_key_sha256", untouched)

    def test_preflight_persistence_failure_blocks_installer_launch(self):
        data = {
            "vps_ip": "203.0.113.10",
            "vps_port": 22022,
            "vps_user": "root",
            "vps_pass": "secret",
            "ssh_host_key_sha256": bot._ssh_host_key_sha256(_SSH()),
        }
        connected = _SSH()

        def reject_persistence(verified_data):
            raise RuntimeError("cannot persist verified endpoint")

        with patch.object(
            bot,
            "connect_target_sync",
            return_value=(connected, "linux", 22022, "root"),
        ), patch.object(bot, "_prepare_installer_assets") as prepare, patch.object(
            bot, "_launch_from_linux"
        ) as launch:
            ok, error = bot.launch_reinstall_sync(
                data, preflight_callback=reject_persistence
            )

        self.assertFalse(ok)
        self.assertIn("cannot persist verified endpoint", error)
        prepare.assert_not_called()
        launch.assert_not_called()
        self.assertTrue(connected.closed)

    def test_launch_state_must_persist_before_installer_command(self):
        data = {
            "vps_ip": "203.0.113.10",
            "vps_port": 22022,
            "vps_user": "root",
            "vps_pass": "secret",
            "os_type": "linux",
            "ssh_host_key_sha256": bot._ssh_host_key_sha256(_SSH()),
        }
        connected = _SSH()

        def reject_launch_state():
            raise RuntimeError("cannot persist launch state")

        with patch.object(
            bot,
            "connect_target_sync",
            return_value=(connected, "linux", 22022, "root"),
        ), patch.object(
            bot, "_prepare_installer_assets", return_value=(b"sh", b"bat", b"")
        ), patch.object(bot, "_launch_from_linux") as launch:
            ok, error = bot.launch_reinstall_sync(
                data,
                preflight_callback=lambda verified: None,
                launch_attempt_callback=reject_launch_state,
            )

        self.assertFalse(ok)
        self.assertIn("cannot persist launch state", error)
        launch.assert_not_called()

    def test_add_port_is_additive_and_handles_ubuntu_ssh_socket(self):
        source = inspect.getsource(bot.edit_port_handler)
        self.assertIn('echo "Port $OLD_PORT" >> "$TMP"', source)
        self.assertIn('echo "Port $NEW_PORT" >> "$TMP"', source)
        self.assertIn("systemctl restart ssh.socket", source)
        self.assertIn('if ! is_listening "$OLD_PORT"', source)
        self.assertIn('if ! is_listening "$NEW_PORT"', source)
        self.assertIn("$activePorts + $oldPort + $newPort | Sort-Object -Unique", source)

    def test_failure_message_distinguishes_installer_launch_state(self):
        self.assertEqual(
            bot.reinstall_failure_launch_notice({}),
            "Installer belum dijalankan.",
        )
        self.assertIn(
            "status mulainya tidak dapat dipastikan",
            bot.reinstall_failure_launch_notice({"launch_attempted": True}),
        )
        self.assertEqual(
            bot.reinstall_failure_launch_notice({"installer_launched": True}),
            "Installer sudah dijalankan dan tidak dibatalkan.",
        )

    def test_saved_key_remains_a_connection_fallback(self):
        private_path, _ = bot.ensure_user_bootstrap_key(1001)
        data = {
            "vps_ip": "203.0.113.10",
            "vps_port": 443,
            "vps_user": "root",
            "vps_pass": bot.LINUX_INSTALL_PASSWORD,
            "auth_type": "password",
            "key_fallback": True,
            "ssh_key_path": private_path,
        }
        attempts = []
        fallback = _SSH()

        def password_connect(ip, port, username, password, timeout=12, expected_host_key=""):
            attempts.append(("password", port, username))
            raise bot.paramiko.AuthenticationException("password unavailable")

        def key_connect(ip, port, username, key_path, timeout=12, expected_host_key=""):
            attempts.append(("key", port, username))
            return fallback

        with patch.object(
            bot, "_connect_with_credentials", side_effect=password_connect
        ), patch.object(bot, "_connect_with_key", side_effect=key_connect), patch.object(
            bot, "detect_remote_os_sync", return_value="linux"
        ):
            ssh, remote_os, port, username = bot.connect_target_sync(data)

        self.assertIs(ssh, fallback)
        self.assertEqual((remote_os, port, username), ("linux", 443, "root"))
        self.assertEqual(attempts[0][0], "password")
        self.assertEqual(attempts[-1][0], "key")


if __name__ == "__main__":
    unittest.main(verbosity=2)
