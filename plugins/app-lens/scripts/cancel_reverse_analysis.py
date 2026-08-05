#!/usr/bin/env python3
"""Request safe cancellation of a running AppLens reverse-static analysis."""

from __future__ import annotations

import argparse
from pathlib import Path

from model_tools import utc_now, working_root, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="Analysis output directory")
    arguments = parser.parse_args()
    output_dir = arguments.output.expanduser().resolve()
    request_path = working_root(output_dir) / "reverse-cancel-request.json"
    write_json(request_path, {"requested_at": utc_now(), "scope": "reverse_static_only"})
    print(request_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
