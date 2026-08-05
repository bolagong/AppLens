#!/usr/bin/env python3
"""Create API-safe UI structure evidence with the vendored reverse-engineering wrapper."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from analysis_toolchain import ToolchainError, java_environment, require_jadx
from evidence_summary import write_evidence_summary
from model_tools import jadx_home, working_root, write_json


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
DEFAULT_JADX_TIMEOUT_SECONDS = 3600
DEFAULT_JADX_THREADS = 4
PROGRESS_INTERVAL_SECONDS = 5


def source_paths(decompiled_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in decompiled_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in {".java", ".kt"}
    )


def source_file_count(decompiled_dir: Path) -> int:
    return sum(
        1
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


def write_failure_evidence(
    evidence_path: Path,
    input_sha256: str,
    decompiled_dir: Path,
    reason: str,
    timeout_seconds: int | None = None,
) -> None:
    failure: dict[str, Any] = {"reason": reason}
    if timeout_seconds is not None:
        failure["timeout_seconds"] = timeout_seconds
    write_json(
        evidence_path,
        evidence_payload(
            "failed",
            input_sha256=input_sha256,
            decompiled_workspace=f".applens/work/reverse-decompiled/{input_sha256}",
            failure=failure,
        ),
    )


def write_progress(output_dir: Path, status: str, started_at: str, elapsed_seconds: int, timeout_seconds: int, threads: int, decompiled_dir: Path) -> None:
    write_json(
        output_dir / "evidence" / "reverse-progress.json",
        {
            "schema_version": "1.0",
            "status": status,
            "started_at": started_at,
            "elapsed_seconds": elapsed_seconds,
            "timeout_seconds": timeout_seconds,
            "threads": threads,
            "source_file_count": source_file_count(decompiled_dir),
        },
    )


def stop_process(process: subprocess.Popen[bytes] | subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Path to a user-provided .apk file")
    parser.add_argument("--output", required=True, type=Path, help="Analysis output directory")
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_JADX_TIMEOUT_SECONDS,
        help=f"Maximum JADX runtime in seconds (default: {DEFAULT_JADX_TIMEOUT_SECONDS})",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=DEFAULT_JADX_THREADS,
        help=f"JADX processing thread count (default: {DEFAULT_JADX_THREADS})",
    )
    arguments = parser.parse_args()

    apk_path = arguments.input.expanduser().resolve()
    output_dir = arguments.output.expanduser().resolve()
    if not apk_path.is_file():
        parser.error(f"Input file does not exist: {apk_path}")
    if apk_path.suffix.lower() != ".apk":
        parser.error("Input must have a .apk extension.")
    if arguments.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be greater than zero.")
    if arguments.threads <= 0:
        parser.error("--threads must be greater than zero.")

    input_sha256 = sha256(apk_path)
    evidence_path = output_dir / "evidence" / "reverse-static.json"
    decompiled_dir = working_root(output_dir) / "reverse-decompiled" / input_sha256
    cancel_request = working_root(output_dir) / "reverse-cancel-request.json"
    if not UPSTREAM_WRAPPER.is_file():
        print("Reverse-static analysis failed: the vendored reverse-engineering wrapper is missing.", file=sys.stderr)
        return 2
    try:
        jadx = require_jadx(output_dir)
    except ToolchainError as error:
        print(f"Reverse-static analysis failed: {error}", file=sys.stderr)
        return 2

    started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    started_monotonic = time.monotonic()
    process: subprocess.Popen[bytes] | subprocess.Popen[str] | None = None
    try:
        tool_environment = os.environ.copy()
        tool_environment["APPLENS_JADX"] = jadx
        tool_environment.update(java_environment(output_dir))
        local_jadx_home = jadx_home(output_dir)
        local_jadx_home.mkdir(parents=True, exist_ok=True)
        existing_jadx_options = tool_environment.get("JADX_OPTS", "").strip()
        user_home_option = shlex.quote(f"-Duser.home={local_jadx_home}")
        tool_environment["JADX_OPTS"] = f"{existing_jadx_options} {user_home_option}".strip()
        process = subprocess.Popen(
            [
                str(UPSTREAM_WRAPPER),
                "--engine",
                "jadx",
                "--no-res",
                "--threads",
                str(arguments.threads),
                "--output",
                str(decompiled_dir),
                str(apk_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=tool_environment,
        )
        while process.poll() is None:
            elapsed_seconds = int(time.monotonic() - started_monotonic)
            if cancel_request.is_file():
                stop_process(process)
                cancel_request.unlink(missing_ok=True)
                write_failure_evidence(evidence_path, input_sha256, decompiled_dir, "cancelled")
                write_progress(output_dir, "cancelled", started_at, elapsed_seconds, arguments.timeout_seconds, arguments.threads, decompiled_dir)
                write_evidence_summary(output_dir)
                print("Reverse-static analysis cancelled.", file=sys.stderr)
                return 2
            if elapsed_seconds >= arguments.timeout_seconds:
                stop_process(process)
                write_failure_evidence(evidence_path, input_sha256, decompiled_dir, "timeout", arguments.timeout_seconds)
                write_progress(output_dir, "failed", started_at, elapsed_seconds, arguments.timeout_seconds, arguments.threads, decompiled_dir)
                write_evidence_summary(output_dir)
                print(
                    f"Reverse-static analysis failed: the required JADX run exceeded the {arguments.timeout_seconds}-second timeout.",
                    file=sys.stderr,
                )
                return 2
            write_progress(output_dir, "running", started_at, elapsed_seconds, arguments.timeout_seconds, arguments.threads, decompiled_dir)
            time.sleep(PROGRESS_INTERVAL_SECONDS)
        result_code = process.returncode
        paths = source_paths(decompiled_dir)
    except OSError:
        write_failure_evidence(evidence_path, input_sha256, decompiled_dir, "execution_error")
        write_progress(
            output_dir,
            "failed",
            started_at,
            int(time.monotonic() - started_monotonic),
            arguments.timeout_seconds,
            arguments.threads,
            decompiled_dir,
        )
        write_evidence_summary(output_dir)
        print("Reverse-static analysis failed: the required JADX run did not complete.", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        if process is not None:
            stop_process(process)
        write_failure_evidence(evidence_path, input_sha256, decompiled_dir, "cancelled")
        write_progress(
            output_dir,
            "cancelled",
            started_at,
            int(time.monotonic() - started_monotonic),
            arguments.timeout_seconds,
            arguments.threads,
            decompiled_dir,
        )
        write_evidence_summary(output_dir)
        print("Reverse-static analysis cancelled.", file=sys.stderr)
        return 2

    elapsed_seconds = int(time.monotonic() - started_monotonic)
    if result_code != 0 or not paths:
        write_failure_evidence(evidence_path, input_sha256, decompiled_dir, "no_usable_ui_structure")
        write_progress(output_dir, "failed", started_at, elapsed_seconds, arguments.timeout_seconds, arguments.threads, decompiled_dir)
        write_evidence_summary(output_dir)
        print("Reverse-static analysis failed: JADX produced no usable UI structure evidence.", file=sys.stderr)
        return 2

    payload = evidence_payload(
        "completed",
        input_sha256=input_sha256,
        decompiled_workspace=f".applens/work/reverse-decompiled/{input_sha256}",
        ui_structure=summarize_ui_structure(paths),
    )
    write_json(evidence_path, payload)
    write_progress(output_dir, "completed", started_at, elapsed_seconds, arguments.timeout_seconds, arguments.threads, decompiled_dir)
    write_evidence_summary(output_dir)
    print(evidence_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
