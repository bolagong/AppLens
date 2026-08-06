"""Regression tests for human-readable, safe evidence delivery."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import cleanup_working_data  # noqa: E402
from evidence_summary import write_evidence_summary  # noqa: E402
from model_tools import write_json  # noqa: E402


class EvidenceDeliveryTests(unittest.TestCase):
    def test_summary_is_human_readable_and_excludes_raw_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            write_json(
                output / "evidence" / "static-inventory.json",
                {
                    "archive": {
                        "archive_file_count": 12,
                        "dex_file_count": 1,
                        "native_abis": ["arm64-v8a"],
                        "native_library_count": 2,
                        "resource_signal_summary": [{"name": "Search", "matching_resource_count": 1}],
                        "sample_resource_paths": ["assets/proprietary_brand_asset.png"],
                    },
                    "manifest_metadata": {"status": "limited", "permissions": []},
                    "android_tool_evidence": {
                        "permission_summary": {"declared_permission_count": 56, "generic_signals": ["Camera capture"]},
                        "results": {"badging": {"stdout": "proprietary.example"}},
                    },
                },
            )
            write_json(
                output / "evidence" / "reverse-static.json",
                {"status": "failed", "failure": {"reason": "timeout", "timeout_seconds": 3600}},
            )

            summary = write_evidence_summary(output).read_text(encoding="utf-8")

        self.assertIn("部分完成", summary)
        self.assertIn("超过 3600 秒上限", summary)
        self.assertIn("Camera capture", summary)
        self.assertIn("Manifest 声明权限数：未取得", summary)
        self.assertIn("AAPT2 聚合声明权限数：56", summary)
        self.assertNotIn("proprietary", summary)
        self.assertNotIn("sample_resource_paths", summary)

    def test_summary_only_shows_cancel_hint_for_running_progress(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            write_json(output / "evidence" / "reverse-progress.json", {"status": "completed"})
            summary = write_evidence_summary(output).read_text(encoding="utf-8")

        self.assertIn("当前状态：已完成", summary)
        self.assertNotIn("运行中，可使用", summary)

    def test_cleanup_requires_explicit_delete_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            expired = output / ".applens" / "work" / "reverse-decompiled" / "fixture"
            expired.mkdir(parents=True)
            (expired / "source.java").write_text("fixture", encoding="utf-8")
            old = time.time() - 25 * 3600
            os.utime(expired, (old, old))
            os.utime(expired / "source.java", (old, old))

            with patch.object(sys, "argv", ["cleanup_working_data.py", "--output", str(output)]):
                self.assertEqual(cleanup_working_data.main(), 0)
            self.assertTrue(expired.exists())

            with patch.object(
                sys,
                "argv",
                ["cleanup_working_data.py", "--output", str(output), "--confirm-delete"],
            ):
                self.assertEqual(cleanup_working_data.main(), 0)
            self.assertFalse(expired.exists())

    def test_cleanup_lists_legacy_reverse_working_data(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            legacy = output / "evidence" / "reverse-decompiled" / "fixture"
            legacy.mkdir(parents=True)
            (legacy / "source.java").write_text("fixture", encoding="utf-8")
            old = time.time() - 25 * 3600
            os.utime(legacy, (old, old))
            os.utime(legacy / "source.java", (old, old))

            with patch.object(sys, "argv", ["cleanup_working_data.py", "--output", str(output)]):
                self.assertEqual(cleanup_working_data.main(), 0)
            self.assertTrue(legacy.exists())


if __name__ == "__main__":
    unittest.main()
