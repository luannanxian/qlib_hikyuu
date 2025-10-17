#!/usr/bin/env python3
"""Render summary & detail HTML reports for backtest results."""

from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Optional

import pandas as pd

DEFAULT_SIGNALS = Path("artifacts") / "signals.csv"
DEFAULT_SUMMARY = Path("reports") / "latest" / "backtest_summary.json"
DEFAULT_OUTPUT = Path("reports") / "latest" / "review.html"
DEFAULT_DETAIL_OUTPUT = Path("reports") / "latest" / "review_detail.html"

try:  # pragma: no cover - optional dependency
    import plotly.graph_objects as go
    _PLOTLY_IMPORT_ERROR: Optional[Exception] = None
except Exception as exc:  # pragma: no cover
    go = None
    _PLOTLY_IMPORT_ERROR = exc


def _require_plotly() -> None:
    if go is None:
        raise RuntimeError(
            "Plotly 未安装或导入失败，请先执行 `pip install plotly`，并确保 requirements.txt 中包含 plotly。"
            f" 原始错误: {_PLOTLY_IMPORT_ERROR}"
        )


def load_signals(path: Path) -> list[dict]:
    if not path.exists():
        print(f"[render-report] signals file missing: {path}")
        return []
    with path.open() as fp:
        reader = csv.DictReader(fp)
        return list(reader)


def load_summary(path: Path) -> dict:
    if not path.exists():
        print(f"[render-report] summary file missing: {path}")
        return {}
    return json.loads(path.read_text())


def _build_chart(signals: list[dict]) -> Optional[str]:
    if not signals:
        return None
    _require_plotly()
    try:
        df = pd.DataFrame(signals)
    except Exception:  # pragma: no cover - fallback
        return None

    if "score" not in df or "instrument" not in df:
        return None

    df["score"] = pd.to_numeric(df["score"], errors="coerce")
    df = df.dropna(subset=["score"]).sort_values("score", ascending=False).head(20)
    if df.empty:
        return None

    fig = go.Figure(
        go.Bar(
            x=df["score"],
            y=df["instrument"],
            text=df.get("datetime"),
            orientation="h",
        )
    )
    fig.update_layout(
        title="Top Signals by Score",
        xaxis_title="Score",
        yaxis_title="Instrument",
        height=500,
        margin=dict(l=80, r=20, t=40, b=40),
    )
    html = fig.to_html(full_html=False, include_plotlyjs="cdn")
    return html


def _build_returns_chart(summary: dict) -> Optional[str]:
    strategy_series = summary.get("cumulative_returns") or []
    if not isinstance(strategy_series, list) or not strategy_series:
        return None
    _require_plotly()

    def _extract(series: list[dict]) -> tuple[list[str], list[float]]:
        dates = []
        values = []
        for item in series:
            date = item.get("date")
            value = item.get("value")
            if date is None or value is None:
                continue
            dates.append(str(date))
            try:
                values.append(float(value))
            except (TypeError, ValueError):
                values.append(0.0)
        return dates, values

    bench_series = summary.get("benchmark_cumulative_returns") or []
    strategy_dates, strategy_values = _extract(strategy_series)
    benchmark_dates, benchmark_values = _extract(bench_series if isinstance(bench_series, list) else [])

    fig = go.Figure()
    if strategy_dates:
        fig.add_trace(
            go.Scatter(
                x=strategy_dates,
                y=strategy_values,
                mode="lines",
                name="策略累计收益 Strategy",
            )
        )
    if benchmark_dates:
        benchmark_name = summary.get("benchmark_symbol") or "Benchmark"
        fig.add_trace(
            go.Scatter(
                x=benchmark_dates,
                y=benchmark_values,
                mode="lines",
                name=f"基准累计收益 {benchmark_name}",
                line=dict(dash="dash"),
            )
        )
    if not fig.data:
        return None
    fig.update_layout(
        title="收益曲线 / Return Curve",
        xaxis_title="日期 Date",
        yaxis_title="累计收益 Cumulative Return",
        height=480,
        legend=dict(orientation="h", y=-0.2),
        margin=dict(l=60, r=20, t=60, b=70),
    )
    return fig.to_html(full_html=False, include_plotlyjs="cdn")


def _summary_labels() -> dict:
    return {
        "total_signals": "信号总数 / Total Signals",
        "unique_dates": "交易日期数 / Trading Days",
        "unique_instrument_count": "标的数量 / Instruments",
        "long_signals": "多头信号数 / Long Signals",
        "short_signals": "空头信号数 / Short Signals",
        "avg_long_exposure": "平均多头仓位 / Avg Long Exposure",
        "avg_short_exposure": "平均空头仓位 / Avg Short Exposure",
        "avg_gross_exposure": "平均总仓位 / Avg Gross Exposure",
        "avg_net_exposure": "平均净仓位 / Avg Net Exposure",
        "long_exposure": "累计多头仓位 / Cumulative Long Exposure",
        "short_exposure": "累计空头仓位 / Cumulative Short Exposure",
        "average_weight": "平均权重 / Average Weight",
        "total_return": "总收益 / Total Return",
        "annualized_return": "年化收益 / Annualized Return",
        "annualized_vol": "年化波动 / Annualized Volatility",
        "sharpe_ratio": "夏普比率 / Sharpe Ratio",
        "max_drawdown": "最大回撤 / Max Drawdown",
        "benchmark_symbol": "基准指数 / Benchmark Symbol",
    }


