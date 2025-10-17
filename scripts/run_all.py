#!/usr/bin/env python3
"""Run orchestrated workflow based on configuration."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Callable, Dict, List

import ast

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import (
    check_env,
    export_signals,
    generate_features,
    generate_report,
    compare_reports,
    monitor_metrics,
    prepare_data,
    render_report,
    review_decision,
    run_backtest,
    summary,
    train_model,
)
from scripts.config_utils import load_runtime_config
from scripts.logging_utils import setup_structured_logging

DEFAULT_CONFIGS = [Path("config/base.yaml")]
LOG_PATH = Path("logs") / "run_all.jsonl"


def _set_nested(config: dict, dotted_key: str, value: object) -> None:
    parts = dotted_key.split(".")
    target = config
    for key in parts[:-1]:
        if key not in target or not isinstance(target[key], dict):
            target[key] = {}
        target = target[key]
    target[parts[-1]] = value


def _parse_value(raw: str) -> object:
    try:
        return ast.literal_eval(raw)
    except Exception:
        return raw


def apply_overrides(config: dict, overrides: List[str]) -> dict:
    if not overrides:
        return config

    for item in overrides:
        if "=" not in item:
            logging.warning("Invalid override (missing '='): %s", item)
            continue
        key, raw_value = item.split("=", 1)
        key = key.strip()
        if not key:
            logging.warning("Invalid override key in %s", item)
            continue
        value = _parse_value(raw_value.strip())
        _set_nested(config, key, value)
        logging.info("Override applied: %s=%s", key, value)
    return config


def build_registry(config: dict) -> Dict[str, Callable[[], None]]:
    features_cfg = config.get("features", {})
    template_path = Path(features_cfg.get("template", "config/templates/default_indicators.yaml"))
    output_path = Path(features_cfg.get("output", "features/features.csv"))
    signals_cfg = config.get("signals", {})
    top_k = int(signals_cfg.get("top_k", 3))
    top_k_sell = signals_cfg.get("top_k_sell")
    top_k_sell_value = int(top_k_sell) if top_k_sell is not None else None
    experiments_cfg = config.get("experiments", {})
    experiments_base = Path(experiments_cfg.get("base", "experiments"))
    reports_cfg = config.get("reports", {})
    html_report_path = Path(reports_cfg.get("html", "reports/latest/review.html"))
    summary_json_path = Path(reports_cfg.get("summary", run_backtest.DEFAULT_REPORT_PATH))
    detail_report_cfg = reports_cfg.get("detail")
    if detail_report_cfg:
        detail_report_path = Path(detail_report_cfg)
    else:
        detail_report_path = html_report_path.with_name(f"{html_report_path.stem}_detail{html_report_path.suffix}")
    report_output_path = Path(reports_cfg.get("report", "reports/latest/performance_report.html"))
    benchmark_cfg = reports_cfg.get("benchmark", {})
    benchmark_symbol = benchmark_cfg.get("symbol", run_backtest.DEFAULT_BENCHMARK_SYMBOL)
    benchmark_csv_raw = benchmark_cfg.get("csv")
    benchmark_csv = Path(benchmark_csv_raw) if benchmark_csv_raw else None

    monitor_cfg = config.get("monitor", {})
    monitor_summary = Path(monitor_cfg.get("summary", summary_json_path))
    monitor_metrics_output = Path(monitor_cfg.get("metrics", "experiments/latest/metrics.json"))
    monitor_output = Path(monitor_cfg.get("output", "reports/latest/monitoring.json"))
    monitor_min_signals = monitor_cfg.get("min_signals")
    monitor_min_rows = monitor_cfg.get("min_rows")
    monitor_max_loss = monitor_cfg.get("max_loss")
    monitor_history = Path(monitor_cfg.get("history", "reports/latest/monitoring_history.csv"))
    monitor_chart = Path(monitor_cfg.get("chart", "reports/latest/monitoring_chart.html"))
    monitor_history_limit = int(monitor_cfg.get("history_limit", 100))

    compare_cfg = config.get("compare", {})
    baseline_summary = compare_cfg.get("baseline")
    compare_output = Path(compare_cfg.get("output", "reports/latest/compare.csv"))
    baseline_path = Path(baseline_summary) if baseline_summary else None

    decision_cfg = config.get("decision", {})
    decision_report = Path(decision_cfg.get("report", "artifacts/review_decision.json"))
    decision_output = Path(decision_cfg.get("approved", "artifacts/approved_signals.csv"))
    decision_auto = bool(decision_cfg.get("auto", False))
    decision_confirm = bool(decision_cfg.get("require_confirm", not decision_auto))

    def _decision_step() -> None:
        code = review_decision.run_review(
            Path(signals_cfg.get("output", export_signals.DEFAULT_OUTPUT_PATH)),
            decision_report,
            decision_output,
            decision_auto,
            summary_path=summary_json_path,
            require_confirm=decision_confirm,
        )
        if code != 0:
            raise SystemExit(code)

    def _compare_step() -> None:
        if baseline_path is None:
            logging.info("Compare step skipped: baseline not configured.")
            return
        if not baseline_path.exists():
            logging.warning("Baseline summary not found: %s", baseline_path)
            return
        compare_reports.run(baseline_path, summary_json_path, compare_output)

    registry = {
        "check": lambda: check_env.main(),
        "prepare": lambda: prepare_data.run(),
        "train": lambda: train_model.run_with_config(config),
        "features": lambda: generate_features.run_from_config(template_path, output_path),
        "signals": lambda: export_signals.run(
            export_signals.DEFAULT_PRED_PATH,
            Path(signals_cfg.get("output", export_signals.DEFAULT_OUTPUT_PATH)),
            top_k,
            top_k_sell=top_k_sell_value,
        ),
        "backtest": lambda: run_backtest.run(
            Path(signals_cfg.get("output", export_signals.DEFAULT_OUTPUT_PATH)),
            summary_json_path,
            benchmark_symbol=benchmark_symbol,
            benchmark_csv=benchmark_csv,
        ),
        "summary": lambda: summary.summarize(experiments_base),
        "review": lambda: render_report.run(
            Path(signals_cfg.get("output", export_signals.DEFAULT_OUTPUT_PATH)),
            summary_json_path,
            html_report_path,
            detail_report_path,
        ),
        "report": lambda: generate_report.run(
            summary_json_path,
            Path(signals_cfg.get("output", export_signals.DEFAULT_OUTPUT_PATH)),
            report_output_path,
            detail_link=os.path.relpath(detail_report_path, report_output_path.parent),
            summary_link=os.path.relpath(html_report_path, report_output_path.parent),
        ),
        "monitor": lambda: monitor_metrics.collect_metrics(
            summary_path=monitor_summary,
            metrics_path=monitor_metrics_output,
            output_path=monitor_output,
            min_signals=monitor_min_signals,
            min_rows=monitor_min_rows,
            max_loss=monitor_max_loss,
            history_path=monitor_history,
            history_limit=monitor_history_limit,
            chart_path=monitor_chart,
        ),
        "decision": _decision_step,
    }
    if baseline_path is not None:
        registry["compare"] = _compare_step
    return registry


def main() -> int:
    parser = argparse.ArgumentParser(description="Run workflow steps")
    parser.add_argument("--steps", nargs="+", help="Ordered list of steps to run")
    parser.add_argument(
        "--config",
        nargs="+",
        default=DEFAULT_CONFIGS,
        type=Path,
        help="Configuration files (yaml or json)",
    )
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--set",
        dest="overrides",
        action="append",
        default=[],
        help="Override configuration values, e.g. --set signals.top_k=5",
    )
    args = parser.parse_args()

    setup_structured_logging("run_all", verbose=args.verbose, log_file=LOG_PATH)
    logging.info("Loading configuration from %s", args.config)
    config = load_runtime_config([Path(p) for p in args.config])
    config = apply_overrides(config, args.overrides)
    registry = build_registry(config)
    steps = args.steps or config.get("workflow", {}).get("steps", list(registry.keys()))

    for step in steps:
        if step not in registry:
            logging.error("Unknown step: %s", step)
            raise SystemExit(1)
        logging.info("Running step: %s", step)
        registry[step]()

    logging.info("Workflow completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
