#!/usr/bin/env python3
"""Generate an extended performance report with weekly/monthly breakdowns."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

try:  # pragma: no cover
    import pdfkit
except Exception:  # noqa: BLE001
    pdfkit = None  # type: ignore[assignment]

DEFAULT_SUMMARY = Path("reports") / "latest" / "backtest_summary.json"
DEFAULT_SIGNALS = Path("artifacts") / "signals.csv"
DEFAULT_OUTPUT = Path("reports") / "latest" / "performance_report.html"


def _load_summary(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Summary file not found: {path}")
    return json.loads(path.read_text())


def _load_signals(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Signals file not found: {path}")
    df = pd.read_csv(path)
    if df.empty:
        raise ValueError("Signals file is empty.")
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["instrument"] = df["instrument"].astype(str)
    df["action"] = df.get("action", "buy").astype(str).str.lower()
    df["weight"] = pd.to_numeric(df.get("weight", 0.0), errors="coerce").fillna(0.0)
    df["score"] = pd.to_numeric(df.get("score", 0.0), errors="coerce").fillna(0.0)
    return df


def _daily_df(summary: dict) -> pd.DataFrame:
    daily = summary.get("daily_returns") or []
    if not isinstance(daily, list) or not daily:
        return pd.DataFrame(columns=["date", "value"])
    df = pd.DataFrame(daily)
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce").fillna(0.0)
    return df


def _weekly_returns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    weekly = df.copy()
    weekly["week"] = weekly["date"].dt.to_period("W").astype(str)
    weekly_grouped = weekly.groupby("week")["value"].sum().reset_index()
    weekly_grouped["cum"] = weekly_grouped["value"].cumsum()
    return weekly_grouped


def _monthly_returns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    monthly = df.copy()
    monthly["month"] = monthly["date"].dt.to_period("M").astype(str)
    return monthly.groupby("month")["value"].sum().reset_index()


def _instrument_summary(signals: pd.DataFrame) -> pd.DataFrame:
    grouped = signals.groupby("instrument").agg(
        signals=("instrument", "count"),
        long_signals=("action", lambda x: (x != "sell").sum()),
        short_signals=("action", lambda x: (x == "sell").sum()),
        avg_weight=("weight", "mean"),
        avg_score=("score", "mean"),
    )
    grouped = grouped.sort_values("signals", ascending=False)
    return grouped.reset_index()


def _render_table(df: pd.DataFrame, headers: List[str]) -> str:
    if df.empty:
        return "<p>暂无数据 / No data available.</p>"
    rows = []
    for row in df.itertuples(index=False):
        cells = "".join(f"<td>{getattr(row, col)}</td>" for col in df.columns)
        rows.append(f"<tr>{cells}</tr>")
    header_html = "".join(f"<th>{name}</th>" for name in headers)
    return f"""
<table>
  <thead><tr>{header_html}</tr></thead>
  <tbody>
    {''.join(rows)}
  </tbody>
</table>
"""


def _render_html(
    summary: dict,
    signals: pd.DataFrame,
    daily: pd.DataFrame,
    weekly: pd.DataFrame,
    monthly: pd.DataFrame,
    detail_link: Optional[str],
    summary_link: Optional[str],
) -> str:
    headline = f"""
<ul>
  <li><strong>总收益 Total Return:</strong> {summary.get('total_return', 0):.4f}</li>
  <li><strong>年化收益 Annualized:</strong> {summary.get('annualized_return', 0):.4f}</li>
  <li><strong>夏普比率 Sharpe:</strong> {summary.get('sharpe_ratio', 0):.4f}</li>
  <li><strong>最大回撤 Max Drawdown:</strong> {summary.get('max_drawdown', 0):.4f}</li>
  <li><strong>信号条数 Signals:</strong> {summary.get('total_signals', 0)}</li>
