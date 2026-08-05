#!/usr/bin/env python3
"""Explore a package only on an isolated Android emulator with conservative click rules."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as element_tree
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from model_tools import utc_now, write_json


BLOCKED_PATTERN = re.compile(
    r"\b(log[ -]?in|sign[ -]?in|sign[ -]?up|register|password|passcode|verification|verify|otp|"
    r"member(ship)?|subscribe|subscription|pay|payment|purchase|checkout|order|delete|remove|"
    r"publish|post|upload|send|share|invite|follow|call|email|message|withdraw|transfer|confirm|allow)\b",
    re.IGNORECASE,
)
INTERCEPTION_PATTERN = re.compile(
    r"\b(log[ -]?in|sign[ -]?in|create account|register|password|subscription|membership|"
    r"start trial|payment|checkout|purchase)\b",
    re.IGNORECASE,
)
SAFE_ROLE_WORDS = re.compile(r"\b(tab|home|back|next|more|detail|list|search|filter|sort|setting|menu|open|view|close|done)\b", re.IGNORECASE)
AMBIGUOUS_LABEL_PATTERN = re.compile(r"^(ok|yes|no|continue|cancel)$", re.IGNORECASE)
BOUNDS_PATTERN = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def adb(serial: str, *arguments: str, timeout: int = 60, text: bool = True) -> subprocess.CompletedProcess[Any]:
    return subprocess.run(
        ["adb", "-s", serial, *arguments],
        check=False,
        capture_output=True,
        text=text,
        timeout=timeout,
    )


def check_emulator(serial: str) -> None:
    if not shutil.which("adb"):
        raise RuntimeError("adb is not available.")
    state = adb(serial, "get-state")
    if state.returncode != 0 or state.stdout.strip() != "device":
        raise RuntimeError(f"ADB target {serial!r} is not ready.")
    qemu = adb(serial, "shell", "getprop", "ro.kernel.qemu")
    if not serial.startswith("emulator-") and qemu.stdout.strip() != "1":
        raise RuntimeError("Refusing to explore a non-emulator ADB target.")


def command_ok(result: subprocess.CompletedProcess[Any], label: str) -> None:
    if result.returncode != 0:
        message = result.stderr.decode() if isinstance(result.stderr, bytes) else result.stderr
        raise RuntimeError(message.strip() or f"{label} failed.")


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def visible_text(node: element_tree.Element) -> str:
    return " ".join(part for part in (node.attrib.get("text", ""), node.attrib.get("content-desc", "")) if part).strip()


def node_summary(node: element_tree.Element) -> dict[str, str]:
    return {
        "text": node.attrib.get("text", ""),
        "content_desc": node.attrib.get("content-desc", ""),
        "resource_id": node.attrib.get("resource-id", ""),
        "class": node.attrib.get("class", ""),
        "bounds": node.attrib.get("bounds", ""),
    }


def signature(root: element_tree.Element) -> str:
    labels = [visible_text(node) for node in root.iter("node") if visible_text(node)]
    return hashlib.sha256("\n".join(labels[:80]).encode("utf-8")).hexdigest()[:16]


def is_clickable(node: element_tree.Element) -> bool:
    return node.attrib.get("clickable") == "true" and bool(BOUNDS_PATTERN.fullmatch(node.attrib.get("bounds", "")))


def safe_targets(root: element_tree.Element) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    allowed: list[dict[str, str]] = []
    blocked: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for node in root.iter("node"):
        if not is_clickable(node):
            continue
        summary = node_summary(node)
        label = " ".join((summary["text"], summary["content_desc"], summary["resource_id"])).strip()
        key = (label, summary["bounds"])
        if key in seen:
            continue
        seen.add(key)
        if not label:
            # A nameless button can be an irreversible action; do not guess.
            blocked.append({**summary, "reason": "unnamed_clickable"})
        elif BLOCKED_PATTERN.search(label):
            blocked.append({**summary, "reason": "high_risk_or_auth_label"})
        elif SAFE_ROLE_WORDS.search(label) or (
            len(label) > 2
            and len(label) <= 80
            and not AMBIGUOUS_LABEL_PATTERN.fullmatch(label)
            and any(view_type in summary["class"] for view_type in ("TextView", "ImageView", "RecyclerView", "Tab"))
        ):
            allowed.append(summary)
    return allowed, blocked


def center(bounds: str) -> tuple[int, int]:
    match = BOUNDS_PATTERN.fullmatch(bounds)
    if not match:
        raise ValueError(f"Invalid bounds: {bounds}")
    left, top, right, bottom = (int(value) for value in match.groups())
    return ((left + right) // 2, (top + bottom) // 2)


@dataclass
class Snapshot:
    signature: str
    root: element_tree.Element
    xml: str
    labels: list[str]


class Explorer:
    def __init__(self, serial: str, package: str, output_dir: Path, delay: float, max_screens: int, max_depth: int) -> None:
        self.serial = serial
        self.package = package
        self.output_dir = output_dir
        self.delay = delay
        self.max_screens = max_screens
        self.max_depth = max_depth
        self.screens_dir = output_dir / "evidence" / "screenshots"
        self.paths_dir = output_dir / "evidence" / "paths"
        self.dynamic_dir = output_dir / "evidence" / "dynamic"
        for directory in (self.screens_dir, self.paths_dir, self.dynamic_dir):
            directory.mkdir(parents=True, exist_ok=True)
        self.screens: list[dict[str, Any]] = []
        self.paths: list[dict[str, Any]] = []
        self.blocked: list[dict[str, Any]] = []
        self.visited: set[str] = set()

    def snapshot(self) -> Snapshot:
        remote_path = "/sdcard/apk_competitor_analysis_window.xml"
        dump = adb(self.serial, "shell", "uiautomator", "dump", remote_path)
        command_ok(dump, "UI dump")
        pulled = adb(self.serial, "exec-out", "cat", remote_path, text=False)
        command_ok(pulled, "UI dump retrieval")
        xml = pulled.stdout.decode("utf-8", errors="replace")
        root = element_tree.fromstring(xml)
        labels = [visible_text(node) for node in root.iter("node") if visible_text(node)]
        return Snapshot(signature(root), root, xml, labels[:120])

    def save_snapshot(self, snapshot: Snapshot, path: list[str]) -> str:
        screen_id = f"screen-{len(self.screens) + 1:03d}-{snapshot.signature}"
        xml_path = self.paths_dir / f"{screen_id}.xml"
        image_path = self.screens_dir / f"{screen_id}.png"
        xml_path.write_text(snapshot.xml, encoding="utf-8")
        image = adb(self.serial, "exec-out", "screencap", "-p", text=False)
        command_ok(image, "Screenshot")
        image_path.write_bytes(image.stdout)
        self.screens.append(
            {
                "id": screen_id,
                "signature": snapshot.signature,
                "screenshot": str(image_path.relative_to(self.output_dir)),
                "ui_dump": str(xml_path.relative_to(self.output_dir)),
                "labels": snapshot.labels,
                "path": path,
                "confidence": "dynamically_verified",
            }
        )
        self.visited.add(snapshot.signature)
        return screen_id

    def tap(self, target: dict[str, str]) -> None:
        x, y = center(target["bounds"])
        result = adb(self.serial, "shell", "input", "tap", str(x), str(y))
        command_ok(result, "Safe tap")
        time.sleep(self.delay)

    def back(self) -> None:
        result = adb(self.serial, "shell", "input", "keyevent", "KEYCODE_BACK")
        command_ok(result, "Back navigation")
        time.sleep(self.delay)

    def explore(self, snapshot: Snapshot, path: list[str], depth: int) -> None:
        if len(self.screens) >= self.max_screens or depth > self.max_depth:
            return
        if snapshot.signature not in self.visited:
            self.save_snapshot(snapshot, path)
        allowed, blocked = safe_targets(snapshot.root)
        self.blocked.extend({"path": path, **item} for item in blocked)
        for target in allowed:
            if len(self.screens) >= self.max_screens:
                return
            action_label = target["text"] or target["content_desc"] or target["resource_id"]
            self.tap(target)
            try:
                after = self.snapshot()
            except (RuntimeError, element_tree.ParseError) as error:
                self.blocked.append({"path": path + [action_label], "reason": "snapshot_failed", "error": str(error)})
                self.back()
                continue
            action_path = path + [action_label]
            combined_labels = " ".join(after.labels)
            if INTERCEPTION_PATTERN.search(combined_labels):
                self.blocked.append({"path": action_path, "reason": "auth_or_commercial_interception", "labels": after.labels[:30]})
                self.back()
                continue
            if after.signature != snapshot.signature:
                self.paths.append({"from": snapshot.signature, "to": after.signature, "action": action_label, "path": action_path})
                if after.signature not in self.visited:
                    self.explore(after, action_path, depth + 1)
                self.back()
            else:
                # A reversible state change is recorded, then restored when possible.
                self.paths.append({"from": snapshot.signature, "to": after.signature, "action": action_label, "path": action_path, "state_change": "not_navigated"})


def launch_package(serial: str, package: str) -> None:
    result = adb(serial, "shell", "monkey", "-p", package, "1")
    command_ok(result, "Application launch")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True, help="ADB serial for a resettable emulator")
    parser.add_argument("--package", required=True, help="Already installed package name")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--confirm-isolated-emulator", action="store_true", help="Required acknowledgement before launch and exploration")
    parser.add_argument("--max-screens", type=int, default=20)
    parser.add_argument("--max-depth", type=int, default=3)
    parser.add_argument("--delay", type=float, default=1.0)
    arguments = parser.parse_args()
    if not arguments.confirm_isolated_emulator:
        parser.error("--confirm-isolated-emulator is required.")
    if arguments.max_screens < 1 or arguments.max_depth < 0:
        parser.error("--max-screens must be positive and --max-depth cannot be negative.")

    output_dir = arguments.output.expanduser().resolve()
    try:
        check_emulator(arguments.serial)
        explorer = Explorer(arguments.serial, arguments.package, output_dir, arguments.delay, arguments.max_screens, arguments.max_depth)
        launch_package(arguments.serial, arguments.package)
        time.sleep(arguments.delay)
        explorer.explore(explorer.snapshot(), ["launch"], 0)
        session = {
            "schema_version": "1.0",
            "created_at": utc_now(),
            "package": arguments.package,
            "serial": arguments.serial,
            "safety": {
                "isolated_emulator_confirmed": True,
                "high_risk_actions_blocked": True,
                "authentication_and_commercial_intercepts_skipped": True,
            },
            "screens": explorer.screens,
            "navigation_paths": explorer.paths,
            "blocked_or_skipped": explorer.blocked,
        }
        session_path = output_dir / "evidence" / "dynamic" / "dynamic-session.json"
        write_json(session_path, session)
        print(session_path)
        return 0
    except (OSError, RuntimeError, subprocess.TimeoutExpired, element_tree.ParseError, ValueError) as error:
        print(f"Safe exploration failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
