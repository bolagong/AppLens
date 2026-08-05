#!/usr/bin/env python3
"""Run optional Flutter checks without installing dependencies or changing user settings."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from model_tools import utc_now, write_json


def execute(command: list[str], directory: Path) -> dict[str, Any]:
    result = subprocess.run(command, cwd=directory, check=False, capture_output=True, text=True, timeout=180)
    return {"command": command, "exit_code": result.returncode, "stdout": result.stdout[-12000:], "stderr": result.stderr[-4000:]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run", action="store_true", help="Run flutter pub get, analyze, and test")
    arguments = parser.parse_args()
    output_dir = arguments.output.expanduser().resolve()
    prototype_dir = output_dir / "flutter_prototype"
    if not (prototype_dir / "pubspec.yaml").is_file():
        print("Flutter prototype is missing. Run generate_flutter.py first.", file=sys.stderr)
        return 2
    flutter = shutil.which("flutter")
    report: dict[str, Any] = {"created_at": utc_now(), "flutter_available": bool(flutter), "ran": arguments.run, "checks": []}
    if arguments.run:
        if not flutter:
            print("flutter is not available; no checks were run.", file=sys.stderr)
            return 2
        for command in ([flutter, "pub", "get"], [flutter, "analyze"], [flutter, "test"]):
            result = execute(command, prototype_dir)
            report["checks"].append(result)
            if result["exit_code"] != 0:
                write_json(prototype_dir / "verification.json", report)
                print(json.dumps(report, ensure_ascii=False, indent=2), file=sys.stderr)
                return 2
    write_json(prototype_dir / "verification.json", report)
    print(prototype_dir / "verification.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
