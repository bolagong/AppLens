#!/usr/bin/env python3
"""Generate the safe, human-readable AppLens evidence summary."""

from __future__ import annotations

import argparse
from pathlib import Path

from evidence_summary import write_evidence_summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="Analysis output directory")
    arguments = parser.parse_args()
    print(write_evidence_summary(arguments.output.expanduser().resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
