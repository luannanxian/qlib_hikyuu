#!/usr/bin/env python3
"""Train model using Qlib configuration with graceful fallback."""

from __future__ import annotations

import argparse
import json
import os
import pickle
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd

from scripts.config_utils import load_runtime_config

try:  # pragma: no cover - import guard for environments缺少 qlib
    import qlib
    from qlib.constant import REG_CN
    from qlib.utils import init_instance_by_config
except Exception:  # noqa: BLE001
    qlib = None  # type: ignore

EXPERIMENT_DIR = Path("experiments") / "latest"
PRED_PATH = EXPERIMENT_DIR / "pred.pkl"
METRICS_PATH = EXPERIMENT_DIR / "metrics.json"
DEFAULT_CONFIG = Path("config/base.yaml")


def _select_run_mode(config: Dict[str, object]) -> str:
    run_modes = config.get("run_modes", {}) or {}
    preferred = os.environ.get("QLIB_RUN_MODE", run_modes.get("default", "quick"))
    supported = run_modes.get("supported") or [preferred]
    supported = [str(mode) for mode in supported]
    if preferred in supported:
        return preferred
    return supported[0]


def _build_handler_config(spec: Dict[str, object], data_source: str, config: Dict[str, object]) -> Dict[str, object]:
    if data_source == "hikyuu":
        env_codes = os.environ.get("QLIB_HIKYUU_INSTRUMENTS")
        if env_codes:
            instruments = [code.strip().upper() for code in env_codes.split(",") if code.strip()]
        else:
            instruments = [code.strip().upper() for code in config.get("hikyuu", {}).get("instruments", [])]
        if not instruments:
            raise ValueError("Hikyuu data source requires instrument list via config or QLIB_HIKYUU_INSTRUMENTS")
        handler_kwargs = {
            "instruments": instruments,
            "start_time": spec["start_time"],
            "end_time": spec["end_time"],
            "fit_start_time": spec["fit_start_time"],
            "fit_end_time": spec["fit_end_time"],
            "freq": spec.get("freq", "day"),
            "label_shift": int(spec.get("label_shift", 1)),
        }
        return {
            "class": "HikyuuAlphaHandler",
            "module_path": "hikyuu_integration",
            "kwargs": handler_kwargs,
        }

    # Qlib Alpha158 default handler
    handler_kwargs = {
        "start_time": spec["start_time"],
        "end_time": spec["end_time"],
        "fit_start_time": spec["fit_start_time"],
        "fit_end_time": spec["fit_end_time"],
        "instruments": spec["instruments"],
        "infer_processors": [
            {"class": "FilterCol", "kwargs": {"col_list": ["$close", "$volume"]}},
            {"class": "RobustZScoreNorm", "kwargs": {"fields_group": "feature", "clip_outlier": True}},
            {"class": "Fillna", "kwargs": {"fields_group": "feature"}},
        ],
        "learn_processors": [
            {"class": "DropnaLabel"},
            {"class": "CSRankNorm", "kwargs": {"fields_group": "label"}},
        ],
        "label": spec.get("label", ["Ref($close, -1) / $close - 1"]),
    }
    return {
        "class": "Alpha158",
        "module_path": "qlib.contrib.data.handler",
        "kwargs": handler_kwargs,
    }


def _build_dataset_and_model(config: Dict[str, object]) -> Tuple[Dict[str, object], Dict[str, object]]:
    run_mode = _select_run_mode(config)
    dataset_cfg = config.get("dataset", {})
    spec = dataset_cfg.get(run_mode)
    if not isinstance(spec, dict):
        raise ValueError(f"Dataset configuration for run mode '{run_mode}' not found")

    data_source = os.environ.get("QLIB_DATA_SOURCE", "qlib").lower()
    handler_cfg = _build_handler_config(spec, data_source, config)
    segments_cfg = spec.get("segments", {})
    if not isinstance(segments_cfg, dict):
        raise ValueError("segments configuration must be a mapping")
    segments = {name: tuple(values) for name, values in segments_cfg.items()}

    dataset_config = {
        "class": "DatasetH",
        "module_path": "qlib.data.dataset",
        "kwargs": {
            "handler": handler_cfg,
            "segments": segments,
        },
    }

    model_cfg = config.get("model", {})
    if not isinstance(model_cfg, dict):
        raise ValueError("model configuration must be a mapping")
    model_config = {
        "class": model_cfg.get("class", "LGBModel"),
        "module_path": model_cfg.get("module_path", "qlib.contrib.model.gbdt"),
        "kwargs": model_cfg.get("kwargs", {}),
    }
    return dataset_config, model_config


def _train_with_qlib(config: Dict[str, object], pred_path: Path, metrics_path: Path) -> None:
    if qlib is None:
        raise ImportError("qlib is not installed in the current environment")

    provider_uri = os.path.expanduser(config.get("data", {}).get("provider_uri", "~/.qlib/qlib_data/cn_data"))
    qlib.init(provider_uri=provider_uri, region=REG_CN, expression_cache=None, dataset_cache=None)

    dataset_cfg, model_cfg = _build_dataset_and_model(config)
    dataset = init_instance_by_config(dataset_cfg)
    model = init_instance_by_config(model_cfg)

    model.fit(dataset)
    pred = model.predict(dataset, segment="test")
    if isinstance(pred, pd.Series):
        pred_df = pred.to_frame("score")
    else:
        pred_df = pd.DataFrame(pred)

    pred_path.parent.mkdir(parents=True, exist_ok=True)
    pred_df.to_pickle(pred_path)

    if isinstance(pred_df.index, pd.MultiIndex):
        instruments = sorted(pred_df.index.get_level_values(-1).unique())
    else:
        instruments = []

    metrics = {
        "placeholder": False,
        "rows": int(len(pred_df)),
        "instruments": instruments,
    }
    metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False))
    print(f"[train-model] trained via qlib, predictions saved to {pred_path}")


def _train_placeholder(pred_path: Path, metrics_path: Path) -> None:
    rng = np.random.default_rng(seed=2024)
    dates = pd.date_range(end=pd.Timestamp.today(), periods=5, freq="B")
    instruments = ["SH600000", "SH600009", "SZ000001", "SZ000002"]
    records = []
    for dt in dates:
        for inst in instruments:
            records.append((dt, inst, float(rng.normal())))
    pred_df = pd.DataFrame(records, columns=["datetime", "instrument", "score"]).set_index(["datetime", "instrument"])
    pred_path.parent.mkdir(parents=True, exist_ok=True)
    pred_df.to_pickle(pred_path)
    metrics = {
        "placeholder": True,
        "rows": int(len(pred_df)),
        "instruments": instruments,
    }
    metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False))
    print(f"[train-model] fallback predictions saved to {pred_path}")


def run_with_config(config: Dict[str, object], pred_path: Path = PRED_PATH, metrics_path: Path = METRICS_PATH) -> None:
    try:
        _train_with_qlib(config, pred_path, metrics_path)
        log_to_mlflow(config, metrics_path)
    except Exception as exc:  # pragma: no cover
        print(f"[train-model] qlib workflow failed: {exc}\nUsing placeholder results instead.")
        _train_placeholder(pred_path, metrics_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Train model using Qlib or fallback")
    parser.add_argument("--config", nargs="+", type=Path, default=[DEFAULT_CONFIG])
    parser.add_argument("--pred-path", type=Path, default=PRED_PATH)
    parser.add_argument("--metrics-path", type=Path, default=METRICS_PATH)
    args = parser.parse_args()

    config = load_runtime_config(list(args.config)) or {}
    run_with_config(config, pred_path=args.pred_path, metrics_path=args.metrics_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
