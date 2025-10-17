#!/usr/bin/env python3
"""Train model using Qlib configuration with graceful fallback."""

from __future__ import annotations

import argparse
import json
import os
import pickle
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
import logging

from scripts.config_utils import load_runtime_config

try:  # pragma: no cover - import guard for environments缺少 qlib
    import qlib
    from qlib.constant import REG_CN
    from qlib.utils import init_instance_by_config
except Exception:  # noqa: BLE001
    qlib = None  # type: ignore

try:  # pragma: no cover - optional dependency for Hikyuu training
    from lightgbm import LGBMRegressor
except Exception:  # noqa: BLE001
    LGBMRegressor = None  # type: ignore[assignment]

try:  # pragma: no cover - fallback estimator
    from sklearn.linear_model import Ridge
except Exception:  # noqa: BLE001
    Ridge = None  # type: ignore[assignment]


LOGGER = logging.getLogger("train-model")

EXPERIMENT_DIR = Path("experiments") / "latest"
PRED_PATH = EXPERIMENT_DIR / "pred.pkl"
METRICS_PATH = EXPERIMENT_DIR / "metrics.json"
DEFAULT_CONFIG = Path("config/base.yaml")
HIKYUU_CACHE_PATH = EXPERIMENT_DIR / "hikyuu_cache.pkl"


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


def _build_dataset_and_model(config: Dict[str, object]) -> Tuple[Dict[str, object], Dict[str, object], str]:
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
    return dataset_config, model_config, data_source


