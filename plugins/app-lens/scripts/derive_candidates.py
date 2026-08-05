#!/usr/bin/env python3
"""Derive reviewable product-function candidates from safe static evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from model_tools import append_audit, load_json, load_model, new_function, write_json


SIGNALS = {
    "camera": ("Camera capture", "Declared camera capability or camera-related resource"),
    "search": ("Search", "Search-related resource name"),
    "favorite": ("Save or favorite", "Favorite-related resource name"),
    "bookmark": ("Save or bookmark", "Bookmark-related resource name"),
    "filter": ("Filter or sort", "Filter-related resource name"),
    "location": ("Location-aware experience", "Location-related resource name"),
    "map": ("Map browsing", "Map-related resource name"),
    "share": ("External sharing", "Share-related resource name; do not execute dynamically"),
    "notification": ("Notification preferences", "Notification-related resource name"),
    "profile": ("Profile or account area", "Profile-related resource name"),
    "setting": ("Settings", "Settings-related resource name"),
}
PERMISSION_SIGNALS = {
    "android.permission.CAMERA": ("Camera capture", "Manifest declares CAMERA permission"),
    "android.permission.ACCESS_FINE_LOCATION": ("Location-aware experience", "Manifest declares fine location permission"),
    "android.permission.ACCESS_COARSE_LOCATION": ("Location-aware experience", "Manifest declares coarse location permission"),
    "android.permission.POST_NOTIFICATIONS": ("Notification preferences", "Manifest declares notification permission"),
}


def evidence_strings(evidence: dict[str, Any]) -> list[str]:
    archive = evidence.get("archive", {})
    strings = list(archive.get("sample_resource_paths", []))
    results = evidence.get("android_tool_evidence", {}).get("results", {})
    for result in results.values():
        if isinstance(result, dict):
            strings.append(result.get("stdout", ""))
    return [value.lower() for value in strings if isinstance(value, str)]


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
    haystack = "\n".join(evidence_strings(evidence))
    for keyword, (name, reason) in SIGNALS.items():
        if keyword in haystack:
            candidates[name] = reason
    permission_output = haystack
    for permission, (name, reason) in PERMISSION_SIGNALS.items():
        if permission.lower() in permission_output:
            candidates[name] = reason

    reverse_evidence: dict[str, Any] | None = None
    if reverse_evidence_path.is_file():
        try:
            payload = load_json(reverse_evidence_path)
            if isinstance(payload, dict) and payload.get("status") == "completed":
                reverse_evidence = payload
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    if reverse_evidence:
        for name in reverse_signals(reverse_evidence):
            candidates.setdefault(name, "Restricted reverse-static UI structure signal")

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

    append_audit(model, "static_candidates_derived", {"created": created, "sources": ["evidence/static-inventory.json", "evidence/reverse-static.json"] if reverse_evidence else ["evidence/static-inventory.json"]})
    write_json(output_dir / "project-model.json", model)
    print(json.dumps({"created": created, "count": len(created)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
