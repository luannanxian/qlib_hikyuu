#!/usr/bin/env python3
"""Generate signal CSV from prediction artifact."""

from __future__ import annotations

import argparse
import csv
import pickle
from collections import defaultdict
from pathlib import Path

import pandas as pd

DEFAULT_PRED_PATH = Path("experiments") / "latest" / "pred.pkl"
DEFAULT_OUTPUT_PATH = Path("artifacts") / "signals.csv"


def run(pred_path: Path, output_path: Path, top_k: int) -> None:
    if not pred_path.exists():
        raise FileNotFoundError(f"Prediction file not found: {pred_path}")
    with pred_path.open("rb") as fp:
        raw = pickle.load(fp)

    grouped = defaultdict(list)
    if isinstance(raw, pd.DataFrame):
        df = raw.reset_index()
        for _, row in df.iterrows():
            grouped[str(row["datetime"])].append(
                {
                    "datetime": str(row["datetime"]),
                    "instrument": str(row["instrument"]),
                    "score": float(row["score"]),
                }
            )
    else:
        for row in raw:
            grouped[row["datetime"]].append(row)

    signals = []
    for dt, items in grouped.items():
        top_items = sorted(items, key=lambda x: x["score"], reverse=True)[:top_k]
        for item in top_items:
            signals.append(
                {
                    "datetime": dt,
                    "instrument": item["instrument"],
                    "action": "buy",
                    "weight": round(1.0 / top_k, 4),
                    "score": item["score"],
                }
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as fp:
        writer = csv.DictWriter(
            fp, fieldnames=["datetime", "instrument", "action", "weight", "score"]
        )
        writer.writeheader()
        writer.writerows(signals)
    print(f"[export-signals] wrote {len(signals)} rows to {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Export signals from predictions")
    parser.add_argument("--pred-path", type=Path, default=DEFAULT_PRED_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()
    run(args.pred_path, args.output, args.top_k)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
