#!/usr/bin/env python3
"""Shared, dependency-free utilities for the local project model."""

from __future__ import annotations

import json
import os
import hashlib
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CONFIDENCE_LEVELS = {"dynamically_verified", "static_inference", "unconfirmed"}
PRODUCT_DECISIONS = {"keep", "modify", "delete", "add"}
ABSTRACT_ADOPTION_NOTE = "采用全部抽象功能；使用原创品牌、图标、文案、图片、Mock 数据和本地逻辑，不复制竞品资产或专有实现。"
FEATURE_DISPLAY_NAMES = {
    "Camera capture": "相机采集",
    "External sharing": "外部分享",
    "Filter or sort": "筛选或排序",
    "Location-aware experience": "位置相关体验",
    "Map browsing": "地图浏览",
    "Notification preferences": "通知偏好",
    "Save or bookmark": "保存或收藏",
    "Save or favorite": "收藏或喜欢",
    "Profile area": "个人资料",
    "Search": "搜索",
    "Settings": "设置",
}
FUNCTION_FIELDS = (
    "name",
    "entry",
    "flow",
    "pages",
    "page_states",
    "interaction_rules",
    "competitor_evidence",
    "confidence",
    "product_decision",
    "modification_notes",
    "acceptance_criteria",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def write_json(path: Path, payload: Any) -> None:
    """Atomically replace a JSON artifact without leaving a partial model."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            json.dump(payload, target, ensure_ascii=False, indent=2)
            target.write("\n")
        Path(temporary_name).replace(path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def write_text(path: Path, content: str) -> None:
    """Atomically write a text artifact without leaving a partial delivery file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            target.write(content)
        Path(temporary_name).replace(path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def internal_root(output_dir: Path) -> Path:
    """Return the isolated, non-delivery working area for one analysis run."""
    return output_dir / ".applens"


def toolchain_root(output_dir: Path) -> Path:
    return internal_root(output_dir) / "toolchain"


def working_root(output_dir: Path) -> Path:
    return internal_root(output_dir) / "work"


def jadx_home(output_dir: Path) -> Path:
    return internal_root(output_dir) / "jadx-home"


def output_layout(output_dir: Path) -> None:
    for directory in (
        output_dir / "evidence" / "screenshots",
        output_dir / "evidence" / "paths",
        output_dir / "evidence" / "dynamic",
        output_dir / "flutter_prototype",
        output_dir / "docs",
        toolchain_root(output_dir),
        working_root(output_dir),
        jadx_home(output_dir),
    ):
        directory.mkdir(parents=True, exist_ok=True)


def model_path(output_dir: Path) -> Path:
    return output_dir / "project-model.json"


def load_model(output_dir: Path) -> dict[str, Any]:
    payload = load_json(model_path(output_dir))
    if not isinstance(payload, dict):
        raise ValueError("project-model.json must contain an object.")
    return payload


def append_audit(model: dict[str, Any], event: str, details: dict[str, Any]) -> None:
    audit = model.setdefault("audit", [])
    if not isinstance(audit, list):
        raise ValueError("Model audit must be a list.")
    audit.append({"at": utc_now(), "event": event, "details": details})


def adopt_all_abstract_features(model: dict[str, Any]) -> tuple[int, bool]:
    """Adopt every evidence-derived feature for an original implementation."""
    functions = model.get("functions")
    if not isinstance(functions, list):
        raise ValueError("model.functions must be a list.")

    changed = False
    adopted_count = 0
    for function in functions:
        if not isinstance(function, dict):
            raise ValueError("Every model function must be an object.")
        adopted_count += 1
        if function.get("product_decision") != "keep" or function.get("modification_notes") != ABSTRACT_ADOPTION_NOTE:
            changed = True
        function["product_decision"] = "keep"
        function["modification_notes"] = ABSTRACT_ADOPTION_NOTE

    if changed:
        generation = model.setdefault("generation", {})
        if not isinstance(generation, dict):
            raise ValueError("model.generation must be an object.")
        generation["approved_model_version"] = None
        generation["approved_at"] = None
        generation["approved_model_fingerprint"] = None
        generation["prd_status"] = "blocked_pending_confirmation"
        project = model.setdefault("project", {})
        if not isinstance(project, dict):
            raise ValueError("model.project must be an object.")
        project["status"] = "model_review"
        append_audit(
            model,
            "all_abstract_features_adopted",
            {
                "count": adopted_count,
                "mode": "original_abstract_features",
                "excluded": ["competitor brands", "proprietary assets", "backend logic", "authentication and payment"],
            },
        )
    return adopted_count, changed


def display_feature_name(name: Any) -> str:
    """Return the localized user-facing name while preserving raw evidence names."""
    value = str(name)
    return FEATURE_DISPLAY_NAMES.get(value, value)


def approval_fingerprint(model: dict[str, Any]) -> str:
    """Hash only the editable product decisions that PRD/prototype generation uses."""
    project = model.get("project", {})
    payload = {
        "project": {
            "name": project.get("name") if isinstance(project, dict) else None,
            "analysis_scope": project.get("analysis_scope") if isinstance(project, dict) else None,
        },
        "visual_model": model.get("visual_model"),
        "functions": model.get("functions"),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def new_function(name: str, confidence: str = "unconfirmed") -> dict[str, Any]:
    """Return an explicitly incomplete function for product-owner editing."""
    return {
        "name": name,
        "entry": "",
        "flow": [],
        "pages": [],
        "page_states": [],
        "interaction_rules": [],
        "competitor_evidence": [],
        "confidence": confidence,
        "product_decision": "modify",
        "modification_notes": "Requires product-owner review.",
        "acceptance_criteria": [],
    }


def validation_errors(model: dict[str, Any], require_confirmation: bool = False) -> list[str]:
    errors: list[str] = []
    if model.get("schema_version") != "1.0":
        errors.append("schema_version must be 1.0")

    project = model.get("project")
    if not isinstance(project, dict):
        errors.append("project must be an object")
    else:
        for key in ("name", "status", "analysis_scope"):
            if not isinstance(project.get(key), str) or not project[key].strip():
                errors.append(f"project.{key} must be a non-empty string")

    functions = model.get("functions")
    if not isinstance(functions, list):
        errors.append("functions must be a list")
    else:
        for index, function in enumerate(functions):
            prefix = f"functions[{index}]"
            if not isinstance(function, dict):
                errors.append(f"{prefix} must be an object")
                continue
            missing = [field for field in FUNCTION_FIELDS if field not in function]
            if missing:
                errors.append(f"{prefix} is missing: {', '.join(missing)}")
                continue
            if not isinstance(function["name"], str) or not function["name"].strip():
                errors.append(f"{prefix}.name must be a non-empty string")
            if function["confidence"] not in CONFIDENCE_LEVELS:
                errors.append(f"{prefix}.confidence is invalid")
            if function["product_decision"] not in PRODUCT_DECISIONS:
                errors.append(f"{prefix}.product_decision is invalid")
            for field in ("flow", "pages", "page_states", "interaction_rules", "competitor_evidence", "acceptance_criteria"):
                if not isinstance(function[field], list):
                    errors.append(f"{prefix}.{field} must be a list")
            for field in ("entry", "modification_notes"):
                if not isinstance(function[field], str):
                    errors.append(f"{prefix}.{field} must be a string")

    generation = model.get("generation")
    if not isinstance(generation, dict):
        errors.append("generation must be an object")
    elif require_confirmation and not isinstance(generation.get("approved_model_version"), str):
        errors.append("generation.approved_model_version is required before PRD generation")
    return errors
