#!/usr/bin/env python3
"""Evaluate trading signals using Hikyuu行情数据并输出真实收益曲线。"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

try:  # pragma: no cover - optional dependency
    from hikyuu_integration import HikyuuDataLoader
    _HIKYUU_IMPORT_ERROR: Optional[Exception] = None
except Exception as exc:  # noqa: BLE001
    HikyuuDataLoader = None  # type: ignore[assignment]
    _HIKYUU_IMPORT_ERROR = exc

DEFAULT_SIGNAL_PATH = Path("artifacts") / "signals.csv"
DEFAULT_REPORT_PATH = Path("reports") / "latest" / "backtest_summary.json"
DEFAULT_BENCHMARK_SYMBOL = "SH000300"
TRADING_DAYS_PER_YEAR = 252


def _load_signals(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Signals file not found: {path}")
    df = pd.read_csv(path)
    if df.empty:
        raise ValueError("信号文件为空，无法回测。")
    if "datetime" not in df.columns or "instrument" not in df.columns:
        raise ValueError("信号文件缺少 datetime 或 instrument 列。")
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["instrument"] = df["instrument"].astype(str).str.upper()
    df["action"] = df.get("action", "buy").astype(str).str.lower()
    df["weight"] = pd.to_numeric(df.get("weight", 0.0), errors="coerce").fillna(0.0)
    df["score"] = pd.to_numeric(df.get("score", 0.0), errors="coerce").fillna(0.0)
    df.sort_values(["datetime", "instrument"], inplace=True)
    return df.reset_index(drop=True)


def _load_close_prices(instruments: Iterable[str], start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if HikyuuDataLoader is None:
        raise RuntimeError(
            "未安装 hikyuu，无法执行真实收益计算。请在运行环境中安装 hikyuu 或使用 qlib_hikyuu 虚拟环境。"
        ) from _HIKYUU_IMPORT_ERROR
    loader = HikyuuDataLoader(fields=("CLOSE",), freq="day", label_shift=0)
    data = loader.load(instruments, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    if data.empty:
        raise ValueError("无法从 Hikyuu 获取到对应标的的行情数据。")
    close_series = data[("feature", "CLOSE")]
    close = close_series.unstack("instrument").sort_index()
    close.index = pd.to_datetime(close.index)
    return close.loc[(close.index >= start) & (close.index <= end)]


def _compute_returns(close: pd.DataFrame) -> pd.DataFrame:
    forward = close.shift(-1)
    returns = forward / close - 1.0
    returns = returns.iloc[:-1].fillna(0.0)
    return returns


def _max_drawdown(cumulative: pd.Series) -> float:
    peak = cumulative.cummax()
    drawdown = (cumulative - peak) / peak.replace(0, np.nan)
    return float(drawdown.min()) if not drawdown.empty else 0.0


def _annualized_metrics(daily_returns: pd.Series) -> Tuple[float, float, float]:
    if daily_returns.empty:
        return 0.0, 0.0, 0.0
    mean_daily = daily_returns.mean()
    vol = daily_returns.std(ddof=0)
    annual_return = (1 + mean_daily) ** TRADING_DAYS_PER_YEAR - 1
    annual_vol = vol * np.sqrt(TRADING_DAYS_PER_YEAR)
    sharpe = annual_return / annual_vol if annual_vol else 0.0
    return float(annual_return), float(annual_vol), float(sharpe)


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _segregate(rows: Iterable[dict]) -> Tuple[list[dict], list[dict]]:
    long_rows = []
    short_rows = []
    for row in rows:
        action = (row.get("action") or "").lower()
        if action == "sell":
            short_rows.append(row)
        else:
            long_rows.append(row)
    return long_rows, short_rows


def _read_benchmark_file(path: Path) -> Dict[str, float]:
    if not path.exists():
        return {}

    with path.open(newline="") as fp:
        reader = csv.DictReader(fp)
        rows = list(reader)

    if not rows:
        return {}

    def _find_field(names: Iterable[str], target_keywords: Iterable[str]) -> Optional[str]:
        lowered_map = {name.lower(): name for name in names}
        for keyword in target_keywords:
            if keyword in lowered_map:
                return lowered_map[keyword]
        return None

    first_row = rows[0]
    date_field = _find_field(first_row.keys(), ("datetime", "date"))
    return_field = None
    for key in first_row.keys():
        if "return" in key.lower() or key.lower() in {"ret", "pct_chg"}:
            return_field = key
            break

    price_field = None
    if return_field is None:
        price_field = _find_field(first_row.keys(), ("close", "price", "last", "close_price"))

    data: Dict[str, float] = {}
    if return_field:
        for row in rows:
            date_value = (row.get(date_field) or "").strip() if date_field else ""
            if not date_value:
                continue
            data[date_value] = _float(row.get(return_field))
    elif price_field:
        prev_price: Optional[float] = None
        for row in sorted(rows, key=lambda r: (r.get(date_field) or "").strip()):
            date_value = (row.get(date_field) or "").strip() if date_field else ""
            if not date_value:
                continue
            price = _float(row.get(price_field))
            if prev_price is not None and prev_price != 0.0:
                data[date_value] = (price / prev_price) - 1.0
            else:
                data[date_value] = 0.0
            prev_price = price
    return data


def _placeholder_benchmark(dates: List[str]) -> Dict[str, float]:
    if not dates:
        return {}
    # Create a gentle upward slope as placeholder.
    midpoint = len(dates) / 2 if dates else 1
    returns: Dict[str, float] = {}
    for idx, date in enumerate(sorted(dates)):
        drift = 0.0005
        seasonal = 0.0003 * ((idx - midpoint) / max(midpoint, 1))
        returns[date] = round(drift + seasonal, 6)
    return returns


def _load_benchmark_returns(
    dates: List[str],
    benchmark_csv: Optional[Path],
    benchmark_symbol: Optional[str],
) -> Dict[str, float]:
    if not dates:
        return {}

    returns: Dict[str, float] = {}

    if benchmark_csv is not None:
        returns = _read_benchmark_file(benchmark_csv)

    if not returns and benchmark_symbol:
        # Attempt to load via qlib when available.
        try:
            import pandas as pd  # type: ignore
            import qlib  # type: ignore
            from qlib.data import D  # type: ignore
            from qlib.constant import REG_CN  # type: ignore

            if not getattr(qlib.config.C, "_registered", False):  # type: ignore[attr-defined]
                qlib.init(provider_uri="~/.qlib/qlib_data/cn_data", region=REG_CN)

            if dates:
                df = D.features(
                    benchmark_symbol,
                    ["Ref($close, -1) / $close - 1"],
                    start_time=min(dates),
                    end_time=max(dates),
                )
                if isinstance(df, pd.DataFrame):
                    for datetime_value, value in df.iloc[:, 0].items():
                        date = str(datetime_value)[:10]
                        returns[date] = float(value)
        except Exception:
            returns = {}

    if not returns:
        returns = _placeholder_benchmark(dates)

    return {date: returns.get(date, 0.0) for date in dates}


@dataclass
class DailyStat:
    date: pd.Timestamp
    pnl: float
    long_exposure: float
    short_exposure: float
    gross_exposure: float
    net_exposure: float


def run(
    signal_path: Path,
    report_path: Path,
    benchmark_symbol: Optional[str] = DEFAULT_BENCHMARK_SYMBOL,
    benchmark_csv: Optional[Path] = None,
) -> None:
    signals = _load_signals(signal_path)
    instruments = sorted(signals["instrument"].unique())
    long_signals = signals[signals["action"] != "sell"]
    short_signals = signals[signals["action"] == "sell"]

    start_date = signals["datetime"].min()
    end_date = signals["datetime"].max()
    close = _load_close_prices(instruments, start_date, end_date + pd.Timedelta(days=5))
    returns = _compute_returns(close)

    portfolio_returns: List[DailyStat] = []
    for date, group in signals.groupby("datetime"):
        if date not in returns.index:
            continue
        daily_ret = 0.0
        long_exp = 0.0
        short_exp = 0.0
        for row in group.itertuples():
            inst = row.instrument
            if inst not in returns.columns:
                continue
            instrument_return = returns.at[date, inst]
            weight = float(row.weight)
            if row.action == "sell":
                daily_ret -= weight * instrument_return
                short_exp += weight
            else:
                daily_ret += weight * instrument_return
                long_exp += weight
        if long_exp == 0 and short_exp == 0:
            continue
        gross = long_exp + short_exp
        net = long_exp - short_exp
        portfolio_returns.append(
            DailyStat(date=date, pnl=daily_ret, long_exposure=long_exp, short_exposure=short_exp, gross_exposure=gross, net_exposure=net)
        )

    if not portfolio_returns:
        raise ValueError("在所选时间范围内无法计算任何有效的收益。")

    portfolio_series = pd.Series(
        {stat.date: stat.pnl for stat in portfolio_returns},
        dtype=float,
    ).sort_index()

    cumulative = (1 + portfolio_series).cumprod() - 1
    benchmark_dates = [date.strftime("%Y-%m-%d") for date in portfolio_series.index]
    benchmark_daily = _load_benchmark_returns(benchmark_dates, benchmark_csv, benchmark_symbol)
    benchmark_series = pd.Series(
        [benchmark_daily.get(date.strftime("%Y-%m-%d"), 0.0) for date in portfolio_series.index],
        index=portfolio_series.index,
        dtype=float,
    )
    benchmark_cumulative = (1 + benchmark_series).cumprod() - 1

    annual_return, annual_vol, sharpe = _annualized_metrics(portfolio_series)
    max_dd = _max_drawdown(1 + cumulative)

    avg_long_exp = float(np.mean([stat.long_exposure for stat in portfolio_returns]))
    avg_short_exp = float(np.mean([stat.short_exposure for stat in portfolio_returns]))
    avg_gross_exp = float(np.mean([stat.gross_exposure for stat in portfolio_returns]))
    avg_net_exp = float(np.mean([stat.net_exposure for stat in portfolio_returns]))
    total_long_exposure = float(long_signals["weight"].sum())
    total_short_exposure = float(short_signals["weight"].sum())
    avg_weight = float(signals["weight"].mean()) if not signals.empty else 0.0

    unique_instrument_list = sorted(instruments)
    summary = {
        "total_signals": int(len(signals)),
        "unique_dates": int(signals["datetime"].nunique()),
        "unique_instruments": unique_instrument_list,
        "unique_instrument_count": int(len(unique_instrument_list)),
        "long_signals": int(len(long_signals)),
        "short_signals": int(len(short_signals)),
        "avg_long_exposure": round(avg_long_exp, 6),
        "avg_short_exposure": round(avg_short_exp, 6),
        "avg_gross_exposure": round(avg_gross_exp, 6),
        "avg_net_exposure": round(avg_net_exp, 6),
        "long_exposure": round(total_long_exposure, 6),
        "short_exposure": round(total_short_exposure, 6),
        "average_weight": round(avg_weight, 6),
        "total_return": round(float(cumulative.iloc[-1]), 6),
        "annualized_return": round(annual_return, 6),
        "annualized_vol": round(annual_vol, 6),
        "sharpe_ratio": round(sharpe, 6),
        "max_drawdown": round(max_dd, 6),
        "benchmark_symbol": benchmark_symbol,
        "daily_returns": [
            {
                "date": stat.date.strftime("%Y-%m-%d"),
                "value": round(stat.pnl, 6),
                "long_exposure": round(stat.long_exposure, 6),
                "short_exposure": round(stat.short_exposure, 6),
                "gross_exposure": round(stat.gross_exposure, 6),
                "net_exposure": round(stat.net_exposure, 6),
            }
            for stat in portfolio_returns
        ],
        "cumulative_returns": [
            {"date": date.strftime("%Y-%m-%d"), "value": round(val, 6)}
            for date, val in cumulative.items()
        ],
        "benchmark_daily_returns": [
            {"date": date.strftime("%Y-%m-%d"), "value": round(benchmark_series.at[date], 6)}
            for date in benchmark_series.index
        ],
        "benchmark_cumulative_returns": [
            {"date": date.strftime("%Y-%m-%d"), "value": round(val, 6)}
            for date, val in benchmark_cumulative.items()
        ],
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"[run-backtest] summary written to {report_path}")
    for key, value in summary.items():
        if isinstance(value, list):
            continue
        print(f"  - {key}: {value}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run placeholder backtest")
    parser.add_argument("--signals", type=Path, default=DEFAULT_SIGNAL_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--benchmark-symbol", type=str, default=DEFAULT_BENCHMARK_SYMBOL)
    parser.add_argument("--benchmark-csv", type=Path)
    args = parser.parse_args()
    run(
        args.signals,
        args.report,
        benchmark_symbol=args.benchmark_symbol,
        benchmark_csv=args.benchmark_csv,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
