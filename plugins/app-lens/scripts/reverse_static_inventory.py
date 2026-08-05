#!/usr/bin/env python3
"""Create API-safe UI structure evidence with the vendored reverse-engineering wrapper."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from analysis_toolchain import ToolchainError, java_environment, require_jadx
from model_tools import write_json


UPSTREAM_WRAPPER = (
    Path(__file__).resolve().parent.parent
    / "third_party"
    / "android-reverse-engineering-skill"
    / "decompile.sh"
)
UI_SUFFIXES = {
    "activity": "activity_like",
    "fragment": "fragment_like",
    "viewmodel": "view_model_like",
    "presenter": "presenter_like",
    "screen": "screen_like",
    "adapter": "adapter_like",
}
PRODUCT_SIGNALS = {
    "bookmark": "Save or bookmark",
    "camera": "Camera capture",
    "favorite": "Save or favorite",
    "filter": "Filter or sort",
    "location": "Location-aware experience",
    "map": "Map browsing",
    "notification": "Notification preferences",
    "search": "Search",
    "setting": "Settings",
    "share": "External sharing",
}
EXCLUDED_UI_MARKERS = {
    "auth",
    "billing",
    "login",
    "member",
    "membership",
    "paywall",
    "payment",
    "register",
    "signin",
    "signup",
    "subscribe",
    "subscription",
}


def source_paths(decompiled_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in decompiled_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in {".java", ".kt"}
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def summarize_ui_structure(paths: list[Path]) -> dict[str, Any]:
    counts = {kind: 0 for kind in UI_SUFFIXES.values()}
    counts["source_file_count"] = len(paths)
    signals: set[str] = set()
    excluded = 0

    for path in paths:
        stem = path.stem.lower()
        if any(marker in stem for marker in EXCLUDED_UI_MARKERS):
            excluded += 1
            continue
        for suffix, kind in UI_SUFFIXES.items():
            if stem.endswith(suffix):
                counts[kind] += 1
        for keyword, signal in PRODUCT_SIGNALS.items():
            if keyword in stem:
                signals.add(signal)

    return {
        "component_counts": counts,
        "product_signals": [
            {
                "name": signal,
                "confidence": "static_inference",
                "note": "Inferred from a non-sensitive UI source-file name; requires product review.",
            }
            for signal in sorted(signals)
        ],
        "excluded_interception_candidate_count": excluded,
    }


def evidence_payload(status: str, **details: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "status": status,
        "scope": {
            "purpose": "offline UI structure and product-signal evidence",
            "included": [
                "source-file counts grouped by UI role",
                "generic product signals from non-sensitive UI source-file names",
            ],
            "excluded": [
                "decompiled source code",
                "API endpoints and URLs",
                "credentials, tokens, and authentication material",
                "backend, signing, encryption, and network logic",
                "Frida, traffic capture, bypasses, and native analysis",
            ],
        },
        "tool": {
            "name": "CreditTone/android-reverse-engineering-skill",
            "wrapper": "third_party/android-reverse-engineering-skill/decompile.sh",
            "engine": "jadx",
            "resource_decoding": False,
        },
    }
    payload.update(details)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Path to a user-provided .apk file")
    parser.add_argument("--output", required=True, type=Path, help="Analysis output directory")
    arguments = parser.parse_args()

    apk_path = arguments.input.expanduser().resolve()
    output_dir = arguments.output.expanduser().resolve()
    if not apk_path.is_file():
        parser.error(f"Input file does not exist: {apk_path}")
    if apk_path.suffix.lower() != ".apk":
        parser.error("Input must have a .apk extension.")

    input_sha256 = sha256(apk_path)
    evidence_path = output_dir / "evidence" / "reverse-static.json"
    decompiled_dir = output_dir / "evidence" / "reverse-decompiled" / input_sha256
    if not UPSTREAM_WRAPPER.is_file():
        print("Reverse-static analysis failed: the vendored reverse-engineering wrapper is missing.", file=sys.stderr)
        return 2
    try:
        jadx = require_jadx(output_dir)
    except ToolchainError as error:
        print(f"Reverse-static analysis failed: {error}", file=sys.stderr)
        return 2

    try:
        tool_environment = os.environ.copy()
        tool_environment["APPLENS_JADX"] = jadx
        tool_environment.update(java_environment(output_dir))
        result = subprocess.run(
            [str(UPSTREAM_WRAPPER), "--engine", "jadx", "--no-res", "--output", str(decompiled_dir), str(apk_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=900,
            env=tool_environment,
        )
        paths = source_paths(decompiled_dir)
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"Reverse-static analysis failed: the required JADX run did not complete: {error}", file=sys.stderr)
        return 2

    if result.returncode != 0 or not paths:
        message = result.stderr.strip() or "jadx produced no usable UI structure evidence."
        print(f"Reverse-static analysis failed: {message[:1000]}", file=sys.stderr)
        return 2

    payload = evidence_payload(
        "completed",
        input_sha256=input_sha256,
        decompiled_workspace=f"evidence/reverse-decompiled/{input_sha256}",
        ui_structure=summarize_ui_structure(paths),
    )
    write_json(evidence_path, payload)
    print(evidence_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
