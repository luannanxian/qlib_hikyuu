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

DEFAULT_SIGNALS = Path("artifacts") / "signals.csv"
DECISION_REPORT = Path("artifacts") / "review_decision.json"
APPROVED_SIGNALS = Path("artifacts") / "approved_signals.csv"


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Review signals and approve or reject them.")
    parser.add_argument("--signals", type=Path, default=DEFAULT_SIGNALS)
    parser.add_argument("--report", type=Path, default=DECISION_REPORT)
    parser.add_argument("--approved", type=Path, default=APPROVED_SIGNALS)
    parser.add_argument("--auto", action="store_true", help="Approve all signals without prompting.")
    args = parser.parse_args()

    if not args.signals.exists():
        print(f"Signals file not found: {args.signals}")
        return 1

    signals = load_signals(args.signals)
    if not signals:
        print("No signals to review.")
        return 0

    if args.auto:
        decisions = [True] * len(signals)
    else:
        decisions = prompt_decision(signals)

    approved_count = save_decision_report(signals, decisions, args.report, args.approved)
    print(f"Approved {approved_count}/{len(signals)} signals. Report saved to {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

