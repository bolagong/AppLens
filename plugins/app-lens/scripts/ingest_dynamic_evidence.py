#!/usr/bin/env python3
"""Attach a completed safe-exploration session to the editable product model."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from model_tools import append_audit, load_json, load_model, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    output_dir = arguments.output.expanduser().resolve()
    session_path = output_dir / "evidence" / "dynamic" / "dynamic-session.json"
    try:
        model = load_model(output_dir)
        session = load_json(session_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Cannot read model or dynamic evidence: {error}", file=sys.stderr)
        return 2
    if not isinstance(session, dict):
        print("Dynamic session must be an object.", file=sys.stderr)
        return 2

    observations = model.setdefault("observations", {})
    observations["screenshots"] = session.get("screens", [])
    observations["navigation_paths"] = session.get("navigation_paths", [])
    observations["interception_points"] = session.get("blocked_or_skipped", [])
    append_audit(
        model,
        "dynamic_evidence_ingested",
        {"screens": len(observations["screenshots"]), "paths": len(observations["navigation_paths"]), "source": "evidence/dynamic/dynamic-session.json"},
    )
    write_json(output_dir / "project-model.json", model)
    print(output_dir / "project-model.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
