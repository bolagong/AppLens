#!/usr/bin/env python3
"""List user apps or pull only an explicitly confirmed installed package over ADB."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from model_tools import utc_now, write_json


def adb(serial: str, *arguments: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["adb", "-s", serial, *arguments],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def require_adb() -> None:
    if not shutil.which("adb"):
        raise RuntimeError("adb is not available. Install Android platform-tools first.")


def require_device(serial: str) -> None:
    result = adb(serial, "get-state")
    if result.returncode != 0 or result.stdout.strip() != "device":
        raise RuntimeError(f"ADB device {serial!r} is not authorized and ready.")


def list_packages(serial: str) -> list[str]:
    result = adb(serial, "shell", "pm", "list", "packages", "-3")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Unable to list installed user packages.")
    return sorted(line.removeprefix("package:").strip() for line in result.stdout.splitlines() if line.startswith("package:"))


def pull_package(serial: str, package: str, output_dir: Path) -> dict[str, Any]:
    result = adb(serial, "shell", "pm", "path", package)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"Cannot read paths for {package}.")
    remote_paths = [line.removeprefix("package:").strip() for line in result.stdout.splitlines() if line.startswith("package:")]
    if not remote_paths:
        raise RuntimeError(f"No APK paths returned for {package}.")

    package_dir = output_dir / "acquired-apk" / package
    package_dir.mkdir(parents=True, exist_ok=True)
    pulled = []
    for index, remote_path in enumerate(remote_paths):
        filename = Path(remote_path).name or f"split-{index}.apk"
        local_path = package_dir / filename
        pull = adb(serial, "pull", remote_path, str(local_path), timeout=180)
        if pull.returncode != 0 or not local_path.is_file():
            raise RuntimeError(pull.stderr.strip() or f"Failed to pull {remote_path}.")
        pulled.append({"remote_path": remote_path, "local_path": str(local_path), "size_bytes": local_path.stat().st_size})
    manifest = {
        "schema_version": "1.0",
        "acquired_at": utc_now(),
        "serial": serial,
        "package": package,
        "files": pulled,
        "scope": "User explicitly selected this package. No application was launched or interacted with.",
    }
    manifest_path = package_dir / "acquisition.json"
    write_json(manifest_path, manifest)
    return {"manifest": str(manifest_path), "files": pulled}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    list_parser = subparsers.add_parser("list", help="List third-party package names on an authorized device")
    list_parser.add_argument("--serial", required=True)
    pull_parser = subparsers.add_parser("pull", help="Pull only one user-confirmed package and its split APKs")
    pull_parser.add_argument("--serial", required=True)
    pull_parser.add_argument("--package", required=True)
    pull_parser.add_argument("--confirm-package", required=True, help="Repeat --package to prove explicit selection")
    pull_parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()

    try:
        require_adb()
        require_device(arguments.serial)
        if arguments.command == "list":
            print(json.dumps({"serial": arguments.serial, "packages": list_packages(arguments.serial)}, ensure_ascii=False, indent=2))
            return 0
        if arguments.package != arguments.confirm_package:
            raise RuntimeError("--confirm-package must exactly match --package.")
        result = pull_package(arguments.serial, arguments.package, arguments.output.expanduser().resolve())
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"ADB acquisition failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
