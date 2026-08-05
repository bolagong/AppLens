#!/usr/bin/env python3
"""Dependency-free release checks for this plugin source tree."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
REQUIRED_SCRIPTS = {
    "preflight.sh", "static_inventory.py", "reverse_static_inventory.py", "bootstrap_project.py", "derive_candidates.py",
    "install_to_emulator.py", "safe_explore.py", "ingest_dynamic_evidence.py", "serve_workbench.py",
    "approve_model.py", "generate_flutter.py", "verify_flutter.py", "generate_prd.py", "validate_model.py",
}
FORBIDDEN_SCRIPTS = {"adb_acquire.py"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plugin", nargs="?", type=Path, default=Path(__file__).resolve().parent.parent)
    arguments = parser.parse_args()
    root = arguments.plugin.expanduser().resolve()
    errors: list[str] = []
    manifest_path = root / ".codex-plugin" / "plugin.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"Release validation failed: cannot read manifest: {error}", file=sys.stderr)
        return 2
    if manifest.get("name") != root.name:
        errors.append("manifest name must match the plugin folder name")
    if not SEMVER.fullmatch(str(manifest.get("version", ""))):
        errors.append("manifest version must be strict semantic versioning")
    for key in ("description", "author", "skills", "interface"):
        if key not in manifest:
            errors.append(f"manifest is missing {key}")
    interface = manifest.get("interface", {})
    for key in ("displayName", "shortDescription", "longDescription", "developerName", "category", "defaultPrompt"):
        if key not in interface:
            errors.append(f"manifest interface is missing {key}")
    skill = root / "skills" / "app-lens" / "SKILL.md"
    try:
        skill_text = skill.read_text(encoding="utf-8")
        if not skill_text.startswith("---\n") or "\n---\n" not in skill_text[:1000]:
            errors.append("Skill front matter is missing or malformed")
        for key in ("name:", "description:"):
            if key not in skill_text[:1000]:
                errors.append(f"Skill front matter is missing {key}")
    except OSError:
        errors.append("core Skill file is missing")
    missing_scripts = sorted(name for name in REQUIRED_SCRIPTS if not (root / "scripts" / name).is_file())
    if missing_scripts:
        errors.append(f"missing scripts: {', '.join(missing_scripts)}")
    forbidden_scripts = sorted(name for name in FORBIDDEN_SCRIPTS if (root / "scripts" / name).exists())
    if forbidden_scripts:
        errors.append(f"unsupported device-acquisition scripts present: {', '.join(forbidden_scripts)}")
    for required in (
        root / "third_party" / "android-reverse-engineering-skill" / "decompile.sh",
        root / "third_party" / "android-reverse-engineering-skill" / "LICENSE",
        root / "third_party" / "android-reverse-engineering-skill" / "NOTICE.md",
    ):
        if not required.is_file():
            errors.append(f"missing reverse-engineering dependency file: {required.relative_to(root)}")
    for required in (root / "README.md", root / "workbench" / "index.html", root / "RELEASE.md"):
        if not required.is_file():
            errors.append(f"missing release file: {required.relative_to(root)}")
    repository_root = root.parents[1]
    marketplace_path = repository_root / ".agents" / "plugins" / "marketplace.json"
    try:
        marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
        entries = marketplace.get("plugins", []) if isinstance(marketplace, dict) else []
        entry = next((item for item in entries if isinstance(item, dict) and item.get("name") == root.name), None)
        if not entry:
            errors.append("Marketplace manifest does not list this plugin")
        elif entry.get("source", {}).get("path") != f"./plugins/{root.name}":
            errors.append("Marketplace source path does not match the plugin path")
    except (OSError, json.JSONDecodeError):
        errors.append("missing or invalid .agents/plugins/marketplace.json")
    if errors:
        print("Release validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 2
    print(f"Release validation passed: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
