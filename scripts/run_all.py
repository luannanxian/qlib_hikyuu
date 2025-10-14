#!/usr/bin/env python3
"""
Workflow orchestrator for the Hikyuu × Qlib workstation.

This script wires together the placeholder CLI tools to demonstrate an end-to-end
pipeline. It will be extended with real logic in future iterations.
"""

from __future__ import annotations

import argparse
from typing import Callable, Dict, List

import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import check_env, export_signals, prepare_data, run_backtest, train_model

STEP_REGISTRY: Dict[str, Callable[[], None]] = {
    "check": lambda: check_env.main(),
    "prepare": lambda: prepare_data.run(),
    "train": lambda: train_model.run(),
    "signals": lambda: export_signals.run(
        export_signals.DEFAULT_PRED_PATH, export_signals.DEFAULT_OUTPUT_PATH, top_k=3
    ),
    "backtest": lambda: run_backtest.run(
        run_backtest.DEFAULT_SIGNAL_PATH, run_backtest.DEFAULT_REPORT_PATH
    ),
}

DEFAULT_ORDER: List[str] = ["check", "prepare", "train", "signals", "backtest"]


def run_steps(steps: List[str]) -> None:
    for step in steps:
        if step not in STEP_REGISTRY:
            raise ValueError(f"Unknown step: {step}")
        print(f"\n=== Running step: {step} ===")
        STEP_REGISTRY[step]()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run end-to-end workflow.")
    parser.add_argument(
        "--steps",
        nargs="+",
        default=DEFAULT_ORDER,
        help=f"Steps to execute in order (default: {' '.join(DEFAULT_ORDER)})",
    )
    args = parser.parse_args()
    run_steps(args.steps)
    print("\nWorkflow completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
