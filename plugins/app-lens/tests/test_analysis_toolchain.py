"""Regression tests for strict AppLens toolchain gating."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from analysis_toolchain import missing_required_tools, resolve_required_tools  # noqa: E402
from provision_analysis_tools import select_jadx_asset, select_jre_package  # noqa: E402


class AnalysisToolchainTests(unittest.TestCase):
    def test_uses_aapt2_when_aapt_is_not_available(self) -> None:
        tools = resolve_required_tools(
            environment={},
            find_command=lambda name: {"aapt2": "/tools/aapt2", "jadx": "/tools/jadx"}.get(name),
        )

        self.assertEqual(tools, {"aapt": "/tools/aapt2", "jadx": "/tools/jadx"})
        self.assertEqual(missing_required_tools(tools), [])

    def test_reports_both_missing_tools(self) -> None:
        tools = resolve_required_tools(environment={}, find_command=lambda _name: None)

        self.assertEqual(missing_required_tools(tools), ["aapt or aapt2", "jadx"])

    def test_uses_explicit_vetted_tool_paths(self) -> None:
        tools = resolve_required_tools(
            environment={"APPLENS_AAPT": "/plugin-tools/aapt2", "APPLENS_JADX": "/plugin-tools/jadx"},
            find_command=lambda _name: None,
        )

        self.assertEqual(tools, {"aapt": "/plugin-tools/aapt2", "jadx": "/plugin-tools/jadx"})

    def test_accepts_checksum_verified_upstream_download_metadata(self) -> None:
        jadx = select_jadx_asset(
            {
                "assets": [
                    {"name": "jadx-gui-1.5.5-win.zip", "digest": "sha256:" + "0" * 64},
                    {"name": "jadx-1.5.5.zip", "digest": "sha256:" + "a" * 64, "browser_download_url": "https://example.test/jadx.zip"},
                ]
            }
        )
        jre = select_jre_package(
            [
                {
                    "binaries": [
                        {
                            "package": {
                                "name": "OpenJDK21U-jre_aarch64_mac_hotspot.tar.gz",
                                "link": "https://example.test/jre.tar.gz",
                                "checksum": "b" * 64,
                            }
                        }
                    ]
                }
            ]
        )

        self.assertEqual(jadx["name"], "jadx-1.5.5.zip")
        self.assertEqual(jre["name"], "OpenJDK21U-jre_aarch64_mac_hotspot.tar.gz")


if __name__ == "__main__":
    unittest.main()
