#!/usr/bin/env python3
"""Verify that AppLens can perform a full, non-degraded static analysis."""

from __future__ import annotations

import sys
import argparse
from pathlib import Path

from analysis_toolchain import ToolchainError, require_full_toolchain


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Analysis output directory containing a provisioned toolchain receipt")
    arguments = parser.parse_args()
    try:
        tools = require_full_toolchain(arguments.output.expanduser().resolve() if arguments.output else None)
    except ToolchainError as error:
        print(f"AppLens toolchain check failed: {error}", file=sys.stderr)
        return 2
    print(f"AppLens full-analysis toolchain ready: aapt={tools['aapt']}; jadx={tools['jadx']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
