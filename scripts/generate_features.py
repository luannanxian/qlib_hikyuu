#!/usr/bin/env python3
"""Generate factor features from templates using Qlib (with graceful fallback)."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd

from scripts.config_utils import _DEFAULT_TEMPLATE, load_yaml

OUTPUT_DIR = Path("features")
DEFAULT_OUTPUT = OUTPUT_DIR / "features.csv"
DEFAULT_TEMPLATE = Path("config/templates/default_indicators.yaml")
LOGGER = logging.getLogger("generate-features")


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


def _compute_with_qlib(runtime_cfg: Dict[str, object], output: Path) -> bool:
    try:
        import qlib
        from qlib.constant import REG_CN, REG_US, REG_TW
        from qlib.data import D
    except Exception as exc:  # pragma: no cover
        LOGGER.warning("Qlib not available: %s", exc)
        return False

    region_map = {"cn": REG_CN, "us": REG_US, "tw": REG_TW}
    region = region_map.get(str(runtime_cfg["region"]).lower(), REG_CN)

    qlib.init(
        provider_uri=os.path.expanduser(str(runtime_cfg["provider_uri"])),
        region=region,
        expression_cache=None,
        dataset_cache=None,
    )

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
        return False

    df.columns = pd.Index(column_names, name="indicator")
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output)
    LOGGER.info(
        "Generated %d indicators for %d records via Qlib: %s",
        len(column_names),
        len(df),
        output,
    )
    return True


def emit_placeholder(template: Dict[str, object], output: Path) -> None:
    indicators = template.get("indicators") or []
    rows = ["indicator,value"]
    for indicator in indicators:
        if isinstance(indicator, dict):
            name = indicator.get("name") or indicator.get("type", "UNKNOWN")
        else:
            name = str(indicator)
        rows.append(f"{name},0.0")
    if len(rows) == 1:
        rows.append("placeholder,0.0")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(rows))
    LOGGER.info("Fallback placeholder features written to %s", output)


def _emit_features(template_path: Path, output_path: Path) -> None:
    template = _load_template(template_path)
    runtime_cfg = _resolve_runtime_config(template)
    if not _compute_with_qlib(runtime_cfg, output_path):
        emit_placeholder(template, output_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate features from template configuration.")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)

    _emit_features(args.template, args.output)
    return 0


def run_from_config(template_path: Path, output_path: Path) -> None:
    _emit_features(template_path, output_path)


if __name__ == "__main__":
    raise SystemExit(main())
