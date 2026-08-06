"""Render a safe, human-readable evidence delivery summary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from model_tools import load_json, utc_now, working_root, write_text


def read_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = load_json(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def list_item(value: str) -> str:
    return value.replace("\n", " ").strip()


def component_text(counts: Any) -> str:
    if not isinstance(counts, dict):
        return "未取得"
    items = [f"{key}: {value}" for key, value in sorted(counts.items()) if isinstance(value, int)]
    return "；".join(items) if items else "未取得"


def resource_signals(archive: Any) -> list[str]:
    if not isinstance(archive, dict):
        return []
    items = archive.get("resource_signal_summary", [])
    if not isinstance(items, list):
        return []
    signals: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name, count = item.get("name"), item.get("matching_resource_count")
        if isinstance(name, str) and isinstance(count, int):
            signals.append(f"{list_item(name)}（{count} 条聚合资源信号）")
    return signals


def dex_count(archive: dict[str, Any]) -> int | None:
    value = archive.get("dex_file_count")
    if isinstance(value, int) and value >= 0:
        return value
    # Read older evidence without preserving or emitting its raw filenames.
    legacy = archive.get("dex_files")
    if isinstance(legacy, list):
        return len(legacy)
    return None


def manifest_permission_count(manifest: dict[str, Any]) -> int | None:
    if manifest.get("status") != "parsed":
        return None
    permissions = manifest.get("permissions")
    return len(permissions) if isinstance(permissions, list) else None


def android_permission_count(android: dict[str, Any]) -> int | None:
    summary = android.get("permission_summary")
    if not isinstance(summary, dict):
        return None
    value = summary.get("declared_permission_count")
    return value if isinstance(value, int) and value >= 0 else None


def progress_line(progress: dict[str, Any] | None) -> str:
    prefix = "- 运行进度：`evidence/reverse-progress.json`"
    status = progress.get("status") if isinstance(progress, dict) else None
    if status == "running":
        return prefix + "；当前运行中，可使用 `scripts/cancel_reverse_analysis.py --output <输出目录>` 请求安全取消。"
    if status == "completed":
        return prefix + "；当前状态：已完成。"
    if status in {"failed", "cancelled"}:
        return prefix + f"；当前状态：{status}。"
    return prefix + "；当前状态未取得。"


def reverse_summary(reverse: dict[str, Any] | None, legacy_working_data: bool = False) -> tuple[str, list[str]]:
    if reverse is None:
        if legacy_working_data:
            return "未完成", ["检测到旧版运行留下的未完成工作数据，但没有安全的失败证据记录；未生成模型、原型或 PRD。"]
        return "未运行", ["受限 UI 结构分析尚未产生证据。"]
    status = reverse.get("status")
    if status == "completed":
        structure = reverse.get("ui_structure", {})
        lines = [f"UI 角色计数：{component_text(structure.get('component_counts') if isinstance(structure, dict) else {})}"]
        signals = structure.get("product_signals", []) if isinstance(structure, dict) else []
        names = [item.get("name") for item in signals if isinstance(item, dict) and isinstance(item.get("name"), str)]
        lines.append("通用产品信号（`static_inference`）：" + ("；".join(sorted(names)) if names else "未发现"))
        return "已完成", lines
    failure = reverse.get("failure", {})
    reason = failure.get("reason") if isinstance(failure, dict) else None
    timeout = failure.get("timeout_seconds") if isinstance(failure, dict) else None
    details = "受限 UI 结构分析失败，未生成模型、原型或 PRD。"
    if reason == "timeout" and isinstance(timeout, int):
        details = f"受限 UI 结构分析超过 {timeout} 秒上限，未生成模型、原型或 PRD。"
    elif reason == "cancelled":
        details = "受限 UI 结构分析已取消，未生成模型、原型或 PRD。"
    return "未完成", [details]


def render_evidence_summary(output_dir: Path) -> str:
    evidence_dir = output_dir / "evidence"
    run_brief = read_object(evidence_dir / "run-brief.json")
    toolchain = read_object(evidence_dir / "toolchain.json")
    static = read_object(evidence_dir / "static-inventory.json")
    reverse = read_object(evidence_dir / "reverse-static.json")
    progress = read_object(evidence_dir / "reverse-progress.json")
    reverse_status, reverse_lines = reverse_summary(
        reverse,
        legacy_working_data=(output_dir / "evidence" / "reverse-decompiled").exists(),
    )

    if static is None:
        overall_status = "未完成"
    elif reverse is not None and reverse.get("status") == "completed":
        overall_status = "已完成"
    else:
        overall_status = "部分完成"

    lines = [
        "# AppLens 证据摘要",
        "",
        f"- 生成时间：{utc_now()}",
        f"- 交付状态：**{overall_status}**",
        "- 内容边界：仅包含聚合统计、标准权限信号和通用 UI 信号；不包含反编译源码、资源路径、原始 AAPT 输出、接口或凭据。",
        "",
        "## 执行状态",
        "",
        f"- 运行配置：{'已记录' if run_brief else '未记录'}",
        f"- 工具链：{'已校验' if toolchain else '未记录'}",
        f"- 基础静态清单：{'已完成' if static else '未完成'}",
        f"- 受限 UI 结构分析：{reverse_status}",
        *[f"- {line}" for line in reverse_lines],
        "",
        "## 基础静态证据",
        "",
        "- 结论置信度：`static_inference`；所有聚合信号都需要产品负责人复核。",
    ]
    if static is None:
        lines.append("基础静态清单尚不可用。")
    else:
        archive = static.get("archive", {})
        manifest = static.get("manifest_metadata", {})
        android = static.get("android_tool_evidence", {})
        if isinstance(archive, dict):
            dex_files = dex_count(archive)
            lines.extend(
                [
                    f"- 归档文件数：{archive.get('archive_file_count', '未取得')}",
                    f"- DEX 文件数：{dex_files if dex_files is not None else '未取得'}",
                    f"- 原生 ABI 数：{len(archive.get('native_abis', [])) if isinstance(archive.get('native_abis'), list) else '未取得'}",
                    f"- 原生库数：{archive.get('native_library_count', '未取得')}",
                ]
            )
            signals = resource_signals(archive)
            lines.append("- 聚合资源信号：" + ("；".join(signals) if signals else "未发现"))
        if isinstance(manifest, dict):
            manifest_count = manifest_permission_count(manifest)
            lines.extend(
                [
                    f"- Manifest 解析状态：{manifest.get('status', '未取得')}",
                    f"- Manifest 声明权限数：{manifest_count if manifest_count is not None else '未取得'}",
                    f"- Manifest 组件计数：{component_text(manifest.get('component_counts'))}",
                ]
            )
        if isinstance(android, dict):
            permission_summary = android.get("permission_summary", {})
            if isinstance(permission_summary, dict):
                aapt_count = android_permission_count(android)
                if aapt_count is not None:
                    lines.append(f"- AAPT2 聚合声明权限数：{aapt_count}")
                signals = permission_summary.get("generic_signals", [])
                lines.append("- Android 工具通用权限信号：" + ("；".join(signals) if isinstance(signals, list) and signals else "未发现"))

    lines.extend(
        [
            "",
            "## 交付物与临时数据",
            "",
            "- 可读摘要：`docs/EVIDENCE_SUMMARY.md`",
            "- 机器证据：`evidence/` 中的 JSON 文件",
            "- 工具缓存：`.applens/toolchain/`（不属于交付结果）",
            "- 临时工作数据：`.applens/work/`（不属于交付结果，默认保留 24 小时）",
            progress_line(progress),
            "- 清理候选：运行 `scripts/cleanup_working_data.py --output <输出目录>` 查看；仅在加上 `--confirm-delete` 后删除超过 24 小时的临时数据。",
        ]
    )
    if working_root(output_dir).exists():
        lines.append("- 当前临时工作区：已创建。")
    if (output_dir / "evidence" / "reverse-decompiled").exists():
        lines.append("- 旧版临时工作区：`evidence/reverse-decompiled/`；清理命令也会将其作为候选，但不会自动删除。")
    lines.append("")
    return "\n".join(lines)


def write_evidence_summary(output_dir: Path) -> Path:
    summary_path = output_dir / "docs" / "EVIDENCE_SUMMARY.md"
    write_text(summary_path, render_evidence_summary(output_dir))
    return summary_path
