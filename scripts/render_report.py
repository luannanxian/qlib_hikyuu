#!/usr/bin/env python3
"""Render a simple HTML report combining signals and backtest summary."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

DEFAULT_SIGNALS = Path("artifacts") / "signals.csv"
DEFAULT_SUMMARY = Path("reports") / "latest" / "backtest_summary.json"
DEFAULT_OUTPUT = Path("reports") / "latest" / "review.html"


def load_signals(path: Path) -> list[dict]:
    if not path.exists():
        print(f"[render-report] signals file missing: {path}")
        return []
    with path.open() as fp:
        reader = csv.DictReader(fp)
        return list(reader)


def load_summary(path: Path) -> dict:
    if not path.exists():
        print(f"[render-report] summary file missing: {path}")
        return {}
    return json.loads(path.read_text())


def render_html(signals: list[dict], summary: dict) -> str:
    rows_html = "".join(
        f"<tr><td>{row['datetime']}</td><td>{row['instrument']}</td><td>{row['action']}</td><td>{row['weight']}</td><td>{row['score']}</td></tr>"
        for row in signals
    )
    if not rows_html:
        rows_html = "<tr><td colspan='5'>No signals available</td></tr>"

    summary_html = "".join(
        f"<li><strong>{key}</strong>: {value}</li>" for key, value in summary.items()
    ) or "<li>No summary metrics.</li>"

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <title>Hikyuu × Qlib Review</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 2rem; }}
        table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
        th, td {{ border: 1px solid #ccc; padding: 0.5rem; text-align: left; }}
        th {{ background: #f5f5f5; }}
    </style>
</head>
<body>
    <h1>Strategy Review</h1>
    <h2>Summary</h2>
    <ul>{summary_html}</ul>
    <h2>Signals</h2>
    <table>
        <thead>
            <tr><th>Date</th><th>Instrument</th><th>Action</th><th>Weight</th><th>Score</th></tr>
        </thead>
        <tbody>{rows_html}</tbody>
    </table>
</body>
</html>
"""


def run(signals_path: Path, summary_path: Path, output_path: Path) -> None:
    signals = load_signals(signals_path)
    summary = load_summary(summary_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    html = render_html(signals, summary)
    output_path.write_text(html, encoding="utf-8")
    print(f"[render-report] wrote {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Render HTML review report")
    parser.add_argument("--signals", type=Path, default=DEFAULT_SIGNALS)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    run(args.signals, args.summary, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
