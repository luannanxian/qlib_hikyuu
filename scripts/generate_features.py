#!/usr/bin/env python3
"""Generate factor features from templates using Qlib (with graceful fallback)."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from scripts.config_utils import _DEFAULT_TEMPLATE, load_yaml

OUTPUT_DIR = Path("features")
DEFAULT_OUTPUT = OUTPUT_DIR / "features.csv"
DEFAULT_TEMPLATE = Path("config/templates/default_indicators.yaml")
LOGGER = logging.getLogger("generate-features")
HIKYUU_CACHE_PATH = Path("experiments") / "latest" / "hikyuu_cache.pkl"


def _load_template(path: Path) -> Dict[str, object]:
    try:
        return load_yaml(path, fallback=_DEFAULT_TEMPLATE)
    except Exception as exc:  # pragma: no cover
        LOGGER.warning("Failed to load template %s: %s. Using default.", path, exc)
        return dict(_DEFAULT_TEMPLATE)


def _coerce_iterable(value: object) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(v) for v in value]
    return [str(value)]


def _build_expression(indicator: Dict[str, object]) -> Tuple[str, str]:
    if "expression" in indicator:
        name = indicator.get("name") or indicator["expression"]
        return str(name), str(indicator["expression"])

    indicator_type = str(indicator.get("type", "")).lower()
    if not indicator_type:
        raise ValueError("Indicator entry must define 'type' or 'expression'")

    field = str(indicator.get("field", "$close"))
    window = indicator.get("window")

    if indicator_type in {"sma", "mean"}:
        if window is None:
            raise ValueError("SMA requires 'window'")
        expr = f"Mean({field}, {int(window)})"
    elif indicator_type == "ema":
        if window is None:
            raise ValueError("EMA requires 'window'")
        expr = f"EMA({field}, {int(window)})"
    elif indicator_type == "std":
        if window is None:
            raise ValueError("STD requires 'window'")
        expr = f"Std({field}, {int(window)})"
    elif indicator_type == "roc":
        if window is None:
            raise ValueError("ROC requires 'window'")
        expr = f"Ref({field}, -{int(window)}) / {field} - 1"
    elif indicator_type == "rsi":
        if window is None:
            raise ValueError("RSI requires 'window'")
        expr = f"RSI({field}, {int(window)})"
    elif indicator_type == "macd":
        fast = int(indicator.get("fast", 12))
        slow = int(indicator.get("slow", 26))
        signal = int(indicator.get("signal", 9))
        expr = f"MACD({field}, {fast}, {slow}, {signal})"
    elif indicator_type == "volatility":
        if window is None:
            raise ValueError("Volatility requires 'window'")
        expr = f"Std({field}, {int(window)}) / Mean({field}, {int(window)})"
    else:
        raise ValueError(f"Unsupported indicator type: {indicator_type}")

    name = indicator.get("name") or f"{indicator_type}_{field.strip('$')}_{window if window else 'custom'}"
    return str(name), expr


def _resolve_runtime_config(template: Dict[str, object]) -> Dict[str, object]:
    cfg = {}
    cfg["provider_uri"] = (
        os.environ.get("QLIB_PROVIDER_URI")
        or template.get("provider_uri")
        or "~/.qlib/qlib_data/cn_data"
    )
    cfg["region"] = os.environ.get("QLIB_REGION") or template.get("region") or "cn"
    instruments = os.environ.get("QLIB_FEATURE_INSTRUMENTS")
    cfg["instruments"] = (
        [code.strip() for code in instruments.split(",") if code.strip()]
        if instruments
        else _coerce_iterable(template.get("instruments") or ["SH600000"])
    )
    cfg["start"] = os.environ.get("QLIB_FEATURE_START") or template.get("start") or template.get("start_time") or "2018-01-01"
    cfg["end"] = os.environ.get("QLIB_FEATURE_END") or template.get("end") or template.get("end_time") or "2020-12-31"
    cfg["freq"] = template.get("frequency") or template.get("freq") or "day"
    cfg["indicators"] = template.get("indicators") or []
    return cfg


def _init_qlib_if_needed(runtime_cfg: Dict[str, object]) -> bool:
    try:
        import qlib
        from qlib.constant import REG_CN, REG_US, REG_TW
        from qlib.data import D
    except Exception as exc:  # pragma: no cover
        LOGGER.warning("Qlib not available: %s", exc)
        return False

    region_map = {"cn": REG_CN, "us": REG_US, "tw": REG_TW}
    region = region_map.get(str(runtime_cfg["region"]).lower(), REG_CN)

    if not getattr(qlib.config.C, "_registered", False):  # type: ignore[attr-defined]
        qlib.init(
            provider_uri=os.path.expanduser(str(runtime_cfg["provider_uri"])),
            region=region,
            expression_cache=None,
            dataset_cache=None,
        )
    return True


def _compute_with_qlib(runtime_cfg: Dict[str, object]) -> Optional[pd.DataFrame]:
    if not _init_qlib_if_needed(runtime_cfg):
        return None

    from qlib.data import D  # type: ignore  # noqa: WPS347

    indicators: Iterable[Dict[str, object]] = runtime_cfg["indicators"]
    expressions: List[str] = []
    column_names: List[str] = []
    for indicator in indicators:
        if not isinstance(indicator, dict):
            raise ValueError("indicator entries must be mappings")
        name, expr = _build_expression(indicator)
        column_names.append(name)
        expressions.append(expr)

    if not expressions:
        LOGGER.warning("No indicators defined in template; skipping Qlib computation.")
        return False

    try:
        df = D.features(
            runtime_cfg["instruments"],
            expressions,
            runtime_cfg["start"],
            runtime_cfg["end"],
            freq=runtime_cfg["freq"],
        )
    except Exception as exc:
        LOGGER.warning("Failed to compute features via Qlib: %s", exc)
        return None

    df.columns = pd.Index(column_names, name="indicator")
    return df


def _placeholder_df(template: Dict[str, object]) -> pd.DataFrame:
    indicators = template.get("indicators") or []
    if not indicators:
        return pd.DataFrame({"indicator": ["placeholder"], "value": [0.0]})
    data = {"indicator": [], "value": []}
    for indicator in indicators:
        if isinstance(indicator, dict):
            name = indicator.get("name") or indicator.get("type", "UNKNOWN")
        else:
            name = str(indicator)
        data["indicator"].append(name)
        data["value"].append(0.0)
    return pd.DataFrame(data)


def _load_cached_hikyuu_data(runtime_cfg: Dict[str, object]) -> Optional[pd.DataFrame]:
    if not HIKYUU_CACHE_PATH.exists():
        return None
    try:
        df = pd.read_pickle(HIKYUU_CACHE_PATH)
    except Exception as exc:  # pragma: no cover
        LOGGER.warning("Failed to load cached Hikyuu dataset: %s", exc)
        return None
    if not isinstance(df.index, pd.MultiIndex):
        LOGGER.warning("Cached dataset index not MultiIndex; skipping cache.")
        return None

    instruments = [code.upper() for code in runtime_cfg.get("instruments", [])]
    start = pd.Timestamp(runtime_cfg.get("start"))
    end = pd.Timestamp(runtime_cfg.get("end"))
    idx = df.index
    if instruments:
        mask_instr = idx.get_level_values("instrument").isin(instruments)
        df = df.loc[mask_instr]
    if start is not pd.NaT:
        df = df.loc[df.index.get_level_values("datetime") >= start]
    if end is not pd.NaT:
        df = df.loc[df.index.get_level_values("datetime") <= end]
    if df.empty:
        LOGGER.warning("Cached dataset filtered to empty selection for current template.")
        return None
    return df.sort_index()


def _resolve_series(value: Any, feature_df: pd.DataFrame) -> pd.Series:
    if isinstance(value, pd.Series):
        return value
    if isinstance(value, str):
        field = value.strip().upper()
        if field not in feature_df.columns:
            raise ValueError(f"Field '{field}' not available in cached dataset.")
        return feature_df[field]
    raise TypeError(f"Unsupported argument type: {type(value)!r}")


def _apply_group_operation(series: pd.Series, func: Callable[[pd.Series], pd.Series]) -> pd.Series:
    grouped = series.groupby(level="instrument", group_keys=False)
    result = grouped.apply(func)
    if isinstance(result.index, pd.MultiIndex):
        try:
            result = result.droplevel(0)
        except (KeyError, ValueError):
            pass
    return result


def _calc_indicator_series(
    indicator_type: str,
    field: Any,
    window: Optional[int],
    feature_df: pd.DataFrame,
) -> pd.Series:
    series = _resolve_series(field, feature_df)
    indicator_type = indicator_type.lower()
    if window is not None:
        window = int(window)

    if indicator_type in {"sma", "mean"}:
        if window is None or window <= 0:
            raise ValueError("SMA/Mean requires a positive window.")
        return _apply_group_operation(series, lambda s: s.rolling(window).mean())

    if indicator_type == "ema":
        if window is None or window <= 0:
            raise ValueError("EMA requires a positive window.")
        return _apply_group_operation(series, lambda s: s.ewm(span=window, adjust=False).mean())

    if indicator_type == "std":
        if window is None or window <= 0:
            raise ValueError("STD requires a positive window.")
        return _apply_group_operation(series, lambda s: s.rolling(window).std())

    if indicator_type == "roc":
        if window is None:
            raise ValueError("ROC requires window.")
        return _apply_group_operation(series, lambda s: s.shift(window) / s - 1.0)

    if indicator_type == "volatility":
        if window is None or window <= 0:
            raise ValueError("Volatility requires a positive window.")
        rolling_mean = _apply_group_operation(series, lambda s: s.rolling(window).mean())
        rolling_std = _apply_group_operation(series, lambda s: s.rolling(window).std())
        return rolling_std / rolling_mean.replace(0.0, pd.NA)

    if indicator_type == "ref":
        if window is None:
            raise ValueError("Ref requires step.")
        return _apply_group_operation(series, lambda s: s.shift(window))

    raise ValueError(f"Unsupported indicator type from cache: {indicator_type}")


def _evaluate_expression_from_cache(
    expression: str,
    feature_df: pd.DataFrame,
    cache: Dict[Tuple[str, str, int], pd.Series],
) -> pd.Series:
    expr_py = re.sub(r"\$(\w+)", lambda m: f"'{m.group(1)}'", expression)

    def _ensure_series(value: Any) -> pd.Series:
        if isinstance(value, str):
            return _resolve_series(value, feature_df)
        if isinstance(value, pd.Series):
            return value
        raise TypeError(f"Expression produced unsupported type {type(value)!r}")

    def _cached_indicator(indicator_type: str, field: str, window: int) -> pd.Series:
        key = (indicator_type, field.lower(), int(window))
        if key not in cache:
            cache[key] = _calc_indicator_series(indicator_type, field, window, feature_df)
        return cache[key]

    def EMA(arg: Any, window: int) -> pd.Series:
        if isinstance(arg, str):
            return _cached_indicator("ema", arg, window)
        return _calc_indicator_series("ema", arg, window, feature_df)

    def SMA(arg: Any, window: int) -> pd.Series:
        if isinstance(arg, str):
            return _cached_indicator("sma", arg, window)
        return _calc_indicator_series("sma", arg, window, feature_df)

    def Mean(arg: Any, window: int) -> pd.Series:
        if isinstance(arg, str):
            return _cached_indicator("mean", arg, window)
        return _calc_indicator_series("mean", arg, window, feature_df)

    def STD(arg: Any, window: int) -> pd.Series:
        if isinstance(arg, str):
            return _cached_indicator("std", arg, window)
        return _calc_indicator_series("std", arg, window, feature_df)

    def ROC(arg: Any, window: int) -> pd.Series:
        if isinstance(arg, str):
            return _cached_indicator("roc", arg, window)
        return _calc_indicator_series("roc", arg, window, feature_df)

    def Volatility(arg: Any, window: int) -> pd.Series:
        if isinstance(arg, str):
            return _cached_indicator("volatility", arg, window)
        return _calc_indicator_series("volatility", arg, window, feature_df)

    def Ref(arg: Any, step: int) -> pd.Series:
        if isinstance(arg, str):
            return _cached_indicator("ref", arg, step)
        return _calc_indicator_series("ref", arg, step, feature_df)

    env = {
        "EMA": EMA,
        "SMA": SMA,
        "Mean": Mean,
        "STD": STD,
        "ROC": ROC,
        "Volatility": Volatility,
        "Ref": Ref,
    }
    result = eval(expr_py, {"__builtins__": {}}, env)
    series = _ensure_series(result)
    return series


def _compute_indicator_from_cache(
    indicator: Dict[str, object],
    feature_df: pd.DataFrame,
    cache: Dict[Tuple[str, str, int], pd.Series],
) -> pd.Series:
    if "expression" in indicator:
        return _evaluate_expression_from_cache(str(indicator["expression"]), feature_df, cache)

    indicator_type = str(indicator.get("type", "")).lower()
    field = str(indicator.get("field", "$close")).lstrip("$")
    window = indicator.get("window")
    key = (indicator_type, field.lower(), int(window) if window is not None else -1)
    if key not in cache:
        cache[key] = _calc_indicator_series(indicator_type, field, window, feature_df)
    return cache[key]


def _compute_with_cache(runtime_cfg: Dict[str, object]) -> Optional[pd.DataFrame]:
    cached_df = _load_cached_hikyuu_data(runtime_cfg)
    if cached_df is None:
        return None
    feature_df = cached_df["feature"]
    feature_df.columns = [col.upper() for col in feature_df.columns]
    indicators = runtime_cfg.get("indicators") or []
    if not indicators:
        LOGGER.warning("No indicators defined; cache computation skipped.")
        return None

    cache: Dict[Tuple[str, str, int], pd.Series] = {}
    series_map: Dict[str, pd.Series] = {}
    for indicator in indicators:
        if not isinstance(indicator, dict):
            raise ValueError("indicator entries must be mappings")
        name = indicator.get("name") or indicator.get("type")
        if not name:
            raise ValueError("Indicator entry requires name or type.")
        try:
            series = _compute_indicator_from_cache(indicator, feature_df, cache)
        except Exception as exc:
            LOGGER.warning("Failed to compute indicator '%s' from cache: %s", name, exc)
            return None
        series_map[str(name)] = series

    if not series_map:
        return None

    result = pd.concat(series_map.values(), axis=1)
    result.columns = pd.Index(list(series_map.keys()), name="indicator")
    result = result.sort_index()
    return result


def _determine_version(
    template_path: Path,
    runtime_cfg: Dict[str, object],
    override: Optional[str],
) -> str:
    if override and override != "auto":
        return override

    payload = {
        "template": str(template_path.resolve()),
        "template_mtime": template_path.stat().st_mtime if template_path.exists() else None,
        "runtime": {
            "instruments": runtime_cfg.get("instruments"),
            "start": runtime_cfg.get("start"),
            "end": runtime_cfg.get("end"),
            "freq": runtime_cfg.get("freq"),
            "indicators": runtime_cfg.get("indicators"),
        },
    }
    digest = hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    return digest[:10]


def _versioned_path(output_path: Path, version: str) -> Path:
    stem = output_path.stem
    suffix = output_path.suffix or ".csv"
    return output_path.with_name(f"{stem}_v{version}{suffix}")


def _write_manifest(manifest_path: Path, version: str, file_path: Path, runtime_cfg: Dict[str, object]) -> None:
    entry = {
        "version": version,
        "file": str(file_path.name),
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "runtime": runtime_cfg,
    }
    manifest = []
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text())
        except Exception:  # pragma: no cover - malformed manifest fallback
            manifest = []
    manifest = [item for item in manifest if item.get("version") != version]
    manifest.append(entry)
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))


def _save_dataframe(df: pd.DataFrame, path: Path, fmt: str) -> None:
    fmt = fmt.lower()
    path.parent.mkdir(parents=True, exist_ok=True)
    is_placeholder = set(df.columns) <= {"indicator", "value"} and list(df.index.names) == [None]
    if fmt == "csv":
        df.to_csv(path, index=not is_placeholder)
    elif fmt in {"parquet", "pq"}:
        try:
            df.to_parquet(path)
        except Exception as exc:  # pragma: no cover
            LOGGER.warning("Failed to write Parquet %s: %s", path, exc)
    elif fmt in {"hdf", "h5", "hdf5"}:
        try:
            df.to_hdf(path, key="data", mode="w")
        except Exception as exc:  # pragma: no cover
            LOGGER.warning("Failed to write HDF5 %s: %s", path, exc)
    else:
        raise ValueError(f"Unsupported format: {fmt}")


def _emit_features(
    template_path: Path,
    output_path: Path,
    version_override: Optional[str] = None,
    formats: Optional[Sequence[str]] = None,
    keep_basename: bool = True,
) -> None:
    template = _load_template(template_path)
    runtime_cfg = _resolve_runtime_config(template)
    df = _compute_with_cache(runtime_cfg)
    if df is None:
        df = _compute_with_qlib(runtime_cfg)
    if df is None:
        raise RuntimeError(
            "无法从缓存或 Qlib 生成特征，请先运行 train 步骤或检查 Qlib 数据配置。"
        )

    version = _determine_version(template_path, runtime_cfg, version_override)
    version_path = _versioned_path(output_path, version)
    selected_formats = [fmt.lower() for fmt in (formats or ("csv",))]

    for fmt in selected_formats:
        target = version_path if fmt == "csv" else version_path.with_suffix(f".{fmt if fmt not in {'hdf','hdf5'} else 'h5'}")
        _save_dataframe(df, target, fmt)
        LOGGER.info("Wrote features (%s) to %s", fmt, target)

    if keep_basename:
        for fmt in selected_formats:
            target = output_path if fmt == "csv" else output_path.with_suffix(f".{fmt if fmt not in {'hdf','hdf5'} else 'h5'}")
            _save_dataframe(df, target, fmt)

    manifest_path = output_path.with_suffix(output_path.suffix + ".versions.json")
    _write_manifest(manifest_path, version, version_path, runtime_cfg)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate features from template configuration.")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--version", type=str, default="auto", help="Version tag (default auto hash)")
    parser.add_argument(
        "--format",
        action="append",
        dest="formats",
        help="Output format (csv/hdf/parquet). Repeat for multiple.",
    )
    parser.add_argument("--no-base-copy", action="store_true", help="Only write versioned files")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)

    _emit_features(
        args.template,
        args.output,
        version_override=args.version,
        formats=args.formats,
        keep_basename=not args.no_base_copy,
    )
    return 0


def run_from_config(
    template_path: Path,
    output_path: Path,
    version: Optional[str] = None,
    formats: Optional[Sequence[str]] = None,
    keep_basename: bool = True,
) -> None:
    _emit_features(template_path, output_path, version_override=version, formats=formats, keep_basename=keep_basename)


if __name__ == "__main__":
    raise SystemExit(main())
