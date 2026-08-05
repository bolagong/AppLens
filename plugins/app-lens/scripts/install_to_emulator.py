#!/usr/bin/env python3
"""Install user-provided APK files only on a confirmed isolated Android emulator."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from model_tools import utc_now, write_json


def adb(serial: str, *arguments: str, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["adb", "-s", serial, *arguments], check=False, capture_output=True, text=True, timeout=timeout)


def require_emulator(serial: str) -> None:
    if not shutil.which("adb"):
        raise RuntimeError("adb is not available.")
    state = adb(serial, "get-state", timeout=30)
    qemu = adb(serial, "shell", "getprop", "ro.kernel.qemu", timeout=30)
    if state.returncode != 0 or state.stdout.strip() != "device":
        raise RuntimeError(f"ADB target {serial!r} is not ready.")
    if not serial.startswith("emulator-") and qemu.stdout.strip() != "1":
        raise RuntimeError("Refusing to install onto a non-emulator ADB target.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--apk", required=True, type=Path, help="Path to the user-provided APK")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--confirm-isolated-emulator", action="store_true")
    arguments = parser.parse_args()
    if not arguments.confirm_isolated_emulator:
        parser.error("--confirm-isolated-emulator is required.")
    output_dir = arguments.output.expanduser().resolve()
    try:
        require_emulator(arguments.serial)
        apk_path = arguments.apk.expanduser().resolve()
        if not apk_path.is_file() or apk_path.suffix.lower() != ".apk":
            raise ValueError("--apk must be an existing .apk file.")
        result = adb(arguments.serial, "install", "-r", str(apk_path))
        if result.returncode != 0 or "Success" not in result.stdout:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "APK installation failed.")
        payload = {"created_at": utc_now(), "serial": arguments.serial, "installed_files": [apk_path.name], "result": result.stdout.strip(), "isolated_emulator_confirmed": True}
        evidence_path = output_dir / "evidence" / "dynamic" / "installation.json"
        write_json(evidence_path, payload)
        print(evidence_path)
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"Emulator installation failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
