#!/usr/bin/env python3
"""
CLI tool to review signals and produce a decision summary.

This script allows the user to inspect the generated signals, accept or reject
individual recommendations, and produce a trimmed signal file for further use.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Optional

DEFAULT_SIGNALS = Path("artifacts") / "signals.csv"
DECISION_REPORT = Path("artifacts") / "review_decision.json"
APPROVED_SIGNALS = Path("artifacts") / "approved_signals.csv"
SUMMARY_DEFAULT = Path("reports") / "latest" / "backtest_summary.json"


def load_signals(path: Path):
    with path.open() as fp:
        reader = csv.DictReader(fp)
        return list(reader)


def prompt_decision(signals):
    decisions = []
    for row in signals:
        print(
            f"Date: {row['datetime']}, Instrument: {row['instrument']}, "
            f"Score: {row['score']}, Action: {row['action']}, Weight: {row['weight']}"
        )
        while True:
            answer = input("Accept this signal? [y/n] (default y): ").strip().lower()
            if answer in {"", "y", "n"}:
                break
            print("Please enter y, n, or press Enter for default (y).")
        decisions.append(answer != "n")
    return decisions


def _print_summary(summary_path: Optional[Path]) -> None:
    if not summary_path or not summary_path.exists():
        return
    try:
        data = json.loads(summary_path.read_text())
    except Exception as exc:  # pragma: no cover
        print(f"[review-decision] failed to read summary {summary_path}: {exc}")
        return
    print("\n=== Backtest Summary ===")
    for key, value in data.items():
        if isinstance(value, (int, float, str)):
            print(f"{key}: {value}")
        elif isinstance(value, list):
            print(f"{key}: {len(value)} items")
        else:
            print(f"{key}: {value}")
    print("========================\n")


def _prompt_continue() -> bool:
    while True:
        answer = input("继续逐条审核调仓信号？[Y/n] ").strip().lower()
        if answer in {"", "y", "n"}:
            return answer != "n"
        print("请输入 y 或 n (默认 y)。")


def save_decision_report(signals, decisions, report_path: Path, approved_path: Path):
    approved_rows = [row for row, decision in zip(signals, decisions) if decision]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            {
                "total_signals": len(signals),
                "approved": len(approved_rows),
                "rejected": len(signals) - len(approved_rows),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    with approved_path.open("w", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=["datetime", "instrument", "action", "weight", "score"])
        writer.writeheader()
        writer.writerows(approved_rows)
    return len(approved_rows)


def run_review(
    signals_path: Path = DEFAULT_SIGNALS,
    report_path: Path = DECISION_REPORT,
    approved_path: Path = APPROVED_SIGNALS,
    auto: bool = False,
    summary_path: Optional[Path] = None,
    require_confirm: bool = False,
) -> int:
    if not signals_path.exists():
        print(f"Signals file not found: {signals_path}")
        return 1

    signals = load_signals(signals_path)
    if not signals:
        print("No signals to review.")
        return 0

    _print_summary(summary_path)
    if require_confirm and not auto:
        if not _prompt_continue():
            print("用户取消执行调仓确认。")
            return 1

    decisions = [True] * len(signals) if auto else prompt_decision(signals)

    approved_count = save_decision_report(signals, decisions, report_path, approved_path)
    print(f"Approved {approved_count}/{len(signals)} signals. Report saved to {report_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Review signals and approve or reject them.")
    parser.add_argument("--signals", type=Path, default=DEFAULT_SIGNALS)
    parser.add_argument("--report", type=Path, default=DECISION_REPORT)
    parser.add_argument("--approved", type=Path, default=APPROVED_SIGNALS)
    parser.add_argument("--auto", action="store_true", help="Approve all signals without prompting.")
    parser.add_argument("--summary", type=Path, default=SUMMARY_DEFAULT, help="Backtest summary JSON for overview")
    parser.add_argument("--confirm", action="store_true", help="在审核前要求确认")
    args = parser.parse_args()
    return run_review(
        args.signals,
        args.report,
        args.approved,
        args.auto,
        summary_path=args.summary,
        require_confirm=args.confirm,
    )


if __name__ == "__main__":
    raise SystemExit(main())
