#!/usr/bin/env python3
"""List or explicitly delete expired, non-delivery AppLens working data."""

from __future__ import annotations

import argparse
import shutil
import time
from pathlib import Path

from model_tools import working_root


def newest_mtime(path: Path) -> float:
    newest = path.stat().st_mtime
    for child in path.rglob("*"):
        try:
            newest = max(newest, child.stat().st_mtime)
        except OSError:
            continue
    return newest


def size_bytes(path: Path) -> int:
    total = 0
    for child in path.rglob("*"):
        try:
            if child.is_file():
                total += child.stat().st_size
        except OSError:
            continue
    return total


def cleanup_candidates(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for path in root.iterdir():
        if not path.is_dir():
            continue
        if path.name == "reverse-decompiled":
            candidates.extend(child for child in path.iterdir() if child.is_dir())
        else:
            candidates.append(path)
    return sorted(candidates)


def all_working_candidates(output_dir: Path) -> list[Path]:
    candidates: list[Path] = []
    current_root = working_root(output_dir)
    if current_root.is_dir():
        candidates.extend(cleanup_candidates(current_root))
    legacy_root = output_dir / "evidence" / "reverse-decompiled"
    if legacy_root.is_dir():
        candidates.extend(child for child in legacy_root.iterdir() if child.is_dir())
    return sorted(candidates)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="Analysis output directory")
    parser.add_argument("--older-than-hours", type=float, default=24, help="Only consider working data older than this age (default: 24)")
    parser.add_argument("--confirm-delete", action="store_true", help="Required before deleting any eligible working data")
    arguments = parser.parse_args()
    if arguments.older_than_hours < 0:
        parser.error("--older-than-hours cannot be negative.")

    output_dir = arguments.output.expanduser().resolve()
    if not working_root(output_dir).is_dir() and not (output_dir / "evidence" / "reverse-decompiled").is_dir():
        print("No AppLens working data found.")
        return 0
    cutoff = time.time() - arguments.older_than_hours * 3600
    candidates = [path for path in all_working_candidates(output_dir) if newest_mtime(path) <= cutoff]
    if not candidates:
        print("No expired AppLens working data found.")
        return 0
    for path in candidates:
        print(f"candidate={path.relative_to(output_dir)} bytes={size_bytes(path)}")
    if not arguments.confirm_delete:
        print("No data deleted. Re-run with --confirm-delete to remove the listed working data.")
        return 0
    for path in candidates:
        shutil.rmtree(path)
        print(f"deleted={path.relative_to(output_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
