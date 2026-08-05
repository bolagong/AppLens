#!/usr/bin/env python3
"""Validate a project model before generation or publication."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from model_tools import load_json, validation_errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", type=Path, help="Path to project-model.json")
    parser.add_argument("--require-confirmation", action="store_true")
    arguments = parser.parse_args()
    try:
        model = load_json(arguments.model.expanduser().resolve())
        if not isinstance(model, dict):
            raise ValueError("Model must be an object.")
        errors = validation_errors(model, arguments.require_confirmation)
    except (OSError, ValueError) as error:
        print(f"Invalid model: {error}", file=sys.stderr)
        return 2
    if errors:
        print("Model validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 2
    print("Model validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
