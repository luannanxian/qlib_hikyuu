#!/usr/bin/env python3
"""CLI 工具：汇总调仓信号并输出终端摘要。"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Tuple

import pandas as pd

DEFAULT_SIGNALS = Path("artifacts") / "signals.csv"


def _load(signals_path: Path) -> pd.DataFrame:
    if not signals_path.exists():
        raise FileNotFoundError(f"signals file missing: {signals_path}")
    df = pd.read_csv(signals_path)
    if "score" in df.columns:
        df["score"] = pd.to_numeric(df["score"], errors="coerce")
    if "weight" in df.columns:
        df["weight"] = pd.to_numeric(df["weight"], errors="coerce")
    return df


def _format_table(df: pd.DataFrame, columns: Tuple[str, ...]) -> str:
    col_widths = {
        col: max(len(col), *(len(str(val)) for val in df[col].astype(str)))
        for col in columns
    }
    header = " | ".join(col.ljust(col_widths[col]) for col in columns)
    separator = "-+-".join("-" * col_widths[col] for col in columns)
    rows: List[str] = []
    for _, row in df.iterrows():
        rows.append(" | ".join(str(row[col]).ljust(col_widths[col]) for col in columns))
    return "\n".join([header, separator, *rows])


def summarize(signals_path: Path, top: int, by_date: bool) -> None:
    df = _load(signals_path)
    total = len(df)
    unique_instruments = df["instrument"].nunique() if "instrument" in df.columns else 0
    actions = df.groupby("action").size().sort_values(ascending=False) if "action" in df.columns else pd.Series(dtype=int)

    print(f"signals: {total}")
    print(f"unique instruments: {unique_instruments}")
    if not actions.empty:
        print("actions breakdown:")
        for action, count in actions.items():
            pct = count / total * 100 if total else 0.0
            print(f"  - {action}: {count} ({pct:.1f}%)")

    if by_date and "datetime" in df.columns:
        grouped = (
            df.groupby("datetime")
            .agg(signals=("instrument", "count"), avg_score=("score", "mean"))
            .sort_index()
        )
        print("\nper-date summary:")
        print(_format_table(grouped.reset_index(), ("datetime", "signals", "avg_score")))

    if top > 0 and "score" in df.columns:
        top_df = df.sort_values("score", ascending=False).head(top)
        print(f"\ntop {top} signals by score:")
        columns = tuple(col for col in ("datetime", "instrument", "score", "action", "weight") if col in top_df.columns)
        print(_format_table(top_df.reset_index(drop=True), columns))


def main() -> int:
    parser = argparse.ArgumentParser(description="Preview signals and output summary statistics.")
    parser.add_argument("--signals", type=Path, default=DEFAULT_SIGNALS)
    parser.add_argument("--top", type=int, default=5, help="展示得分最高的前 N 条")
    parser.add_argument("--by-date", action="store_true", help="按日期输出聚合结果")
    args = parser.parse_args()

    summarize(args.signals, args.top, args.by_date)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
