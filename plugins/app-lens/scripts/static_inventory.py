#!/usr/bin/env python3
"""Create a conservative local inventory for a user-provided APK."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command_output(command: list[str]) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"command": command, "available": False, "error": str(error)}

    return {
        "command": command,
        "available": True,
        "exit_code": result.returncode,
        "stdout": result.stdout[:20000],
        "stderr": result.stderr[:4000],
    }


def inventory_zip(apk_path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(apk_path) as archive:
        names = archive.namelist()
        file_names = [name for name in names if not name.endswith("/")]
        suffixes = Counter(Path(name).suffix.lower() or "[none]" for name in file_names)
        resource_prefixes = Counter(name.split("/", 1)[0] for name in file_names)
        native_libraries = sorted(name for name in file_names if name.startswith("lib/"))
        dex_files = sorted(name for name in file_names if name.endswith(".dex"))

    architectures = sorted(
        {
            parts[1]
            for name in native_libraries
            if len(parts := name.split("/")) >= 3 and parts[0] == "lib"
        }
    )
    return {
        "archive_file_count": len(file_names),
        "top_level_paths": dict(sorted(resource_prefixes.items())),
        "file_extensions": dict(sorted(suffixes.items())),
        "dex_files": dex_files,
        "native_abis": architectures,
        "native_library_count": len(native_libraries),
        "sample_resource_paths": sorted(
            name for name in file_names if name.startswith(("res/", "assets/"))
        )[:200],
    }


def android_tool_evidence(apk_path: Path) -> dict[str, Any]:
    aapt = shutil.which("aapt") or shutil.which("aapt2")
    if not aapt:
        return {
            "tool_available": False,
            "note": "Install Android SDK build tools to collect package and permission metadata.",
        }

    tool_name = Path(aapt).name
    if tool_name == "aapt2":
        commands = {
            "badging": [aapt, "dump", "badging", str(apk_path)],
            "permissions": [aapt, "dump", "permissions", str(apk_path)],
        }
    else:
        commands = {
            "badging": [aapt, "dump", "badging", str(apk_path)],
            "permissions": [aapt, "dump", "permissions", str(apk_path)],
        }

    return {
        "tool_available": True,
        "tool": aapt,
        "results": {name: command_output(command) for name, command in commands.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Path to a user-provided .apk file")
    parser.add_argument("--output", required=True, type=Path, help="Analysis output directory")
    arguments = parser.parse_args()

    input_path = arguments.input.expanduser().resolve()
    output_dir = arguments.output.expanduser().resolve()
    if not input_path.is_file():
        parser.error(f"Input file does not exist: {input_path}")
    if input_path.suffix.lower() != ".apk":
        parser.error("Input must have a .apk extension.")

    output_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir = output_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    try:
        report = {
            "schema_version": "1.0",
            "source": {
                "input_filename": input_path.name,
                "input_type": "apk",
                "input_sha256": sha256(input_path),
                "selected_apk_filename": input_path.name,
                "selected_apk_sha256": sha256(input_path),
            },
            "scope": {
                "purpose": "local static evidence inventory",
                "excluded": [
                    "API endpoints",
                    "credentials and tokens",
                    "backend implementation",
                    "decompiled source code",
                ],
            },
            "archive": inventory_zip(input_path),
            "android_tool_evidence": android_tool_evidence(input_path),
        }
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f"Inventory failed: {error}", file=sys.stderr)
        return 2

    report_path = evidence_dir / "static-inventory.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
