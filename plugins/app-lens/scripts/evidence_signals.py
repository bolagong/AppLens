"""Shared, conservative product-signal rules for safe APK evidence."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import PurePosixPath
from typing import Any, Iterable


# These terms are deliberately narrow.  A hit records a reviewable hypothesis,
# not proof that the application exposes the corresponding user flow.
PRODUCT_SIGNAL_SPECS: dict[str, dict[str, Any]] = {
    "bookmark": {"name": "Save or bookmark", "terms": ("bookmark",)},
    "camera": {"name": "Camera capture", "terms": ("camera",)},
    "favorite": {"name": "Save or favorite", "terms": ("favorite", "favourite")},
    "filter": {"name": "Filter or sort", "terms": ("filter", "sort")},
    "location": {"name": "Location-aware experience", "terms": ("location",)},
    "map": {"name": "Map browsing", "terms": ("map",)},
    "notification": {"name": "Notification preferences", "terms": ("notification",)},
    "profile": {"name": "Profile area", "terms": ("profile",)},
    "search": {"name": "Search", "terms": ("search",)},
    "setting": {"name": "Settings", "terms": ("setting", "settings")},
    "share": {"name": "External sharing", "terms": ("share",)},
}


def _tokens(path: str) -> set[str]:
    """Return file-name tokens without retaining source strings or paths."""
    pure_path = PurePosixPath(path)
    stem = pure_path.stem
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", stem)
    return {
        token.lower()
        for token in re.split(r"[^A-Za-z0-9]+", normalized)
        if token
    }


def resource_signal_summary(resource_paths: Iterable[str]) -> list[dict[str, Any]]:
    """Summarize all safe resource-name hits without exposing raw resource names."""
    matches: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "types": set()})
    for path in resource_paths:
        if not isinstance(path, str) or not path.startswith(("res/", "assets/")):
            continue
        parts = path.split("/")
        resource_type = parts[1].split("-", 1)[0] if len(parts) > 2 and parts[0] == "res" else "asset"
        tokens = _tokens(path)
        for signal, spec in PRODUCT_SIGNAL_SPECS.items():
            if any(term in tokens for term in spec["terms"]):
                matches[signal]["count"] += 1
                matches[signal]["types"].add(resource_type)

    return [
        {
            "signal": signal,
            "name": PRODUCT_SIGNAL_SPECS[signal]["name"],
            "matching_resource_count": details["count"],
            "resource_types": sorted(details["types"]),
        }
        for signal, details in sorted(matches.items())
    ]
