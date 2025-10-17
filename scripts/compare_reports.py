#!/usr/bin/env python3
"""Compare two backtest summaries and highlight key metric deltas."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple


METRIC_KEYS = [
    "total_return",
    "annualized_return",
    "annualized_vol",
    "sharpe_ratio",
    "max_drawdown",
    "total_signals",
    "avg_gross_exposure",
]


def _load_summary(path: Path) -> Dict[str, float]:
    if not path.exists():
        raise FileNotFoundError(f"Summary file not found: {path}")
    return json.loads(path.read_text())


def _format_delta(before: float, after: float) -> str:
    diff = after - before
    sign = "+" if diff >= 0 else ""
    return f"{after:.6f} ({sign}{diff:.6f})"


def compare_summaries(before_path: Path, after_path: Path) -> List[Tuple[str, str]]:
    before = _load_summary(before_path)
    after = _load_summary(after_path)
    rows: List[Tuple[str, str]] = []
    for key in METRIC_KEYS:
        if key not in before or key not in after:
            continue
        before_val = float(before.get(key, 0.0))
        after_val = float(after.get(key, 0.0))
        rows.append((key, _format_delta(before_val, after_val)))
    return rows


def run(before: Path, after: Path, output: Path) -> None:
    rows = compare_summaries(before, after)
    lines = ["Metric,After (Δ)"] + [f"{metric},{delta}" for metric, delta in rows]
    output.write_text("\n".join(lines))
    print(f"[compare-reports] wrote comparison to {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two backtest summary JSON files.")
    parser.add_argument("before", type=Path)
    parser.add_argument("after", type=Path)
    parser.add_argument("--output", type=Path, default=Path("reports/latest/compare.csv"))
    args = parser.parse_args()
    run(args.before, args.after, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