</ul>
"""
    weekly_table = _render_table(weekly.head(10), ["week", "value", "cum"]) if not weekly.empty else "<p>暂无周度数据</p>"
    monthly_table = _render_table(monthly, ["month", "value"]) if not monthly.empty else "<p>暂无月度数据</p>"
    instrument_table = _render_table(
        _instrument_summary(signals).head(20),
        ["instrument", "signals", "long_signals", "short_signals", "avg_weight", "avg_score"],
    )

    detail_anchor = f'<a href="{detail_link}">交易明细 / Trade Details</a>' if detail_link else ""
    summary_anchor = f'<a href="{summary_link}">摘要页面 / Summary Page</a>' if summary_link else ""

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Hikyuu × Qlib Performance Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem; }}
    table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
    th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.6rem; text-align: right; }}
    th {{ background: #f5f5f5; }}
    td:first-child, th:first-child {{ text-align: left; }}
  </style>
</head>
<body>
  <h1>策略复盘报告 Performance Report</h1>
  <p>{summary_anchor} {detail_anchor}</p>
  <h2>核心指标 Highlights</h2>
  {headline}
  <h2>周度收益 Weekly Returns (Top 10)</h2>
  {weekly_table}
  <h2>月度收益 Monthly Returns</h2>
  {monthly_table}
  <h2>信号统计 Signal Breakdown (Top 20)</h2>
  {instrument_table}
</body>
</html>
"""


def run(
    summary_path: Path,
    signals_path: Path,
    output_path: Path,
    detail_link: Optional[str] = None,
    summary_link: Optional[str] = None,
) -> None:
    summary = _load_summary(summary_path)
    signals = _load_signals(signals_path)
    daily = _daily_df(summary)
    weekly = _weekly_returns(daily)
    monthly = _monthly_returns(daily)

    html = _render_html(summary, signals, daily, weekly, monthly, detail_link, summary_link)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"[generate-report] wrote {output_path}")
    if pdfkit is not None:
        try:  # pragma: no cover - pdf export optional
            pdfkit.from_string(html, str(output_path.with_suffix(".pdf")))
            print(f"[generate-report] wrote {output_path.with_suffix('.pdf')}")
        except Exception as exc:
            print(f"[generate-report] pdf export failed: {exc}")

    stem = output_path.stem
    suffix = output_path.suffix or ".html"
    weekly_output = output_path.with_name(f"{stem}_weekly{suffix}")
    monthly_output = output_path.with_name(f"{stem}_monthly{suffix}")
    weekly_table = _render_table(weekly, ["week", "value", "cum"]) if not weekly.empty else "<p>暂无周度数据</p>"
    monthly_table = _render_table(monthly, ["month", "value"]) if not monthly.empty else "<p>暂无月度数据</p>"

    aggregate_template = """<html><head><meta charset="utf-8" /><title>{title}</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 2rem; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.6rem; text-align: right; }}
th {{ background: #f5f5f5; }}
td:first-child, th:first-child {{ text-align: left; }}
</style>
</head>
<body>
  <h1>{title}</h1>
  <p>{links}</p>
  {table}
</body>
</html>
"""
    links_html = " ".join(
        filter(
            None,
            [
                f'<a href="{summary_link}">摘要页面 / Summary Page</a>' if summary_link else "",
                f'<a href="{detail_link}">交易明细 / Trade Details</a>' if detail_link else "",
            ],
        )
    )
    weekly_html = aggregate_template.format(title="周度收益 Weekly Returns", links=links_html, table=weekly_table)
    weekly_output.write_text(weekly_html, encoding="utf-8")
    print(f"[generate-report] wrote {weekly_output}")
    if pdfkit is not None:
        try:
            pdfkit.from_string(weekly_html, str(weekly_output.with_suffix(".pdf")))
            print(f"[generate-report] wrote {weekly_output.with_suffix('.pdf')}")
        except Exception as exc:
            print(f"[generate-report] weekly pdf export failed: {exc}")

    monthly_html = aggregate_template.format(title="月度收益 Monthly Returns", links=links_html, table=monthly_table)
    monthly_output.write_text(monthly_html, encoding="utf-8")
    print(f"[generate-report] wrote {monthly_output}")
    if pdfkit is not None:
        try:
            pdfkit.from_string(monthly_html, str(monthly_output.with_suffix(".pdf")))
            print(f"[generate-report] wrote {monthly_output.with_suffix('.pdf')}")
        except Exception as exc:
            print(f"[generate-report] monthly pdf export failed: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate extended performance report.")
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--signals", type=Path, default=DEFAULT_SIGNALS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--detail-link", type=str)
    parser.add_argument("--summary-link", type=str)
    args = parser.parse_args()
    run(args.summary, args.signals, args.output, args.detail_link, args.summary_link)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
