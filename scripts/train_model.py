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
    # NOTE: In newer Qlib versions, Alpha158 creates flat columns instead of Multi-level
    # We keep processors minimal since we manually handle features/labels later
    handler_kwargs = {
        "start_time": spec["start_time"],
        "end_time": spec["end_time"],
        "fit_start_time": spec["fit_start_time"],
        "fit_end_time": spec["fit_end_time"],
        "instruments": spec["instruments"],
        "infer_processors": [
            {"class": "Fillna", "kwargs": {}},
        ],
        "learn_processors": [
            {"class": "DropnaLabel"},
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

    data_cfg = config.get("data", {}) or {}
    cfg_source = data_cfg.get("data_source") or data_cfg.get("source")
    env_source = os.environ.get("QLIB_DATA_SOURCE")
    if cfg_source:
        data_source = str(cfg_source).lower()
        if not env_source:
            os.environ["QLIB_DATA_SOURCE"] = data_source
    else:
        data_source = (env_source or "qlib").lower()
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

    # Workaround for flat columns: manually prepare data and train
    # Get train data
    print("[DEBUG] Preparing train segment...")
    train_df = dataset.prepare("train")
    print(f"[DEBUG] Train raw shape: {train_df.shape}")

    print("[DEBUG] Preparing valid segment...")
    valid_df = dataset.prepare("valid")
    print(f"[DEBUG] Valid raw shape: {valid_df.shape}")
    print(f"[DEBUG] Valid date range: {valid_df.index.get_level_values(0).min() if len(valid_df) > 0 else 'N/A'} to {valid_df.index.get_level_values(0).max() if len(valid_df) > 0 else 'N/A'}")

    print("[DEBUG] Preparing test segment...")
    test_df = dataset.prepare("test")
    print(f"[DEBUG] Test raw shape: {test_df.shape}")
    print(f"[DEBUG] Test date range: {test_df.index.get_level_values(0).min() if len(test_df) > 0 else 'N/A'} to {test_df.index.get_level_values(0).max() if len(test_df) > 0 else 'N/A'}")

    # Split features and labels
    # The last column is the label, all others are features
    label_col = train_df.columns[-1]  # "Ref($close, -1) / $close - 1"
    feature_cols = train_df.columns[:-1]

    X_train = train_df[feature_cols]
    y_train = train_df[label_col]
    X_valid = valid_df[feature_cols]
    y_valid = valid_df[label_col]
    X_test = test_df[feature_cols]
    y_test = test_df[label_col]

    print(f"[train-model] Train: X={X_train.shape}, y={y_train.shape}")
    print(f"[train-model] Valid: X={X_valid.shape}, y={y_valid.shape}")
    print(f"[train-model] Test: X={X_test.shape}, y={y_test.shape}")

    # Train the model directly with prepared data
    from lightgbm import LGBMRegressor
    lgb_params = model_cfg.get("kwargs", {})
    lgb_model = LGBMRegressor(**lgb_params)

    # Only use eval_set if validation data is not empty
    fit_params = {}
    if len(X_valid) > 0:
        fit_params["eval_set"] = [(X_valid, y_valid)]
        fit_params["eval_metric"] = "l2"

    lgb_model.fit(X_train, y_train, **fit_params)

    # Predict on test set (or train set if test is empty)
    if len(X_test) > 0:
        pred = lgb_model.predict(X_test)
        pred_df = pd.DataFrame({"score": pred}, index=X_test.index)
        print(f"[train-model] Predictions made on test set")
    else:
        print(f"[WARN] Test set is empty, using train set for predictions")
        pred = lgb_model.predict(X_train)
        pred_df = pd.DataFrame({"score": pred}, index=X_train.index)

    pred_path.parent.mkdir(parents=True, exist_ok=True)
    pred_df.to_pickle(pred_path)

    # Extract instruments from MultiIndex
    if isinstance(pred_df.index, pd.MultiIndex):
        instruments = sorted(pred_df.index.get_level_values(-1).unique().tolist())
    else:
        instruments = []

    metrics = {
        "placeholder": False,
        "rows": int(len(pred_df)),
        "instruments": instruments[:10],  # Limit to first 10 for display
    }
    metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False))
    print(f"[train-model] trained via qlib, predictions saved to {pred_path}")
    print(f"[train-model] {len(instruments)} instruments, {len(pred_df)} predictions")


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


def log_to_mlflow(config: Dict[str, object], metrics_path: Path) -> None:
    """Log metrics to MLflow if enabled via environment variable."""

    if not os.environ.get("QLIB_USE_MLFLOW"):
        return

    try:
        import mlflow
    except ImportError:  # pragma: no cover - optional dependency
        print("[train-model] MLflow not available, skipping logging.")
        return

    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI")
    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)

    mlflow_cfg = config.get("mlflow", {}) if isinstance(config.get("mlflow"), dict) else {}
    experiment_name = mlflow_cfg.get("experiment_name", "qlib-workstation")
    mlflow.set_experiment(experiment_name)
    run_name = mlflow_cfg.get("run_name")

    metrics = {}
    if metrics_path.exists():
        metrics = json.loads(metrics_path.read_text() or "{}")

    with mlflow.start_run(run_name=run_name):
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                mlflow.log_metric(key, value)
        if metrics_path.exists():
            mlflow.log_artifact(str(metrics_path))


def run_with_config(config: Dict[str, object], pred_path: Path = PRED_PATH, metrics_path: Path = METRICS_PATH) -> None:
    try:
        _train_with_qlib(config, pred_path, metrics_path)
        log_to_mlflow(config, metrics_path)
    except Exception as exc:  # pragma: no cover
        import traceback
        print(f"[train-model] qlib workflow failed: {exc}")
        print(f"[DEBUG] Full traceback:\n{traceback.format_exc()}")
        print("Using placeholder results instead.")
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
