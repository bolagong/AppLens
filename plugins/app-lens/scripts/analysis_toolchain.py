"""Resolve the mandatory local tools for a full AppLens analysis."""

from __future__ import annotations

import os
import shutil
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any


class ToolchainError(RuntimeError):
    """Raised before analysis when a required local tool is unavailable."""


def resolve_required_tools(
    environment: Mapping[str, str] | None = None,
    find_command: Callable[[str], str | None] = shutil.which,
    output_dir: Path | None = None,
) -> dict[str, str | None]:
    """Resolve explicit overrides first, then the host PATH.

    `APPLENS_AAPT` and `APPLENS_JADX` allow a release to point at vetted,
    plugin-provided binaries without changing a user's global PATH.
    """
    values = os.environ if environment is None else environment
    cached = provisioned_toolchain(output_dir) if output_dir is not None else {}
    aapt = values.get("APPLENS_AAPT") or cached.get("aapt") or find_command("aapt") or find_command("aapt2")
    jadx = values.get("APPLENS_JADX") or cached.get("jadx") or find_command("jadx")
    return {"aapt": aapt, "jadx": jadx}


def provisioned_toolchain(output_dir: Path | None) -> dict[str, str]:
    """Read only a local toolchain receipt created inside the selected output."""
    if output_dir is None:
        return {}
    receipt = output_dir / "evidence" / "toolchain.json"
    try:
        payload: Any = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}
    tools = payload.get("tools") if isinstance(payload, dict) else None
    if not isinstance(tools, dict):
        return {}
    result: dict[str, str] = {}
    for name in ("aapt", "jadx"):
        value = tools.get(name)
        if isinstance(value, str) and Path(value).is_file():
            result[name] = value
    return result


def provisioned_java_home(output_dir: Path | None) -> str | None:
    if output_dir is None:
        return None
    receipt = output_dir / "evidence" / "toolchain.json"
    try:
        payload: Any = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    java_home = payload.get("java_home") if isinstance(payload, dict) else None
    return java_home if isinstance(java_home, str) and Path(java_home).is_dir() else None


def java_environment(output_dir: Path | None) -> dict[str, str]:
    """Return environment additions for a provisioned local JRE, if any."""
    java_home = provisioned_java_home(output_dir)
    if not java_home:
        return {}
    bin_dir = Path(java_home) / "bin"
    if not bin_dir.is_dir():
        return {}
    return {"JAVA_HOME": java_home, "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}


def missing_required_tools(tools: Mapping[str, str | None]) -> list[str]:
    missing: list[str] = []
    if not tools.get("aapt"):
        missing.append("aapt or aapt2")
    if not tools.get("jadx"):
        missing.append("jadx")
    return missing


def require_aapt(output_dir: Path | None = None) -> str:
    path = resolve_required_tools(output_dir=output_dir)["aapt"]
    if not path:
        raise ToolchainError(
            "Full AppLens analysis requires aapt or aapt2. Install Android SDK Build-Tools or set APPLENS_AAPT to a vetted binary."
        )
    return path


def require_jadx(output_dir: Path | None = None) -> str:
    path = resolve_required_tools(output_dir=output_dir)["jadx"]
    if not path:
        raise ToolchainError(
            "Full AppLens analysis requires jadx. Install the vetted JADX distribution or set APPLENS_JADX to its executable."
        )
    return path


def require_full_toolchain(output_dir: Path | None = None) -> dict[str, str]:
    tools = resolve_required_tools(output_dir=output_dir)
    missing = missing_required_tools(tools)
    if missing:
        raise ToolchainError(
            "Full AppLens analysis cannot start because required tools are missing: "
            + ", ".join(missing)
            + ". Install the required toolchain or set APPLENS_AAPT and APPLENS_JADX. No reduced-evidence model will be generated."
        )
    return {"aapt": str(tools["aapt"]), "jadx": str(tools["jadx"])}
