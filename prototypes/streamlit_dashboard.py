"""Lightweight Streamlit prototype for GA 4.3 UI exploration."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st


def load_summary(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def load_signals(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    if "datetime" in df:
        df["datetime"] = pd.to_datetime(df["datetime"])
    return df


def main() -> None:
    st.set_page_config(page_title="Hikyuu × Qlib Dashboard", layout="wide")
    st.title("Hikyuu × Qlib 复盘原型")

    summary_path = Path(st.sidebar.text_input("Summary JSON", "reports/latest/backtest_summary.json"))
    signals_path = Path(st.sidebar.text_input("Signals CSV", "artifacts/signals.csv"))

    summary = load_summary(summary_path)
    signals = load_signals(signals_path)

    st.subheader("关键指标")
    cols = st.columns(3)
    metrics = [
        ("Total Return", summary.get("total_return")),
        ("Annualized Return", summary.get("annualized_return")),
        ("Sharpe", summary.get("sharpe_ratio")),
        ("Max Drawdown", summary.get("max_drawdown")),
        ("Signals", summary.get("total_signals")),
    ]
    for idx, (label, value) in enumerate(metrics):
        with cols[idx % len(cols)]:
            st.metric(label, f"{value:.4f}" if isinstance(value, (int, float)) else "-")

    if not signals.empty:
        st.subheader("信号预览")
        st.dataframe(signals.head(100))

        st.subheader("每日信号数量")
        daily_counts = signals.groupby(signals["datetime"].dt.date)["instrument"].count()
        st.line_chart(daily_counts)
    else:
        st.info("未找到信号数据")


if __name__ == "__main__":
    main()

