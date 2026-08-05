#!/usr/bin/env python3
"""Record one explicit, reusable run brief before AppLens analysis begins."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from model_tools import utc_now, write_json


def contained_by(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", required=True, type=Path, help="Path to the user-provided APK")
    parser.add_argument("--output", required=True, type=Path, help="Project-local analysis output directory")
    parser.add_argument("--workspace", type=Path, default=Path.cwd(), help="Workspace that must contain --output (defaults to the current directory)")
    parser.add_argument("--confirm-user-authorized-apk", action="store_true", help="Record the user's explicit authorization to inspect this APK")
    parser.add_argument("--exploration", choices=("static_only", "dynamic"), default="static_only")
    parser.add_argument("--confirm-isolated-emulator", action="store_true", help="Required only for resettable-emulator exploration")
    parser.add_argument("--allow-static-fallback", action="store_true", help="Continue with static evidence if dynamic exploration cannot run")
    parser.add_argument("--delivery", choices=("evidence", "model", "draft_prototype"), default="model")
    arguments = parser.parse_args()

    apk_path = arguments.apk.expanduser().resolve()
    output_dir = arguments.output.expanduser().resolve()
    workspace = arguments.workspace.expanduser().resolve()
    if not apk_path.is_file() or apk_path.suffix.lower() != ".apk":
        parser.error("--apk must be an existing .apk file.")
    if not arguments.confirm_user_authorized_apk:
        parser.error("--confirm-user-authorized-apk is required.")
    if not workspace.is_dir():
        parser.error("--workspace must be an existing directory.")
    if not contained_by(output_dir, workspace):
        parser.error("--output must be inside --workspace.")
    if arguments.exploration == "dynamic" and not arguments.confirm_isolated_emulator:
        parser.error("--confirm-isolated-emulator is required for dynamic exploration.")
    if arguments.exploration == "static_only" and arguments.confirm_isolated_emulator:
        parser.error("--confirm-isolated-emulator may be used only with --exploration dynamic.")
    if arguments.exploration == "static_only" and arguments.allow_static_fallback:
        parser.error("--allow-static-fallback applies only to dynamic exploration.")

    brief = {
        "schema_version": "1.0",
        "created_at": utc_now(),
        "input": {"filename": apk_path.name, "type": "apk"},
        "authorization": {
            "user_authorized_apk_inspection": True,
            "isolated_emulator_confirmed": arguments.exploration == "dynamic",
        },
        "plan": {
            "exploration": arguments.exploration,
            "allow_static_fallback": bool(arguments.allow_static_fallback),
            "delivery": arguments.delivery,
            "final_prd_requires_model_confirmation": True,
        },
        "scope": {
            "dynamic_paths": "non-authenticated, non-destructive paths only",
            "excluded": ["real devices", "accounts", "payments", "external side effects"],
        },
    }
    brief_path = output_dir / "evidence" / "run-brief.json"
    try:
        write_json(brief_path, brief)
    except OSError as error:
        print(f"Could not write run brief: {error}", file=sys.stderr)
        return 2
    print(brief_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
