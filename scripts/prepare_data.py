#!/usr/bin/env python3
"""Prepare training dataset by extracting OHLCV data via Qlib/Hikyuu."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from scripts.config_utils import load_runtime_config
from scripts.logging_utils import setup_structured_logging

DEFAULT_OUTPUT = Path("data") / "prepared_dataset.csv"
DEFAULT_CONFIGS = [Path("config/base.yaml")]
LOGGER = logging.getLogger("prepare-data")


def _init_qlib(provider_uri: str, region: str) -> bool:
    try:
        import qlib
        from qlib.constant import REG_CN, REG_US, REG_TW
    except Exception as exc:  # pragma: no cover
        LOGGER.warning("Qlib not available: %s", exc)
        return False

    region_map = {"cn": REG_CN, "us": REG_US, "tw": REG_TW}
    target_region = region_map.get(region.lower(), REG_CN)

    if not getattr(qlib.config.C, "_registered", False):  # type: ignore[attr-defined]
        qlib.init(
            provider_uri=os.path.expanduser(provider_uri),
            region=target_region,
            expression_cache=None,
            dataset_cache=None,
        )
    return True


def _resolve_instruments(data_source: str, spec: Dict[str, object], config: Dict[str, object]) -> Sequence[str] | str:
    if data_source == "hikyuu":
        instruments = config.get("hikyuu", {}).get("instruments")
        if instruments:
            return instruments
        env_codes = os.environ.get("QLIB_HIKYUU_INSTRUMENTS")
        if env_codes:
            return [code.strip().upper() for code in env_codes.split(",") if code.strip()]
        raise ValueError("Hikyuu data source requires instrument list via config.hikyuu.instruments or QLIB_HIKYUU_INSTRUMENTS")

    return spec.get("instruments", "csi100")


def _flatten_columns(columns: Iterable) -> List[str]:
    names: List[str] = []
    for col in columns:
        if isinstance(col, tuple):
            names.append(col[-1])
        else:
            names.append(str(col))
    return names


def _detect_anomalies(df: pd.DataFrame) -> Tuple[List[str], List[str], List[str]]:
    warnings_missing: List[str] = []
    warnings_negative: List[str] = []
    warnings_duplicates: List[str] = []

    duplicates = df.duplicated(subset=["date", "symbol"])
    if duplicates.any():
        dup_symbols = df.loc[duplicates, "symbol"].unique().tolist()
        warnings_duplicates = [f"duplicate rows for symbols: {', '.join(dup_symbols)}"]

    for symbol, group in df.groupby("symbol"):
        if len(group["date"].unique()) <= 1:
            continue
        date_range = pd.date_range(group["date"].min(), group["date"].max(), freq="B")
        missing = date_range.difference(group["date"])
        if len(missing) > 0:
            warnings_missing.append(f"{symbol}: missing {len(missing)} business days")

        numeric_cols = ["open", "high", "low", "close", "volume", "amount"]
        for col in numeric_cols:
            if col in group.columns:
                invalid = group[col] <= 0
                if invalid.any():
                    warnings_negative.append(f"{symbol}: {col} has {invalid.sum()} non-positive entries")

    return warnings_missing, warnings_negative, warnings_duplicates


def _append_existing_if_needed(
    output_path: Path,
    df_new: pd.DataFrame,
    append: bool,
) -> pd.DataFrame:
    if not append or not output_path.exists():
        return df_new

    try:
        existing = pd.read_csv(output_path, parse_dates=["date"])
    except Exception as exc:  # pragma: no cover
        LOGGER.warning("Failed to read existing dataset %s: %s. Rewriting from scratch.", output_path, exc)
        return df_new

    if existing.empty:
        return df_new

    combined = pd.concat([existing, df_new], axis=0, ignore_index=True)
    combined = combined.drop_duplicates(subset=["date", "symbol"]).sort_values(["date", "symbol"])
    return combined.reset_index(drop=True)


def _prepare_dataset(config: Dict[str, object], output_path: Path, append: bool, chunk_days: int) -> bool:
    run_mode = config.get("run_modes", {}).get("default", "quick")
    dataset_cfg = config.get("dataset", {}) or {}
    spec = dataset_cfg.get(run_mode)
    if not isinstance(spec, dict):
        raise ValueError(f"Dataset configuration for run mode '{run_mode}' not found")

    data_cfg = config.get("data", {}) or {}
    provider_uri = str(data_cfg.get("provider_uri", "~/.qlib/qlib_data/cn_data"))
    region = str(data_cfg.get("region", "cn"))
    data_source = str(data_cfg.get("data_source") or os.environ.get("QLIB_DATA_SOURCE", "qlib")).lower()

    instruments = _resolve_instruments(data_source, spec, config)
    start_time = pd.Timestamp(spec.get("start_time") or spec.get("start") or "2018-01-01")
    end_time = pd.Timestamp(spec.get("end_time") or spec.get("end") or "2020-12-31")
    freq = spec.get("freq") or spec.get("frequency") or "day"

    if not _init_qlib(provider_uri, region):
        return False

    from qlib.data import D  # type: ignore  # noqa: WPS347

    expressions = ["$open", "$high", "$low", "$close", "$volume", "$amount"]
    chunks: List[pd.DataFrame] = []
    chunk_delta = pd.Timedelta(days=max(chunk_days, 1))
    cursor = start_time
    while cursor <= end_time:
        chunk_end = min(cursor + chunk_delta - pd.Timedelta(days=1), end_time)
        try:
            df_chunk = D.features(
                instruments,
                expressions,
                cursor.strftime("%Y-%m-%d"),
                chunk_end.strftime("%Y-%m-%d"),
                freq=freq,
            )
        except Exception as exc:  # pragma: no cover
            LOGGER.warning("Failed to fetch features [%s, %s]: %s", cursor.date(), chunk_end.date(), exc)
            return False
        if df_chunk.empty:
            LOGGER.warning("Empty data returned for chunk [%s, %s]", cursor.date(), chunk_end.date())
        else:
            df_chunk.columns = _flatten_columns(df_chunk.columns)
            chunks.append(df_chunk.reset_index())
            LOGGER.info(
                "Fetched %d rows for chunk [%s, %s]",
                len(df_chunk),
                cursor.date(),
                chunk_end.date(),
            )
        cursor = chunk_end + pd.Timedelta(days=1)

    if not chunks:
        LOGGER.warning("No data fetched from Qlib.")
        return False

    df_all = pd.concat(chunks, axis=0, ignore_index=True)
    df_all.rename(columns={"datetime": "date", "instrument": "symbol"}, inplace=True)
    df_all["date"] = pd.to_datetime(df_all["date"])
    df_all = df_all.drop_duplicates(subset=["date", "symbol"]).sort_values(["date", "symbol"]).reset_index(drop=True)

    if append:
        df_all = _append_existing_if_needed(output_path, df_all, append=True)

    missing, negatives, duplicates = _detect_anomalies(df_all)
    for msg in missing:
        LOGGER.warning("Missing data: %s", msg)
    for msg in negatives:
        LOGGER.warning("Non-positive data: %s", msg)
    for msg in duplicates:
        LOGGER.warning("Duplicates: %s", msg)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_all.to_csv(output_path, index=False)
    LOGGER.info("Prepared dataset with %d rows and %d columns -> %s", len(df_all), len(df_all.columns), output_path)
    return True


def run(
    output: Path = DEFAULT_OUTPUT,
    config_paths: Optional[Sequence[Path]] = None,
    append: bool = False,
    chunk_days: int = 120,
) -> None:
    config = load_runtime_config(list(config_paths or DEFAULT_CONFIGS)) or {}
    success = False
    try:
        success = _prepare_dataset(config, output, append, chunk_days)
    except Exception as exc:  # pragma: no cover
        LOGGER.warning("prepare_data failed: %s", exc)
        success = False

    if not success:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("Placeholder dataset due to data preparation failure.\n")
        LOGGER.warning("Fallback placeholder dataset written to %s", output)

    print(f"[prepare-data] wrote {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare dataset using Qlib/Hikyuu data")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--config", nargs="+", type=Path, default=DEFAULT_CONFIGS)
    parser.add_argument("--append", action="store_true", help="追加模式，仅补充新日期的数据")
    parser.add_argument("--chunk-days", type=int, default=120, help="按天分片抓取的窗口大小")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    setup_structured_logging("prepare-data", verbose=args.verbose)
    run(args.output, args.config, append=args.append, chunk_days=args.chunk_days)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
