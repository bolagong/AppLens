#!/usr/bin/env python3
"""Generate a Markdown PRD from an explicitly confirmed project model."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from model_tools import approval_fingerprint, append_audit, display_feature_name, load_model, utc_now, validation_errors, write_json


def items(value: Any) -> list[str]:
    return [str(item) for item in value if str(item).strip()] if isinstance(value, list) else []


def bullet_list(values: Any, empty: str = "待产品确认") -> str:
    entries = items(values)
    return "\n".join(f"- {entry}" for entry in entries) if entries else f"- {empty}"


def evidence_list(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return "- 无直接证据；不作为已确认事实"
    entries = []
    for item in value:
        if isinstance(item, dict):
            path = item.get("path", "")
            note = item.get("note", "")
            entries.append(f"- {path}{'：' if path and note else ''}{note}")
        else:
            entries.append(f"- {item}")
    return "\n".join(entries)


def render_function(function: dict[str, Any]) -> str:
    return f'''### {display_feature_name(function.get("name", "未命名功能"))}

- 采用方式：全部抽象功能均以原创实现采用
- 置信度：{function.get("confidence", "unconfirmed")}
- 入口：{function.get("entry") or "待产品确认"}
- 修改说明：{function.get("modification_notes") or "无"}

流程：
{bullet_list(function.get("flow"))}

涉及页面：
{bullet_list(function.get("pages"))}

页面状态：
{bullet_list(function.get("page_states"))}

交互规则：
{bullet_list(function.get("interaction_rules"))}

竞品证据：
{evidence_list(function.get("competitor_evidence"))}

验收标准：
{bullet_list(function.get("acceptance_criteria"))}
'''


def build_prd(model: dict[str, Any]) -> str:
    project = model["project"]
    generation = model["generation"]
    functions = [item for item in model.get("functions", []) if isinstance(item, dict) and item.get("product_decision") != "delete"]
    visual = model.get("visual_model", {})
    notes = bullet_list(visual.get("reference_notes"), "使用原创品牌、图标、文案与 Mock 数据")
    architecture = "\n".join(f"- {display_feature_name(item.get('name', '未命名功能'))}" for item in functions) or "- 当前版本未选择功能"
    function_sections = "\n\n".join(render_function(item) for item in functions) or "本期未选择功能。"
    return f'''# {project["name"]} PRD

## 1. 文档信息与变更记录

| 字段 | 内容 |
| --- | --- |
| 产品方案版本 | {generation["approved_model_version"]} |
| 状态 | 已确认，基于本地证据与产品方案层生成 |
| 生成时间 | {utc_now()} |
| 分析范围 | {project["analysis_scope"]} |

## 2. 本期范围与非目标

本期范围为本地证据抽象出的全部功能与页面，并以原创品牌、图标、文案、图片、Mock 数据和本地逻辑实现。

非目标：登录、注册、会员、订阅、支付、真实后端、竞品 API、真实账户，以及任何外部副作用。

## 3. 信息架构与功能流程

{architecture}

## 4. 功能说明

{function_sections}

## 5. 页面说明

页面视觉采用以下可编辑的参考结论，并使用原创资产实现：

{notes}

页面、导航和信息层级以各功能的“涉及页面”和“流程”为准；未由证据确认的内容必须在实现前补充产品决策。

## 6. 特殊设备能力与页面状态

设备能力仅在静态或动态证据支持时纳入实现；涉及权限时应在隔离模拟器中验证，并向最终用户说明授权原因。

应覆盖的通用页面状态：空态、加载态、成功态和失败态。Flutter 参考原型提供本地可演示状态，不连接真实服务。

## 7. 验收标准

1. Flutter 原型可打开已确认页面，核心本地流程可走通。
2. 组件与视觉决策一致，且全部为原创品牌、图标、文案、图片和 Mock 数据。
3. 鉴权、会员和支付逻辑未被生成。
4. 每项功能的验收标准在产品方案层中可追溯；`unconfirmed` 项不得被表述为已验证事实。
'''


def update_changelog(path: Path, version: str) -> None:
    entry = f"## {version}\n\n- 已从确认的产品方案生成 `PRD.md`。\n"
    existing = path.read_text(encoding="utf-8") if path.exists() else "# Change log\n\n"
    if f"## {version}\n" not in existing:
        path.write_text(existing + entry, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--force", action="store_true", help="Replace an existing docs/PRD.md")
    arguments = parser.parse_args()
    output_dir = arguments.output.expanduser().resolve()
    prd_path = output_dir / "docs" / "PRD.md"
    if prd_path.exists() and not arguments.force:
        print("PRD already exists. Pass --force to regenerate it.", file=sys.stderr)
        return 2
    try:
        model = load_model(output_dir)
        errors = validation_errors(model, require_confirmation=True)
        if errors:
            raise ValueError("; ".join(errors))
        if model["generation"].get("approved_model_fingerprint") != approval_fingerprint(model):
            raise ValueError("Product decisions changed after confirmation; confirm a new model version before generating the PRD.")
        prd_path.parent.mkdir(parents=True, exist_ok=True)
        prd_path.write_text(build_prd(model), encoding="utf-8")
        version = model["generation"]["approved_model_version"]
        update_changelog(output_dir / "docs" / "CHANGELOG.md", version)
        model["generation"]["prd_status"] = "generated"
        append_audit(model, "prd_generated", {"path": "docs/PRD.md", "version": version})
        write_json(output_dir / "project-model.json", model)
    except (OSError, ValueError) as error:
        print(f"PRD generation failed: {error}", file=sys.stderr)
        return 2
    print(prd_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
