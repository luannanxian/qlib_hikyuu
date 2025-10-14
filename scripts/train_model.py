#!/usr/bin/env python3
"""Placeholder model training script."""

from __future__ import annotations

import argparse
import json
import pickle
import random
from datetime import date, timedelta
from pathlib import Path
from typing import List

EXPERIMENT_DIR = Path("experiments") / "latest"
PRED_PATH = EXPERIMENT_DIR / "pred.pkl"
METRICS_PATH = EXPERIMENT_DIR / "metrics.json"
DEFAULT_INSTRUMENTS: List[str] = [
    "SH600000",
    "SH600009",
    "SZ000001",
    "SZ000002",
]


def synthesize_predictions(days: int = 5) -> List[dict]:
    random.seed(2024)
    start = date.today() - timedelta(days=days)
    rows = []
    for i in range(days):
        dt = start + timedelta(days=i + 1)
        for inst in DEFAULT_INSTRUMENTS:
            rows.append(
                {
                    "datetime": dt.isoformat(),
                    "instrument": inst,
                    "score": random.uniform(-1, 1),
                }
            )
    return rows


def run(pred_path: Path = PRED_PATH, metrics_path: Path = METRICS_PATH) -> None:
    pred_path.parent.mkdir(parents=True, exist_ok=True)
    rows = synthesize_predictions()
    with pred_path.open("wb") as fp:
        pickle.dump(rows, fp)
    metrics = {
        "placeholder": True,
        "rows": len(rows),
        "instruments": sorted({row["instrument"] for row in rows}),
    }
    metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False))
    print(f"[train-model] wrote predictions to {pred_path}")
    print(f"[train-model] wrote metrics to {metrics_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Train placeholder model")
    parser.add_argument("--pred-path", type=Path, default=PRED_PATH)
    parser.add_argument("--metrics-path", type=Path, default=METRICS_PATH)
    args = parser.parse_args()
    run(args.pred_path, args.metrics_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
