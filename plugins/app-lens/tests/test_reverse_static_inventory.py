"""Regression tests for isolated JADX execution."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import reverse_static_inventory  # noqa: E402


class ReverseStaticInventoryTests(unittest.TestCase):
    def test_jadx_uses_an_output_local_user_home(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            apk = workspace / "sample.apk"
            output = workspace / "output directory"
            apk.write_bytes(b"APK fixture")
            captured: dict[str, object] = {}

            class CompletedProcess:
                returncode = 0

                def poll(self) -> int:
                    return 0

            def fake_popen(arguments: list[str], **kwargs: object) -> CompletedProcess:
                captured["arguments"] = arguments
                captured["environment"] = kwargs["env"]
                return CompletedProcess()

            with (
                patch.object(sys, "argv", ["reverse_static_inventory.py", str(apk), "--output", str(output)]),
                patch.object(reverse_static_inventory, "require_jadx", return_value="/tools/jadx"),
                patch.object(reverse_static_inventory, "java_environment", return_value={}),
                patch.object(reverse_static_inventory.subprocess, "Popen", side_effect=fake_popen),
                patch.object(reverse_static_inventory, "source_paths", return_value=[output / "HomeActivity.java"]),
                patch.dict(reverse_static_inventory.os.environ, {"JADX_OPTS": "-Xmx1g"}, clear=True),
            ):
                self.assertEqual(reverse_static_inventory.main(), 0)

            environment = captured["environment"]
            self.assertIsInstance(environment, dict)
            options = shlex.split(environment["JADX_OPTS"])
            self.assertEqual(options, ["-Xmx1g", f"-Duser.home={output.resolve() / '.applens' / 'jadx-home'}"])
            self.assertEqual(
                captured["arguments"],
                [
                    str(reverse_static_inventory.UPSTREAM_WRAPPER),
                    "--engine",
                    "jadx",
                    "--no-res",
                    "--threads",
                    "4",
                    "--output",
                    str(output.resolve() / ".applens" / "work" / "reverse-decompiled" / reverse_static_inventory.sha256(apk)),
                    str(apk.resolve()),
                ],
            )
            evidence = json.loads((output / "evidence" / "reverse-static.json").read_text(encoding="utf-8"))
            self.assertEqual(evidence["status"], "completed")

    def test_timeout_writes_safe_failure_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            apk = workspace / "sample.apk"
            output = workspace / "output"
            apk.write_bytes(b"APK fixture")

            with (
                patch.object(
                    sys,
                    "argv",
                    [
                        "reverse_static_inventory.py",
                        str(apk),
                        "--output",
                        str(output),
                        "--timeout-seconds",
                        "90",
                    ],
                ),
                patch.object(reverse_static_inventory, "require_jadx", return_value="/tools/jadx"),
                patch.object(reverse_static_inventory, "java_environment", return_value={}),
                patch.object(reverse_static_inventory.subprocess, "Popen", return_value=_RunningProcess()),
                patch.object(reverse_static_inventory.time, "monotonic", side_effect=[0.0, 91.0]),
            ):
                self.assertEqual(reverse_static_inventory.main(), 2)

            evidence = json.loads((output / "evidence" / "reverse-static.json").read_text(encoding="utf-8"))
            self.assertEqual(evidence["status"], "failed")
            self.assertEqual(evidence["failure"], {"reason": "timeout", "timeout_seconds": 90})
            self.assertNotIn("stderr", evidence)
            progress = json.loads((output / "evidence" / "reverse-progress.json").read_text(encoding="utf-8"))
            self.assertEqual(progress["status"], "failed")
            self.assertEqual(progress["threads"], 4)


class _RunningProcess:
    returncode: int | None = None

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.returncode = -15

    def kill(self) -> None:
        self.returncode = -9

    def wait(self, timeout: int | None = None) -> int:
        return self.returncode or 0


if __name__ == "__main__":
    unittest.main()