def _render_summary_html(
    summary: dict,
    signals: list[dict],
    detail_href: str,
) -> str:
    summary_labels = _summary_labels()
    display_items = [
        (key, summary_labels.get(key, key), value)
        for key, value in summary.items()
        if isinstance(value, (int, float, str))
    ]
    metrics_html = "".join(
        f"<li><strong>{label}</strong>: {value}</li>"
        for key, label, value in display_items
    ) or "<li>暂无摘要指标 / No summary metrics.</li>"

    chart_html = _build_chart(signals)
    score_chart_section = (
        f"<section><h2>分数概览 Score Overview</h2>{chart_html}</section>"
        if chart_html
        else ""
    )
    returns_chart_html = _build_returns_chart(summary)
    returns_section = (
        f"<section><h2>收益曲线 Return Curve</h2>{returns_chart_html}</section>"
        if returns_chart_html
        else ""
    )

    instruments = summary.get("unique_instruments")
    if isinstance(instruments, list):
        instruments_html = "<li><strong>标的列表 / Instruments</strong>: {}</li>".format(
            ", ".join(map(str, instruments))
        )
    else:
        instruments_html = ""

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <title>Hikyuu × Qlib Review</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 2rem; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
        th, td {{ border: 1px solid #ccc; padding: 0.5rem; text-align: left; }}
        th {{ background: #f5f5f5; }}
    </style>
</head>
<body>
    <h1>策略回顾 Strategy Review</h1>
    <p><a href="{detail_href}">查看交易明细 / View Trade Details</a></p>
    <h2>摘要指标 Summary</h2>
    <ul>{metrics_html}{instruments_html}</ul>
    {returns_section}
    {score_chart_section}
    <footer style="margin-top:2rem;">
        <a href="{detail_href}">➡ 前往交易明细 / Trade Details</a>
    </footer>
</body>
</html>
"""


def _render_detail_html(detail_signals: list[dict], summary_href: str, summary: dict) -> str:
    rows_html = "".join(
        f"<tr><td>{row['datetime']}</td><td>{row['instrument']}</td>"
        f"<td>{row['action']}</td><td>{row['weight']}</td><td>{row['score']}</td></tr>"
        for row in detail_signals
    )
    if not rows_html:
        rows_html = "<tr><td colspan='5'>No signals available</td></tr>"

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <title>Hikyuu × Qlib Trade Detail</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 2rem; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
        th, td {{ border: 1px solid #ccc; padding: 0.5rem; text-align: left; }}
        th {{ background: #f5f5f5; }}
    </style>
</head>
<body>
    <h1>交易明细 Trade Details</h1>
    <p><a href="{summary_href}">⬅ 返回摘要 / Back to Summary</a></p>
    <p>交易总计 <strong>{summary.get("total_signals", 0)}</strong> 条，覆盖 <strong>{summary.get("unique_dates", 0)}</strong> 个交易日。</p>
    <table>
        <thead>
            <tr><th>日期 Date</th><th>标的 Instrument</th><th>操作 Action</th><th>权重 Weight</th><th>分数 Score</th></tr>
        </thead>
        <tbody>{rows_html}</tbody>
    </table>
</body>
</html>
"""


def _relative_href(target: Path, base: Path) -> str:
    try:
        return os.path.relpath(target, base.parent)
    except ValueError:
        return target.name


def run(
    signals_path: Path,
    summary_path: Path,
    output_path: Path,
    detail_output_path: Path,
) -> None:
    signals = load_signals(signals_path)
    summary = load_summary(summary_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    detail_output_path.parent.mkdir(parents=True, exist_ok=True)

    detail_href = _relative_href(detail_output_path, output_path)
    summary_href = _relative_href(output_path, detail_output_path)

    summary_html = _render_summary_html(summary, signals, detail_href)
    detail_html = _render_detail_html(signals, summary_href, summary)

    output_path.write_text(summary_html, encoding="utf-8")
    detail_output_path.write_text(detail_html, encoding="utf-8")
    print(f"[render-report] wrote {output_path}")
    print(f"[render-report] wrote {detail_output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Render HTML review report")
    parser.add_argument("--signals", type=Path, default=DEFAULT_SIGNALS)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--detail-output", type=Path, default=DEFAULT_DETAIL_OUTPUT)
    args = parser.parse_args()
    run(args.signals, args.summary, args.output, args.detail_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
