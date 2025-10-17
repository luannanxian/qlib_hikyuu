#!/usr/bin/env python3
"""Generate signal CSV from prediction artifact."""

from __future__ import annotations

import argparse
import csv
import pickle
from collections import defaultdict
from typing import Iterable, List, Optional
from pathlib import Path

try:
    import pandas as pd  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - fallback when pandas missing/broken
    pd = None  # type: ignore[assignment]

DEFAULT_PRED_PATH = Path("experiments") / "latest" / "pred.pkl"
DEFAULT_OUTPUT_PATH = Path("artifacts") / "signals.csv"


def _iter_rows(raw: object) -> Iterable[dict]:
    dataframe_cls = getattr(pd, "DataFrame", None) if pd is not None else None
    if dataframe_cls is not None and isinstance(raw, dataframe_cls):
        return raw.reset_index().to_dict("records")
    if isinstance(raw, list):
        return raw
    raise TypeError("Unsupported prediction payload format; expected DataFrame or list of dicts.")


def _normalise_row(row: dict) -> Optional[dict]:
    datetime_value = row.get("datetime")
    instrument = row.get("instrument")
    score = row.get("score")
    if datetime_value is None or instrument is None or score is None:
        return None
    try:
        score_value = float(score)
    except (TypeError, ValueError):
        return None
    return {
        "datetime": str(datetime_value),
        "instrument": str(instrument),
        "score": score_value,
    }


def _select_signals(
    items: List[dict],
    top_k_buy: int,
    top_k_sell: Optional[int],
) -> List[dict]:
    if not items:
        return []

    buys = [item for item in items if item["score"] >= 0]
    sells = [item for item in items if item["score"] < 0]

    buys = sorted(buys, key=lambda x: x["score"], reverse=True)[: max(top_k_buy, 0)]
    sell_limit = top_k_sell if top_k_sell is not None else top_k_buy
    sells = sorted(sells, key=lambda x: x["score"])[: max(sell_limit, 0)]

    selected = [{"action": "buy", **item} for item in buys]
    selected += [{"action": "sell", **item} for item in sells]

    if not selected:
        return []

    total_score = sum(abs(item["score"]) for item in selected)
    if total_score <= 0:
        weight = 1.0 / len(selected)
        weights = [weight] * len(selected)
    else:
        weights = [abs(item["score"]) / total_score for item in selected]

    formatted = []
    for item, weight in zip(selected, weights):
        formatted.append(
            {
                "datetime": item["datetime"],
                "instrument": item["instrument"],
                "action": item["action"],
                "weight": round(weight, 4),
                "score": round(item["score"], 4),
            }
        )
    return formatted


def run(pred_path: Path, output_path: Path, top_k: int, top_k_sell: Optional[int] = None) -> None:
    if not pred_path.exists():
        raise FileNotFoundError(f"Prediction file not found: {pred_path}")
    with pred_path.open("rb") as fp:
        raw = pickle.load(fp)

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in _iter_rows(raw):
        normalised = _normalise_row(row)
        if normalised:
            grouped[normalised["datetime"]].append(normalised)

    signals = []
    for dt, items in grouped.items():
        selected = _select_signals(items, top_k, top_k_sell)
        signals.extend(selected)

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
    parser.add_argument("--top-k-sell", type=int, help="Number of sell signals per date (default same as top-k)")
    args = parser.parse_args()
    run(args.pred_path, args.output, args.top_k, top_k_sell=args.top_k_sell)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
