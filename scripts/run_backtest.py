#!/usr/bin/env python3
"""Aggregate signals and produce a summary report."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

DEFAULT_SIGNAL_PATH = Path("artifacts") / "signals.csv"
DEFAULT_REPORT_PATH = Path("reports") / "latest" / "backtest_summary.json"


def run(signal_path: Path, report_path: Path) -> None:
    if not signal_path.exists():
        raise FileNotFoundError(f"Signals file not found: {signal_path}")
    rows = []
    with signal_path.open() as fp:
        reader = csv.DictReader(fp)
        rows.extend(reader)

    dates = {row["datetime"] for row in rows}
    instruments = {row["instrument"] for row in rows}
    weights = [float(row["weight"]) for row in rows] if rows else []

    summary = {
        "total_signals": len(rows),
        "unique_dates": len(dates),
        "unique_instruments": len(instruments),
        "average_weight": sum(weights) / len(weights) if weights else 0.0,
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"[run-backtest] summary written to {report_path}")
    for key, value in summary.items():
        print(f"  - {key}: {value}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run placeholder backtest")
    parser.add_argument("--signals", type=Path, default=DEFAULT_SIGNAL_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()
    run(args.signals, args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
