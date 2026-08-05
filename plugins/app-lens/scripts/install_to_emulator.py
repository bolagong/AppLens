#!/usr/bin/env python3
"""Install user-provided APK files only on a confirmed isolated Android emulator."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
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


def xapk_apks(xapk: Path, temporary: Path) -> list[Path]:
    with zipfile.ZipFile(xapk) as archive:
        members = [member for member in archive.namelist() if member.lower().endswith(".apk")]
        if not members:
            raise ValueError("XAPK contains no APK members.")
        members.sort(key=lambda member: (Path(member).name.lower() != "base.apk", member))
        paths = []
        for index, member in enumerate(members):
            path = temporary / f"{index:03d}-{Path(member).name}"
            with archive.open(member) as source, path.open("wb") as target:
                shutil.copyfileobj(source, target)
            paths.append(path)
        return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--apk", type=Path, action="append", default=[], help="APK path; repeat for a split APK set")
    parser.add_argument("--xapk", type=Path, help="XAPK path to install as a base and split APK set")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--confirm-isolated-emulator", action="store_true")
    arguments = parser.parse_args()
    if not arguments.confirm_isolated_emulator:
        parser.error("--confirm-isolated-emulator is required.")
    if bool(arguments.apk) == bool(arguments.xapk):
        parser.error("Provide either one or more --apk values, or one --xapk value.")
    output_dir = arguments.output.expanduser().resolve()
    try:
        require_emulator(arguments.serial)
        with tempfile.TemporaryDirectory(prefix="apk-install-") as temporary:
            paths = xapk_apks(arguments.xapk.expanduser().resolve(), Path(temporary)) if arguments.xapk else [path.expanduser().resolve() for path in arguments.apk]
            if not all(path.is_file() and path.suffix.lower() == ".apk" for path in paths):
                raise ValueError("Every --apk value must be an existing .apk file.")
            install_args = ["install", "-r", str(paths[0])] if len(paths) == 1 else ["install-multiple", "-r", *(str(path) for path in paths)]
            result = adb(arguments.serial, *install_args)
            if result.returncode != 0 or "Success" not in result.stdout:
                raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "APK installation failed.")
            payload = {"created_at": utc_now(), "serial": arguments.serial, "installed_files": [path.name for path in paths], "result": result.stdout.strip(), "isolated_emulator_confirmed": True}
            evidence_path = output_dir / "evidence" / "dynamic" / "installation.json"
            write_json(evidence_path, payload)
            print(evidence_path)
            return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired, zipfile.BadZipFile) as error:
        print(f"Emulator installation failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
