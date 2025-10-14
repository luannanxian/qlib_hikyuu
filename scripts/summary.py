#!/usr/bin/env python3
"""Summarise experiment metrics into a compact table."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List


def collect_metrics(base: Path) -> List[dict]:
    if not base.exists():
        return []
    entries = []
    for path in base.rglob("metrics.json"):
        with path.open() as fp:
            data = json.load(fp)
        entries.append({
            "experiment": path.parent.name,
            "rows": data.get("rows", 0),
            "instruments": ",".join(data.get("instruments", [])),
        })
    return entries


def summarize(base: Path = Path("experiments")) -> None:
    metrics = collect_metrics(base)
    if not metrics:
        print("No experiments found.")
        return
    print("Experiment\tRows\tInstruments")
    for item in metrics:
        print(f"{item['experiment']}\t{item['rows']}\t{item['instruments']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarise experiment metrics.")
    parser.add_argument("--base", type=Path, default=Path("experiments"))
    args = parser.parse_args()

    summarize(args.base)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
