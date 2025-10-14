#!/usr/bin/env python3
"""Run orchestrated workflow based on configuration."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Callable, Dict, List

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import (
    check_env,
    export_signals,
    generate_features,
    prepare_data,
    render_report,
    review_decision,
    run_backtest,
    summary,
    train_model,
)
from scripts.config_utils import load_runtime_config

DEFAULT_CONFIGS = [Path("config/base.yaml")]
LOG_PATH = Path("logs") / "workflow.log"


def setup_logging(verbose: bool) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    handlers = [logging.FileHandler(LOG_PATH, mode="a", encoding="utf-8")]
    if verbose:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
    )


def build_registry(config: dict) -> Dict[str, Callable[[], None]]:
    features_cfg = config.get("features", {})
    template_path = Path(features_cfg.get("template", "config/templates/default_indicators.yaml"))
    output_path = Path(features_cfg.get("output", "features/features.csv"))
    signals_cfg = config.get("signals", {})
    top_k = int(signals_cfg.get("top_k", 3))
    experiments_cfg = config.get("experiments", {})
    experiments_base = Path(experiments_cfg.get("base", "experiments"))
    reports_cfg = config.get("reports", {})
    html_report_path = Path(reports_cfg.get("html", "reports/latest/review.html"))

    decision_cfg = config.get("decision", {})
    decision_report = Path(decision_cfg.get("report", "artifacts/review_decision.json"))
    decision_output = Path(decision_cfg.get("approved", "artifacts/approved_signals.csv"))
    decision_auto = bool(decision_cfg.get("auto", False))

    return {
        "check": lambda: check_env.main(),
        "prepare": lambda: prepare_data.run(),
        "train": lambda: train_model.run_with_config(config),
        "features": lambda: generate_features.run_from_config(template_path, output_path),
        "signals": lambda: export_signals.run(
            export_signals.DEFAULT_PRED_PATH,
            Path(signals_cfg.get("output", export_signals.DEFAULT_OUTPUT_PATH)),
            top_k,
        ),
        "backtest": lambda: run_backtest.run(
            Path(signals_cfg.get("output", export_signals.DEFAULT_OUTPUT_PATH)),
            Path(config.get("reports", {}).get("summary", run_backtest.DEFAULT_REPORT_PATH)),
        ),
        "summary": lambda: summary.summarize(experiments_base),
        "review": lambda: render_report.run(
            Path(signals_cfg.get("output", export_signals.DEFAULT_OUTPUT_PATH)),
            Path(reports_cfg.get("summary", run_backtest.DEFAULT_REPORT_PATH)),
            html_report_path,
        ),
        "decision": lambda: review_decision.run_review(
            Path(signals_cfg.get("output", export_signals.DEFAULT_OUTPUT_PATH)),
            decision_report,
            decision_output,
            decision_auto,
        ),
    }


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
    args = parser.parse_args()

    setup_logging(args.verbose)
    logging.info("Loading configuration from %s", args.config)
    config = load_runtime_config([Path(p) for p in args.config])
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
