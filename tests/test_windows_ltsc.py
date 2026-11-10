#!/usr/bin/env python3
"""Regression tests for Windows 11 Enterprise LTSC 2024 image routing."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bot  # noqa: E402


class WindowsLTSCTests(unittest.TestCase):
    def test_menu_option_uses_pinned_dd_token(self):
        option = bot.WINDOWS_OPTIONS["win11ltsc"]
        self.assertEqual(option["name"], "Windows 11 Enterprise LTSC 2024 (24H2)")
        self.assertEqual(option["cmd"], "dd --img __WIN11_LTSC_DD__")

    def test_all_languages_resolve_to_pinned_bios_images(self):
        expected = {
            "en": "https://dl.lamp.sh/vhd/en-us_win11_ltsc.xz",
            "cn": "https://dl.lamp.sh/vhd/zh-cn_win11_ltsc.xz",
            "jp": "https://dl.lamp.sh/vhd/ja-jp_win11_ltsc.xz",
        }
        for language, image_url in expected.items():
            with self.subTest(language=language):
                data = {
                    "vps_port": 443,
                    "os_type": "windows",
                    "os_cmd": bot.WINDOWS_OPTIONS["win11ltsc"]["cmd"],
                    "lang": language,
                }
                arguments = bot._installer_arguments(data)
                self.assertIn(image_url, arguments)
                self.assertNotIn("__WIN11_LTSC_DD__", arguments)
                self.assertIn("443", arguments)
                self.assertIn("3389", arguments)

    def test_final_verification_requires_enterprise_ltsc_edition(self):
        requested = "Windows 11 Enterprise LTSC 2024 (24H2)"
        self.assertTrue(
            bot.windows_os_matches(requested, "Microsoft Windows 11 Enterprise LTSC")
        )
        self.assertFalse(bot.windows_os_matches(requested, "Microsoft Windows 11 Pro"))
        self.assertFalse(
            bot.windows_os_matches(requested, "Microsoft Windows 10 Enterprise LTSC")
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
