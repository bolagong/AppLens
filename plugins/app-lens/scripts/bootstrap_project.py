#!/usr/bin/env python3
"""Create the editable product-model source of truth from static evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from model_tools import output_layout, utc_now, write_json


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as source:
        payload = json.load(source)
    if not isinstance(payload, dict):
        raise ValueError("Evidence JSON must be an object.")
    return payload


def load_run_brief(output_dir: Path) -> dict[str, Any] | None:
    """Load the optional, user-confirmed run plan without making it mandatory."""
    brief_path = output_dir / "evidence" / "run-brief.json"
    if not brief_path.is_file():
        return None
    brief = load_json(brief_path)
    if brief.get("schema_version") != "1.0":
        raise ValueError("run-brief.json has an unsupported schema version.")
    return brief


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", required=True, type=Path, help="static-inventory.json path")
    parser.add_argument("--output", required=True, type=Path, help="analysis output directory")
    arguments = parser.parse_args()

    evidence_path = arguments.evidence.expanduser().resolve()
    output_dir = arguments.output.expanduser().resolve()
    model_path = output_dir / "project-model.json"

    if model_path.exists():
        print(f"Refusing to overwrite existing model: {model_path}", file=sys.stderr)
        return 2

    try:
        evidence = load_json(evidence_path)
        run_brief = load_run_brief(output_dir)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Cannot read evidence: {error}", file=sys.stderr)
        return 2

    output_layout(output_dir)

    source = evidence.get("source", {})
    reverse_evidence_path = output_dir / "evidence" / "reverse-static.json"
    plan = run_brief.get("plan", {}) if isinstance(run_brief, dict) else {}
    delivery = plan.get("delivery") if isinstance(plan, dict) else None
    model = {
        "schema_version": "1.0",
        "project": {
            "name": "原创产品参考",
            "version": "v0.1",
            "created_at": utc_now(),
            "status": "evidence_review",
            "analysis_scope": "Product and visual reference only; not a competitor reproduction.",
        },
        "observations": {
            "source_input": {
                "input_filename": source.get("input_filename"),
                "input_sha256": source.get("input_sha256"),
                "static_evidence": "evidence/static-inventory.json",
                "reverse_static_evidence": "evidence/reverse-static.json" if reverse_evidence_path.is_file() else None,
                "run_brief": "evidence/run-brief.json" if run_brief else None,
            },
            "screenshots": [],
            "navigation_paths": [],
            "interception_points": [],
        },
        "visual_model": {
            "status": "not_started",
            "reference_notes": [],
            "decisions": {},
        },
        "engagement": {
            "delivery": delivery or "model",
            "exploration": plan.get("exploration", "not_recorded") if isinstance(plan, dict) else "not_recorded",
            "final_prd_requires_model_confirmation": True,
        },
        "functions": [],
        "generation": {
            "approved_model_version": None,
            "approved_at": None,
            "approved_model_fingerprint": None,
            "draft_prototype_requested": delivery == "draft_prototype",
            "flutter_prototype_status": "not_started",
            "prd_status": "blocked_pending_confirmation",
        },
        "audit": [
            {
                "at": utc_now(),
                "event": "model_bootstrapped",
                "details": {
                    "evidence": "evidence/static-inventory.json",
                    "run_brief": "evidence/run-brief.json" if run_brief else None,
                    "requested_delivery": delivery or "model",
                },
            }
        ],
    }
    write_json(model_path, model)
    print(model_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
