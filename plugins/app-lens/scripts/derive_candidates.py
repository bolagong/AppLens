#!/usr/bin/env python3
"""Derive reviewable product-function candidates from safe static evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from evidence_signals import PRODUCT_SIGNAL_SPECS
from model_tools import append_audit, display_feature_name, load_json, load_model, new_function, write_json


PERMISSION_SIGNALS = {
    "android.permission.CAMERA": ("Camera capture", "Manifest declares CAMERA permission"),
    "android.permission.ACCESS_FINE_LOCATION": ("Location-aware experience", "Manifest declares fine location permission"),
    "android.permission.ACCESS_COARSE_LOCATION": ("Location-aware experience", "Manifest declares coarse location permission"),
    "android.permission.POST_NOTIFICATIONS": ("Notification preferences", "Manifest declares notification permission"),
}


def android_permission_signals(evidence: dict[str, Any]) -> list[str]:
    android = evidence.get("android_tool_evidence", {})
    if not isinstance(android, dict):
        return []
    summary = android.get("permission_summary", {})
    if not isinstance(summary, dict):
        return []
    values = summary.get("generic_signals", [])
    return [value for value in values if isinstance(value, str)]


def resource_signal_evidence(evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    archive = evidence.get("archive", {})
    items = archive.get("resource_signal_summary", []) if isinstance(archive, dict) else []
    return {
        item["signal"]: item
        for item in items
        if isinstance(item, dict)
        and isinstance(item.get("signal"), str)
        and isinstance(item.get("matching_resource_count"), int)
        and item["matching_resource_count"] > 0
    }


def manifest_permissions(evidence: dict[str, Any]) -> list[str]:
    metadata = evidence.get("manifest_metadata", {})
    if not isinstance(metadata, dict) or metadata.get("status") != "parsed":
        return []
    values = metadata.get("permissions", [])
    return [value for value in values if isinstance(value, str)]


def evidence_quality(candidate_count: int) -> dict[str, Any]:
    limitations: list[str] = []
    if candidate_count < 2:
        limitations.append("The required static toolchain completed, but it produced fewer than two independent feature hypotheses.")
    return {
        "status": "requires_product_review" if limitations else "reviewable",
        "static_candidate_count": candidate_count,
        "limitations": limitations,
    }


def reverse_signals(evidence: dict[str, Any]) -> list[str]:
    ui_structure = evidence.get("ui_structure", {})
    signals = ui_structure.get("product_signals", []) if isinstance(ui_structure, dict) else []
    return [
        signal.get("name")
        for signal in signals
        if isinstance(signal, dict) and isinstance(signal.get("name"), str)
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="Analysis output directory")
    parser.add_argument("--replace", action="store_true", help="Replace unconfirmed generated candidates")
    arguments = parser.parse_args()
    output_dir = arguments.output.expanduser().resolve()
    evidence_path = output_dir / "evidence" / "static-inventory.json"
    reverse_evidence_path = output_dir / "evidence" / "reverse-static.json"

    try:
        model = load_model(output_dir)
        evidence = load_json(evidence_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Unable to read model or static evidence: {error}", file=sys.stderr)
        return 2
    if not isinstance(evidence, dict):
        print("Static evidence must be an object.", file=sys.stderr)
        return 2

    candidates: dict[str, str] = {}
    resource_signals = resource_signal_evidence(evidence)
    for signal, summary in resource_signals.items():
        spec = PRODUCT_SIGNAL_SPECS.get(signal)
        if not spec:
            continue
        resource_types = ", ".join(summary.get("resource_types", [])) or "resource"
        candidates[display_feature_name(spec["name"])] = (
            f"{summary['matching_resource_count']} resource name(s) across {resource_types} matched a narrow {signal!r} product term"
        )

    for name in android_permission_signals(evidence):
        candidates[display_feature_name(name)] = "Android metadata reported a generic permission capability signal"

    manifest_permission_names = {permission.lower() for permission in manifest_permissions(evidence)}
    for permission, (name, reason) in PERMISSION_SIGNALS.items():
        if permission.lower() in manifest_permission_names:
            candidates[name] = reason

    reverse_evidence: dict[str, Any] | None = None
    if reverse_evidence_path.is_file():
        try:
            payload = load_json(reverse_evidence_path)
            if isinstance(payload, dict) and payload.get("status") == "completed":
                reverse_evidence = payload
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    if reverse_evidence is None:
        print("Full AppLens analysis requires completed reverse-static evidence; rerun reverse_static_inventory.py.", file=sys.stderr)
        return 2
    reverse_signal_names = reverse_signals(reverse_evidence)
    for name in reverse_signal_names:
        candidates.setdefault(display_feature_name(name), "Restricted reverse-static UI structure signal")

    localized_existing = []
    for item in model.get("functions", []):
        if isinstance(item, dict) and item.get("generated_candidate") is True:
            original = item.get("name")
            localized = display_feature_name(original)
            if isinstance(original, str) and localized != original:
                item["name"] = localized
                localized_existing.append({"from": original, "to": localized})

    existing = {item.get("name") for item in model.get("functions", []) if isinstance(item, dict)}
    if arguments.replace:
        model["functions"] = [
            item
            for item in model.get("functions", [])
            if not (isinstance(item, dict) and item.get("generated_candidate") is True)
        ]
        existing = {item.get("name") for item in model["functions"] if isinstance(item, dict)}

    created = []
    for name, reason in sorted(candidates.items()):
        if name in existing:
            continue
        candidate = new_function(name, "static_inference")
        candidate["competitor_evidence"] = [{"type": "static_inventory", "path": "evidence/static-inventory.json", "note": reason}]
        if reverse_evidence and name in reverse_signals(reverse_evidence):
            candidate["competitor_evidence"].append({"type": "reverse_static_inventory", "path": "evidence/reverse-static.json", "note": "Restricted UI structure signal"})
        candidate["generated_candidate"] = True
        model["functions"].append(candidate)
        created.append(name)

    summary = evidence_quality(len(candidates))
    observations = model.setdefault("observations", {})
    observations["static_evidence_quality"] = summary
    append_audit(
        model,
        "static_candidates_derived",
        {
            "created": created,
            "localized_existing": localized_existing,
            "sources": ["evidence/static-inventory.json", "evidence/reverse-static.json"] if reverse_evidence else ["evidence/static-inventory.json"],
            "quality": summary,
        },
    )
    write_json(output_dir / "project-model.json", model)
    print(json.dumps({"created": created, "count": len(created)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
