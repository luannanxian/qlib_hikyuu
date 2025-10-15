#!/usr/bin/env python3
"""Summarise experiment metrics into structured outputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional


def collect_metrics(base: Path) -> List[dict]:
    if not base.exists():
        return []
    entries = []
    for path in base.rglob("metrics.json"):
        with path.open() as fp:
            data = json.load(fp)
        entries.append(
            {
                "experiment": path.parent.name,
                "rows": data.get("rows", 0),
                "instruments": data.get("instruments", []),
                "placeholder": data.get("placeholder", False),
            }
        )
    return entries


def _build_report(metrics: List[dict]) -> Dict[str, object]:
    total = len(metrics)
    success = sum(1 for m in metrics if not m.get("placeholder"))
    instruments = sorted({inst for m in metrics for inst in m.get("instruments", [])})
    total_rows = sum(int(m.get("rows", 0)) for m in metrics)
    return {
        "total_runs": total,
        "successful_runs": success,
        "placeholder_runs": total - success,
        "total_rows": total_rows,
        "unique_instruments": instruments,
        "experiments": [
            {
                "experiment": m["experiment"],
                "rows": m.get("rows", 0),
                "instruments": m.get("instruments", []),
                "placeholder": m.get("placeholder", False),
            }
            for m in metrics
        ],
    }


def _print_table(report: Dict[str, object]) -> None:
    experiments: List[Dict[str, object]] = report["experiments"]  # type: ignore[index]
    if not experiments:
        print("No experiments found.")
        return
    header = "Experiment\tRows\tPlaceholder\tInstruments"
    print(header)
    for item in experiments:
        inst = ",".join(item.get("instruments", []))
        print(
            f"{item['experiment']}\t{item.get('rows', 0)}\t{item.get('placeholder', False)}\t{inst}"
        )


def summarize(
    base: Path = Path("experiments"),
    *,
    output: Optional[Path] = None,
    fmt: str = "table",
) -> None:
    metrics = collect_metrics(base)
    report = _build_report(metrics)

    fmt = fmt.lower()
    if fmt == "json":
        text = json.dumps(report, indent=2, ensure_ascii=False)
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(text, encoding="utf-8")
        else:
            print(text)
        return
    if fmt == "csv":
        lines = ["experiment,rows,placeholder,instruments"]
        for item in report["experiments"]:  # type: ignore[index]
            inst = " ".join(item.get("instruments", []))
            lines.append(
                f"{item['experiment']},{item.get('rows', 0)},{item.get('placeholder', False)},{inst}"
            )
        text = "\n".join(lines)
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(text, encoding="utf-8")
        else:
            print(text)
        return

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    _print_table(report)


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarise experiment metrics.")
    parser.add_argument("--base", type=Path, default=Path("experiments"))
    parser.add_argument("--output", type=Path, help="Optional file to write summary to")
    parser.add_argument(
        "--format",
        choices=("table", "json", "csv"),
        default="table",
        help="Summary output format",
    )
    args = parser.parse_args()

    summarize(args.base, output=args.output, fmt=args.format)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