def _split_features_labels(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
    label_col: Optional[str] = None
    for col in df.columns:
        if str(col).upper().startswith("LABEL"):
            label_col = col
            break
    if label_col is None:
        raise ValueError("Hikyuu handler输出缺少 LABEL 列，无法训练模型")
    features = df.drop(columns=[label_col])
    if features.empty:
        raise ValueError("特征列为空，无法训练模型")
    return features, df[label_col]


def _prepare_segment(dataset, segment: str) -> Optional[Tuple[pd.MultiIndex, pd.DataFrame, pd.Series]]:
    try:
        df = dataset.prepare(segment)
    except Exception:
        return None
    if df is None or df.empty:
        return None
    df = df.sort_index()
    features, labels = _split_features_labels(df)
    return df.index, features, labels


def _map_lgbm_params(raw: Dict[str, object]) -> Dict[str, object]:
    params = raw.copy()
    loss = params.pop("loss", None)
    if loss:
        params.setdefault("objective", loss)
    if "lambda_l1" in params:
        params["reg_alpha"] = params.pop("lambda_l1")
    if "lambda_l2" in params:
        params["reg_lambda"] = params.pop("lambda_l2")
    params.setdefault("objective", "regression")
    params.setdefault("learning_rate", 0.05)
    params.setdefault("n_estimators", 500)
    params.setdefault("subsample", 0.9)
    params.setdefault("colsample_bytree", 0.8)
    params.setdefault("num_leaves", 96)
    return params


def _train_with_hikyuu_dataset(
    dataset_cfg: Dict[str, object],
    model_cfg: Dict[str, object],
    pred_path: Path,
    metrics_path: Path,
) -> None:
    dataset = init_instance_by_config(dataset_cfg)
    segments = {
        "train": _prepare_segment(dataset, "train"),
        "valid": _prepare_segment(dataset, "valid"),
        "test": _prepare_segment(dataset, "test"),
    }
    train_seg = segments.get("train")
    if train_seg is None:
        raise ValueError("Hikyuu 训练数据为空，请检查配置中的时间区间与标的。")
    valid_seg = segments.get("valid")
    test_seg = segments.get("test") or valid_seg
    if test_seg is None:
        raise ValueError("未找到可用于预测的验证/测试集数据。")

    train_index, train_x, train_y = train_seg
    # Persist raw Hikyuu dataset for downstream reuse (e.g., feature generation)
    handler_cfg = dataset_cfg.get("kwargs", {}).get("handler", {})
    if handler_cfg.get("module_path") == "hikyuu_integration":
        loader = getattr(dataset.handler, "data_loader", None)
        handler_kwargs = handler_cfg.get("kwargs", {})
        instruments = handler_kwargs.get("instruments") or []
        start_time = handler_kwargs.get("start_time")
        end_time = handler_kwargs.get("end_time")
        if loader is not None and hasattr(loader, "load"):
            try:
                raw_df = loader.load(instruments, start_time, end_time)
                HIKYUU_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
                raw_df.to_pickle(HIKYUU_CACHE_PATH)
                LOGGER.info("Cached Hikyuu dataset to %s", HIKYUU_CACHE_PATH)
            except Exception as exc:  # pragma: no cover
                LOGGER.warning("Failed to cache Hikyuu dataset: %s", exc)
    estimator_name = "Ridge"
    raw_params = model_cfg.get("kwargs", {})
    use_lightgbm = raw_params.get("use_lightgbm", True)
    if LGBMRegressor is not None and use_lightgbm:
        lgbm_params = _map_lgbm_params(raw_params)
        model = LGBMRegressor(**lgbm_params)
        estimator_name = "LightGBM"
        try:
            model.fit(train_x, train_y)
        except Exception:
            model = None
    else:
        model = None

    if model is None:
        if Ridge is None:
            raise ImportError("sklearn 未安装，无法训练回归模型。请先安装 scikit-learn。")
        alpha = float(raw_params.get("alpha", 1.0))
        model = Ridge(alpha=alpha, fit_intercept=True, random_state=42)
        estimator_name = "Ridge"
        model.fit(train_x, train_y)

    def _rmse(y_true: pd.Series, y_pred: np.ndarray) -> float:
        if len(y_true) == 0:
            return float("nan")
        return float(np.sqrt(np.mean(np.square(y_true.to_numpy() - y_pred))))

    train_pred = model.predict(train_x)
    train_rmse = _rmse(train_y, train_pred)

    needs_fallback = (
        estimator_name == "LightGBM"
        and (np.isnan(train_rmse) or train_rmse == 0.0 or np.allclose(train_pred, train_pred[:1]))
    )
    if needs_fallback:
        if Ridge is None:
            raise RuntimeError("LightGBM 输出恒定，但 scikit-learn 不可用，无法回退训练。")
        model = Ridge(alpha=float(raw_params.get("alpha", 1.0)), fit_intercept=True, random_state=42)
        estimator_name = "Ridge"
        model.fit(train_x, train_y)
        train_pred = model.predict(train_x)
        train_rmse = _rmse(train_y, train_pred)

    valid_rmse = None
    valid_rows = 0
    if valid_seg is not None:
        _, valid_x, valid_y = valid_seg
        valid_pred = model.predict(valid_x)
        valid_rmse = _rmse(valid_y, valid_pred)
        valid_rows = int(len(valid_y))

    test_index, test_x, _ = test_seg
    test_pred = model.predict(test_x)
    pred_df = pd.DataFrame(test_pred, index=test_index, columns=["score"])
    pred_path.parent.mkdir(parents=True, exist_ok=True)
    pred_df.to_pickle(pred_path)

    instruments = sorted(pred_df.index.get_level_values(-1).unique())
    metrics = {
        "placeholder": False,
        "rows": int(len(pred_df)),
        "instruments": instruments,
        "train_rows": int(len(train_x)),
        "train_rmse": train_rmse,
        "valid_rows": valid_rows,
        "valid_rmse": valid_rmse,
        "estimator": estimator_name,
    }
    metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False))
    print(f"[train-model] trained via Hikyuu + {estimator_name}，预测已保存至 {pred_path}")


def _train_with_qlib(config: Dict[str, object], pred_path: Path, metrics_path: Path) -> None:
    if qlib is None:
        raise ImportError("qlib is not installed in the current environment")

    provider_uri = os.path.expanduser(config.get("data", {}).get("provider_uri", "~/.qlib/qlib_data/cn_data"))
    qlib.init(provider_uri=provider_uri, region=REG_CN, expression_cache=None, dataset_cache=None)

    dataset_cfg, model_cfg, data_source = _build_dataset_and_model(config)
    if data_source == "hikyuu":
        return _train_with_hikyuu_dataset(dataset_cfg, model_cfg, pred_path, metrics_path)

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
