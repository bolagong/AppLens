#!/usr/bin/env python3
"""Record an explicit product-owner confirmation before final PRD generation."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from model_tools import approval_fingerprint, append_audit, load_model, utc_now, validation_errors, write_json


VERSION_PATTERN = re.compile(r"^v?\d+(?:\.\d+){0,2}(?:[-+][A-Za-z0-9.-]+)?$")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--version", required=True, help="Confirmed model version, for example v1.0")
    parser.add_argument("--note", default="Confirmed by product owner through Codex.")
    arguments = parser.parse_args()
    if not VERSION_PATTERN.fullmatch(arguments.version):
        parser.error("--version must look like v1.0, 1.0.0, or v1.0-beta.")
    output_dir = arguments.output.expanduser().resolve()
    try:
        model = load_model(output_dir)
        errors = validation_errors(model)
        if errors:
            raise ValueError("; ".join(errors))
        model["project"]["version"] = arguments.version
        model["project"]["status"] = "confirmed"
        generation = model.setdefault("generation", {})
        generation["approved_model_version"] = arguments.version
        generation["approved_at"] = utc_now()
        generation["approved_model_fingerprint"] = approval_fingerprint(model)
        generation["prd_status"] = "ready_to_generate"
        append_audit(model, "model_confirmed", {"version": arguments.version, "note": arguments.note, "source": "codex_command"})
        write_json(output_dir / "project-model.json", model)
    except (OSError, ValueError) as error:
        print(f"Could not confirm model: {error}", file=sys.stderr)
        return 2
    print(output_dir / "project-model.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
