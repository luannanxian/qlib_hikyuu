#!/usr/bin/env python3
"""Placeholder data preparation script."""

from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_OUTPUT = Path("data") / "prepared_dataset.txt"


def run(output: Path = DEFAULT_OUTPUT) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "Placeholder dataset. Replace with real Hikyuu extraction logic.\n"
    )
    print(f"[prepare-data] wrote {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare placeholder dataset")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    run(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
