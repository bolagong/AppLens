"""Dependency-free regression tests for AppLens static fallback evidence."""

from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from evidence_signals import resource_signal_summary  # noqa: E402
from safe_explore import package_from_static_evidence  # noqa: E402
from static_inventory import NO_INDEX, TYPE_STRING, parse_binary_manifest  # noqa: E402


def _utf8_length(value: int) -> bytes:
    return bytes([value]) if value < 0x80 else bytes([0x80 | (value >> 8), value & 0xFF])


def _string_pool(strings: list[str]) -> bytes:
    offsets: list[int] = []
    content = bytearray()
    for value in strings:
        encoded = value.encode("utf-8")
        offsets.append(len(content))
        content.extend(_utf8_length(len(value)))
        content.extend(_utf8_length(len(encoded)))
        content.extend(encoded)
        content.append(0)
    header_size = 28
    strings_start = header_size + 4 * len(offsets)
    size = strings_start + len(content)
    return struct.pack("<HHIIIIII", 0x0001, header_size, size, len(strings), 0, 0x100, strings_start, 0) + struct.pack(
        f"<{len(offsets)}I", *offsets
    ) + content


def _start_element(element_index: int, attribute_name_index: int, value_index: int) -> bytes:
    header_size = 36
    size = header_size + 20
    header = struct.pack("<HHIII", 0x0102, header_size, size, 0, NO_INDEX)
    extension = struct.pack("<IIHHHHHH", NO_INDEX, element_index, 20, 20, 1, 0, 0, 0)
    attribute = struct.pack("<IIIHBBI", NO_INDEX, attribute_name_index, value_index, 8, 0, TYPE_STRING, value_index)
    return header + extension + attribute


def _manifest_fixture() -> bytes:
    strings = [
        "manifest",
        "package",
        "com.example.reference",
        "uses-permission",
        "name",
        "android.permission.CAMERA",
        "activity",
        "com.example.reference.MainActivity",
    ]
    chunks = b"".join(
        [
            _string_pool(strings),
            _start_element(0, 1, 2),
            _start_element(3, 4, 5),
            _start_element(6, 4, 7),
        ]
    )
    return struct.pack("<HHI", 0x0003, 8, 8 + len(chunks)) + chunks


class StaticFallbackTests(unittest.TestCase):
    def test_binary_manifest_yields_only_safe_metadata(self) -> None:
        metadata = parse_binary_manifest(_manifest_fixture())

        self.assertEqual(
            metadata,
            {
                "status": "parsed",
                "parser": "built_in_binary_manifest",
                "package_name": "com.example.reference",
                "permissions": ["android.permission.CAMERA"],
                "component_counts": {
                    "activity": 1,
                    "activity-alias": 0,
                    "provider": 0,
                    "receiver": 0,
                    "service": 0,
                },
            },
        )

    def test_resource_signals_scan_the_entire_archive_not_a_sample(self) -> None:
        paths = [f"res/drawable/alpha_{index:03d}.xml" for index in range(300)]
        paths.extend(["res/layout/search_results.xml", "assets/filter_state.json", "res/drawable/bitmap.xml"])

        self.assertEqual(
            resource_signal_summary(paths),
            [
                {"signal": "filter", "name": "Filter or sort", "matching_resource_count": 1, "resource_types": ["asset"]},
                {"signal": "search", "name": "Search", "matching_resource_count": 1, "resource_types": ["layout"]},
            ],
        )

    def test_dynamic_explorer_uses_the_package_from_safe_static_metadata(self) -> None:
        self.assertEqual(
            package_from_static_evidence(
                {
                    "manifest_metadata": {
                        "status": "parsed",
                        "package_name": "com.example.reference",
                    }
                }
            ),
            "com.example.reference",
        )
        self.assertIsNone(package_from_static_evidence({"manifest_metadata": {"status": "limited"}}))


if __name__ == "__main__":
    unittest.main()
