"""Utility package exporting workflow scripts."""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "check_env",
    "prepare_data",
    "train_model",
    "generate_features",
    "export_signals",
    "run_backtest",
    "render_report",
    "review_decision",
    "run_all",
    "summary",
    "monitor_metrics",
    "generate_report",
    "compare_reports",
]


def __getattr__(name: str) -> Any:
    if name in __all__:
        module = importlib.import_module(f".{name}", __name__)
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
