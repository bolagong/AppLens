"""Regression tests for strict AppLens toolchain gating."""

from __future__ import annotations

import sys
import json
import tempfile
import unittest
import xml.etree.ElementTree as element_tree
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from analysis_toolchain import missing_required_tools, require_full_toolchain, resolve_required_tools  # noqa: E402
import provision_analysis_tools  # noqa: E402
from provision_analysis_tools import select_aapt2_version, select_jadx_asset, select_jre_package  # noqa: E402


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

    def test_prefers_a_stable_aapt2_version_over_newer_prereleases(self) -> None:
        metadata = element_tree.fromstring(
            """
            <metadata><versioning><release>9.0.0-alpha01</release><versions>
              <version>8.6.1-11315950</version><version>9.0.0-alpha01</version>
            </versions></versioning></metadata>
            """
        )

        self.assertEqual(select_aapt2_version(metadata), "8.6.1-11315950")

    def test_provisioner_records_downloaded_tool_paths_for_the_followup_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            aapt = output / "tools" / "aapt2"
            jadx = output / "tools" / "jadx"
            aapt.parent.mkdir(parents=True)
            aapt.touch()
            jadx.touch()
            initial_tools = {"aapt": None, "jadx": None}

            with (
                patch.object(sys, "argv", ["provision_analysis_tools.py", "--output", str(output), "--approve-download"]),
                patch.object(provision_analysis_tools, "host_platform", return_value=("osx", "mac", "aarch64")),
                patch.object(provision_analysis_tools, "resolve_required_tools", return_value=initial_tools),
                patch.object(provision_analysis_tools, "latest_aapt2", return_value=(aapt, {"version": "test"})),
                patch.object(provision_analysis_tools, "latest_jadx", return_value=(jadx, {"version": "test"})),
                patch.object(provision_analysis_tools, "system_java_home", return_value="/existing/java"),
            ):
                self.assertEqual(provision_analysis_tools.main(), 0)

            receipt = json.loads((output / "evidence" / "toolchain.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["tools"], {"aapt": str(aapt), "jadx": str(jadx)})
            self.assertEqual(require_full_toolchain(output), {"aapt": str(aapt), "jadx": str(jadx)})


if __name__ == "__main__":
    unittest.main()
