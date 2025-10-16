#!/usr/bin/env python3
"""Collect monitoring metrics from summary/metrics files with simple threshold checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Optional

DEFAULT_SUMMARY = Path("reports") / "latest" / "backtest_summary.json"
DEFAULT_METRICS = Path("experiments") / "latest" / "metrics.json"
DEFAULT_OUTPUT = Path("reports") / "latest" / "monitoring.json"


def _load_json(path: Path) -> Dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # pragma: no cover
        raise ValueError(f"Failed to parse JSON from {path}: {exc}") from exc


def collect_metrics(
    summary_path: Path = DEFAULT_SUMMARY,
    metrics_path: Path = DEFAULT_METRICS,
    output_path: Optional[Path] = DEFAULT_OUTPUT,
    min_signals: Optional[int] = None,
    min_rows: Optional[int] = None,
    max_loss: Optional[float] = None,
) -> Dict[str, object]:
    summary = _load_json(summary_path)
    metrics = _load_json(metrics_path)

    signals = int(summary.get("total_signals", 0))
    unique_instruments = summary.get("unique_instruments") or []
    unique_dates = int(summary.get("unique_dates", 0))
    average_weight = summary.get("average_weight")

    rows = int(metrics.get("rows", 0))
    placeholder = bool(metrics.get("placeholder", False))
    loss = metrics.get("loss")
    if isinstance(loss, str):
        try:
            loss = float(loss)
        except ValueError:
            loss = None

    report = {
        "summary_path": str(summary_path),
        "metrics_path": str(metrics_path),
        "signals": signals,
        "unique_instruments": unique_instruments,
        "unique_dates": unique_dates,
        "average_weight": average_weight,
        "rows": rows,
        "placeholder": placeholder,
        "loss": loss,
        "violations": [],
    }

    if min_signals is not None and signals < min_signals:
        report["violations"].append({
            "type": "min_signals",
            "expected": min_signals,
            "actual": signals,
        })
    if min_rows is not None and rows < min_rows:
        report["violations"].append({
            "type": "min_rows",
            "expected": min_rows,
            "actual": rows,
        })
    if max_loss is not None and loss is not None and loss > max_loss:
        report["violations"].append({
            "type": "max_loss",
            "expected": max_loss,
            "actual": loss,
        })

    # Persist when requested
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect monitoring metrics and check thresholds")
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--min-signals", type=int)
    parser.add_argument("--min-rows", type=int)
    parser.add_argument("--max-loss", type=float)
    args = parser.parse_args()

    report = collect_metrics(
        summary_path=args.summary,
        metrics_path=args.metrics,
        output_path=args.output,
        min_signals=args.min_signals,
        min_rows=args.min_rows,
        max_loss=args.max_loss,
    )

    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["violations"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
