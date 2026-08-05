"""Regression tests for the default AppLens run brief."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
CONFIGURE_RUN = SCRIPTS / "configure_run.py"


class ConfigureRunTests(unittest.TestCase):
    def test_defaults_to_static_evidence_delivery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            apk_path = workspace / "sample.apk"
            output_dir = workspace / "output"
            apk_path.write_bytes(b"APK fixture")

            result = subprocess.run(
                [
                    sys.executable,
                    str(CONFIGURE_RUN),
                    "--apk",
                    str(apk_path),
                    "--output",
                    str(output_dir),
                    "--workspace",
                    str(workspace),
                    "--confirm-user-authorized-apk",
                ],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            brief = json.loads((output_dir / "evidence" / "run-brief.json").read_text(encoding="utf-8"))
            self.assertEqual(brief["plan"]["exploration"], "static_only")
            self.assertEqual(brief["plan"]["delivery"], "evidence")
            summary = (output_dir / "docs" / "EVIDENCE_SUMMARY.md").read_text(encoding="utf-8")
            self.assertIn("AppLens 证据摘要", summary)


if __name__ == "__main__":
    unittest.main()
