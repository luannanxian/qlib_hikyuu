#!/usr/bin/env python3
"""
Stub data preparation script for the Hikyuu × Qlib workstation.

In MVP stage this script emulates the data extraction workflow by generating a
placeholder dataset artifact. Later it will be replaced with real
HikyuuDataLoader logic.
"""

from __future__ import annotations

import argparse
from pathlib import Path

DATA_DIR = Path("data")
ARTIFACT = DATA_DIR / "prepared_dataset.txt"


def run(output: Path = ARTIFACT) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "Placeholder dataset generated.\n"
        "Replace scripts/prepare_data.py with actual Hikyuu integration.\n"
    )
    print(f"[prepare-data] wrote placeholder artifact: {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare dataset placeholder.")
    parser.add_argument(
        "--output",
        type=Path,
        default=ARTIFACT,
        help="Path to write the placeholder dataset artifact.",
    )
    args = parser.parse_args()
    run(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

