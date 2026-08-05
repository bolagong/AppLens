#!/usr/bin/env python3
"""Create a conservative local inventory for a user-provided APK."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import subprocess
import sys
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

from analysis_toolchain import ToolchainError, require_aapt
from evidence_signals import resource_signal_summary
from evidence_summary import write_evidence_summary
from model_tools import write_json


PERMISSION_SIGNAL_TERMS = {
    "android.permission.CAMERA": "Camera capture",
    "android.permission.ACCESS_FINE_LOCATION": "Location-aware experience",
    "android.permission.ACCESS_COARSE_LOCATION": "Location-aware experience",
    "android.permission.POST_NOTIFICATIONS": "Notification preferences",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command_output(command: list[str]) -> tuple[dict[str, Any], str]:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"available": False, "exit_code": None}, ""

    return {"available": True, "exit_code": result.returncode}, result.stdout


def inventory_zip(apk_path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(apk_path) as archive:
        names = archive.namelist()
        file_names = [name for name in names if not name.endswith("/")]
        suffixes = Counter(Path(name).suffix.lower() or "[none]" for name in file_names)
        resource_prefixes = Counter(name.split("/", 1)[0] for name in file_names)
        native_libraries = sorted(name for name in file_names if name.startswith("lib/"))
        dex_files = sorted(name for name in file_names if name.endswith(".dex"))

    architectures = sorted(
        {
            parts[1]
            for name in native_libraries
            if len(parts := name.split("/")) >= 3 and parts[0] == "lib"
        }
    )
    return {
        "archive_file_count": len(file_names),
        "top_level_paths": dict(sorted(resource_prefixes.items())),
        "file_extensions": dict(sorted(suffixes.items())),
        "dex_files": dex_files,
        "native_abis": architectures,
        "native_library_count": len(native_libraries),
        # Candidates must not be based on the arbitrary first 200 ZIP entries.
        # Store aggregate counts only, so the report remains safe to share locally.
        "resource_signal_summary": resource_signal_summary(file_names),
    }


RES_STRING_POOL_TYPE = 0x0001
RES_XML_START_ELEMENT_TYPE = 0x0102
NO_INDEX = 0xFFFFFFFF
TYPE_STRING = 0x03
COMPONENT_ELEMENTS = {"activity", "activity-alias", "provider", "receiver", "service"}


def _chunk_header(data: bytes, offset: int) -> tuple[int, int, int] | None:
    if offset < 0 or offset + 8 > len(data):
        return None
    chunk_type, header_size, size = struct.unpack_from("<HHI", data, offset)
    if header_size < 8 or size < header_size or offset + size > len(data):
        return None
    return chunk_type, header_size, size


def _length8(data: bytes, offset: int) -> tuple[int, int] | None:
    if offset >= len(data):
        return None
    value = data[offset]
    if value & 0x80:
        if offset + 1 >= len(data):
            return None
        return ((value & 0x7F) << 8) | data[offset + 1], offset + 2
    return value, offset + 1


def _length16(data: bytes, offset: int) -> tuple[int, int] | None:
    if offset + 2 > len(data):
        return None
    value = struct.unpack_from("<H", data, offset)[0]
    if value & 0x8000:
        if offset + 4 > len(data):
            return None
        return ((value & 0x7FFF) << 16) | struct.unpack_from("<H", data, offset + 2)[0], offset + 4
    return value, offset + 2


def _string_pool(data: bytes, offset: int, header_size: int, size: int) -> list[str] | None:
    """Read an Android StringPool; only used for Manifest metadata."""
    if header_size < 28 or offset + header_size > len(data):
        return None
    string_count, _style_count, flags, strings_start, _styles_start = struct.unpack_from("<IIIII", data, offset + 8)
    offsets_start = offset + header_size
    if string_count > 100_000 or offsets_start + string_count * 4 > offset + size:
        return None
    strings_base = offset + strings_start
    if strings_base < offset or strings_base > offset + size:
        return None
    utf8 = bool(flags & 0x100)
    values: list[str] = []
    for index in range(string_count):
        relative = struct.unpack_from("<I", data, offsets_start + index * 4)[0]
        position = strings_base + relative
        if position >= offset + size:
            return None
        if utf8:
            chars = _length8(data, position)
            if chars is None:
                return None
            _char_count, position = chars
            byte_length = _length8(data, position)
            if byte_length is None:
                return None
            length, position = byte_length
            end = position + length
            if end >= offset + size:
                return None
            values.append(data[position:end].decode("utf-8", errors="replace"))
        else:
            units = _length16(data, position)
            if units is None:
                return None
            length, position = units
            end = position + length * 2
            if end + 2 > offset + size:
                return None
            values.append(data[position:end].decode("utf-16le", errors="replace"))
    return values


def _value_string(strings: list[str], raw_value: int, data_type: int, data_value: int) -> str | None:
    index = raw_value if raw_value != NO_INDEX else (data_value if data_type == TYPE_STRING else NO_INDEX)
    return strings[index] if 0 <= index < len(strings) else None


def parse_binary_manifest(data: bytes) -> dict[str, Any] | None:
    """Parse only package, permission, and component-count metadata from AXML."""
    first_header = _chunk_header(data, 0)
    if not first_header:
        return None
    first_type, first_header_size, first_size = first_header
    if first_type != 0x0003:  # RES_XML_TYPE
        return None
    position = first_header_size
    end = first_size
    strings: list[str] | None = None
    package_name: str | None = None
    permissions: set[str] = set()
    components = {element: 0 for element in COMPONENT_ELEMENTS}

    while position < end:
        header = _chunk_header(data, position)
        if not header:
            return None
        chunk_type, header_size, size = header
        if chunk_type == RES_STRING_POOL_TYPE and strings is None:
            strings = _string_pool(data, position, header_size, size)
            if strings is None:
                return None
        elif chunk_type == RES_XML_START_ELEMENT_TYPE and strings is not None:
            # ResXMLTree_node (16 bytes) followed by ResXMLTree_attrExt (20 bytes).
            if header_size < 36 or position + 36 > position + size:
                return None
            _namespace, name_index, attributes_start, attribute_size, attribute_count, _id, _class, _style = struct.unpack_from(
                "<IIHHHHHH", data, position + 16
            )
            element = strings[name_index] if 0 <= name_index < len(strings) else ""
            if element in components:
                components[element] += 1
            attribute_offset = position + 16 + attributes_start
            if attribute_size < 20 or attribute_offset + attribute_count * attribute_size > position + size:
                return None
            for index in range(attribute_count):
                cursor = attribute_offset + index * attribute_size
                _attr_namespace, attr_name_index, raw_value, value_size, _res0, data_type, data_value = struct.unpack_from("<IIIHBBI", data, cursor)
                if value_size < 8:
                    return None
                attr_name = strings[attr_name_index] if 0 <= attr_name_index < len(strings) else ""
                value = _value_string(strings, raw_value, data_type, data_value)
                if not value:
                    continue
                if element == "manifest" and attr_name == "package":
                    package_name = value
                elif element.startswith("uses-permission") and attr_name == "name" and value.startswith("android.permission."):
                    permissions.add(value)
        position += size

    if strings is None:
        return None
    return {
        "status": "parsed",
        "parser": "built_in_binary_manifest",
        "package_name": package_name,
        "permissions": sorted(permissions),
        "component_counts": dict(sorted(components.items())),
    }


def manifest_metadata(apk_path: Path) -> dict[str, Any]:
    """Collect supplemental safe metadata; it never replaces the required aapt output."""
    try:
        with zipfile.ZipFile(apk_path) as archive:
            data = archive.read("AndroidManifest.xml")
    except (KeyError, OSError, zipfile.BadZipFile) as error:
        return {"status": "unavailable", "reason": f"AndroidManifest.xml could not be read: {error}"}

    parsed = parse_binary_manifest(data)
    if parsed:
        return parsed

    # APK manifests are normally binary XML. This guarded fallback supports a
    # plain-text fixture or unusual build without interpreting arbitrary strings.
    permissions = sorted(set(re.findall(r"android\.permission\.[A-Z0-9_]+", data.decode("utf-8", errors="ignore"))))
    return {
        "status": "limited",
        "parser": "permission_string_fallback",
        "permissions": permissions,
        "reason": "The built-in parser could not read the binary manifest structure.",
    }


def android_tool_evidence(apk_path: Path, aapt: str) -> dict[str, Any]:
    tool_name = Path(aapt).name
    if tool_name == "aapt2":
        commands = {
            "badging": [aapt, "dump", "badging", str(apk_path)],
            "permissions": [aapt, "dump", "permissions", str(apk_path)],
        }
    else:
        commands = {
            "badging": [aapt, "dump", "badging", str(apk_path)],
            "permissions": [aapt, "dump", "permissions", str(apk_path)],
        }

    evidence = {
        "tool_available": True,
        "tool": tool_name,
    }
    results: dict[str, dict[str, Any]] = {}
    raw_outputs: dict[str, str] = {}
    for name, command in commands.items():
        result, output = command_output(command)
        results[name] = result
        raw_outputs[name] = output
    evidence["results"] = results
    failures = [
        name
        for name, result in results.items()
        if not isinstance(result, dict) or result.get("exit_code") != 0
    ]
    if failures:
        raise RuntimeError(f"Required Android metadata extraction failed: {', '.join(failures)}")
    permission_names = sorted(
        set(re.findall(r"android\.permission\.[A-Z0-9_]+", raw_outputs.get("permissions", "")))
    )
    evidence["permission_summary"] = {
        "declared_permission_count": len(permission_names),
        "generic_signals": sorted(
            {signal for permission, signal in PERMISSION_SIGNAL_TERMS.items() if permission in permission_names}
        ),
    }
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Path to a user-provided .apk file")
    parser.add_argument("--output", required=True, type=Path, help="Analysis output directory")
    arguments = parser.parse_args()

    input_path = arguments.input.expanduser().resolve()
    output_dir = arguments.output.expanduser().resolve()
    if not input_path.is_file():
        parser.error(f"Input file does not exist: {input_path}")
    if input_path.suffix.lower() != ".apk":
        parser.error("Input must have a .apk extension.")

    try:
        # A full product analysis never silently substitutes this with a
        # resource-only fallback. Check before creating evidence artifacts.
        aapt = require_aapt(output_dir)
        report = {
            "schema_version": "1.0",
            "source": {
                "input_type": "apk",
                "input_sha256": sha256(input_path),
                "selected_apk_sha256": sha256(input_path),
            },
            "scope": {
                "purpose": "local static evidence inventory",
                "excluded": [
                    "API endpoints",
                    "credentials and tokens",
                    "backend implementation",
                    "decompiled source code",
                ],
            },
            "archive": inventory_zip(input_path),
            "manifest_metadata": manifest_metadata(input_path),
            "android_tool_evidence": android_tool_evidence(input_path, aapt),
        }
    except (OSError, ToolchainError, ValueError, zipfile.BadZipFile) as error:
        print(f"Inventory failed: {error}", file=sys.stderr)
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir = output_dir / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    report_path = evidence_dir / "static-inventory.json"
    write_json(report_path, report)
    write_evidence_summary(output_dir)
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
