#!/usr/bin/env python3
"""Collect monitoring metrics, persist history, render charts, and surface alerts."""

from __future__ import annotations

import argparse
import csv
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

from .logging_utils import setup_structured_logging

DEFAULT_SUMMARY = Path("reports") / "latest" / "backtest_summary.json"
DEFAULT_METRICS = Path("experiments") / "latest" / "metrics.json"
DEFAULT_OUTPUT = Path("reports") / "latest" / "monitoring.json"
DEFAULT_HISTORY = Path("reports") / "latest" / "monitoring_history.csv"
DEFAULT_CHART = Path("reports") / "latest" / "monitoring_chart.html"
DEFAULT_HISTORY_LIMIT = 50
HISTORY_FIELDS = ("timestamp", "signals", "rows", "loss", "violations")

LOGGER = setup_structured_logging("monitor.metrics")


def _load_json(path: Path) -> Dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # pragma: no cover
        raise ValueError(f"Failed to parse JSON from {path}: {exc}") from exc


def _update_history(
    report: Dict[str, object],
    history_path: Path,
    history_limit: int,
    timestamp: Optional[str],
    logger: logging.Logger,
) -> List[Dict[str, object]]:
    """Persist monitoring history in CSV format and return typed entries."""
    history_limit = max(history_limit, 1) if history_limit else 0
    history_path.parent.mkdir(parents=True, exist_ok=True)

    existing: List[Dict[str, str]] = []
    if history_path.exists():
        try:
            with history_path.open("r", encoding="utf-8", newline="") as fp:
                reader = csv.DictReader(fp)
                for row in reader:
                    existing.append({k: row.get(k, "") for k in HISTORY_FIELDS})
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to read monitoring history %s: %s", history_path, exc)
            existing = []

    record_timestamp = timestamp or datetime.utcnow().isoformat(timespec="seconds")
    loss_value = report.get("loss")
    record = {
        "timestamp": record_timestamp,
        "signals": str(report.get("signals", "")),
        "rows": str(report.get("rows", "")),
        "loss": "" if loss_value is None else str(loss_value),
        "violations": str(len(report.get("violations") or [])),
    }
    combined = (existing + [record]) if history_limit else existing + [record]
    if history_limit:
        combined = combined[-history_limit:]

    with history_path.open("w", encoding="utf-8", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=HISTORY_FIELDS)
        writer.writeheader()
        writer.writerows(combined)

    typed_history: List[Dict[str, object]] = []
    for entry in combined:
        typed_history.append(
            {
                "timestamp": entry["timestamp"],
                "signals": int(entry["signals"]) if entry["signals"] else 0,
                "rows": int(entry["rows"]) if entry["rows"] else 0,
                "loss": float(entry["loss"]) if entry["loss"] not in ("", None) else None,
                "violations": int(entry["violations"]) if entry["violations"] else 0,
            }
        )

    return typed_history


def _render_chart(history: List[Dict[str, object]], chart_path: Path, chart_title: str) -> None:
    """Render a lightweight HTML chart for collected metrics."""
    if not history:
        return
    chart_path.parent.mkdir(parents=True, exist_ok=True)
    chart_data = json.dumps(history, ensure_ascii=False)
    table_rows = "\n".join(
        f"<tr><td>{entry['timestamp']}</td>"
        f"<td>{entry['signals']}</td>"
        f"<td>{entry['rows']}</td>"
        f"<td>{'' if entry['loss'] is None else entry['loss']}</td>"
        f"<td>{entry['violations']}</td></tr>"
        for entry in history
    )
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>{chart_title}</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js" integrity="sha384-Vd0iIdYvMS5XeW0RP4m71XxDtlzP40mUoLju94AgwhTkOyxrojoyTaJKe+UawnlP" crossorigin="anonymous"></script>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 1.5rem; }}
    h1 {{ font-size: 1.5rem; margin-bottom: 1rem; }}
    canvas {{ max-width: 960px; margin-bottom: 1.5rem; }}
    table {{ border-collapse: collapse; }}
    th, td {{ border: 1px solid #ccc; padding: 0.4rem 0.6rem; text-align: right; }}
    th:first-child, td:first-child {{ text-align: left; }}
  </style>
</head>
<body>
  <h1>{chart_title}</h1>
  <canvas id="monitorChart" height="320"></canvas>
  <script>
    const history = {chart_data};
    const labels = history.map(item => item.timestamp);
    const hasLoss = history.some(item => item.loss !== null);
    const chart = new Chart(
      document.getElementById("monitorChart").getContext("2d"),
      {{
        type: "line",
        data: {{
          labels,
          datasets: [
            {{
              label: "Signals",
              data: history.map(item => item.signals),
              borderColor: "#1f77b4",
              tension: 0.2,
              fill: false,
            }},
            {{
              label: "Rows",
              data: history.map(item => item.rows),
              borderColor: "#2ca02c",
              tension: 0.2,
              fill: false,
            }},
            {{
              label: "Violations",
              data: history.map(item => item.violations),
              borderColor: "#d62728",
              tension: 0.2,
              fill: false,
            }},
          ].concat(
            hasLoss
              ? [
                  {{
                    label: "Loss",
                    data: history.map(item => item.loss),
                    borderColor: "#ff7f0e",
                    tension: 0.2,
                    fill: false,
                    yAxisID: "yLoss",
                  }}
                ]
              : []
          ),
        }},
        options: {{
          responsive: true,
          interaction: {{
            mode: "index",
            intersect: false,
          }},
          stacked: false,
          scales: {{
            y: {{
              beginAtZero: true,
              title: {{
                display: true,
                text: "Count",
              }},
            }},
            yLoss: {{
              beginAtZero: true,
              position: "right",
              title: {{
                display: true,
                text: "Loss",
              }},
              grid: {{
                drawOnChartArea: false,
              }},
            }},
          }},
        }},
      }}
    );
  </script>
  <table>
    <thead>
      <tr><th>Timestamp</th><th>Signals</th><th>Rows</th><th>Loss</th><th>Violations</th></tr>
    </thead>
    <tbody>
      {table_rows}
    </tbody>
  </table>
</body>
</html>
"""
    chart_path.write_text(html, encoding="utf-8")


def collect_metrics(
    summary_path: Path = DEFAULT_SUMMARY,
    metrics_path: Path = DEFAULT_METRICS,
    output_path: Optional[Path] = DEFAULT_OUTPUT,
    min_signals: Optional[int] = None,
    min_rows: Optional[int] = None,
    max_loss: Optional[float] = None,
    history_path: Optional[Path] = DEFAULT_HISTORY,
    history_limit: int = DEFAULT_HISTORY_LIMIT,
    chart_path: Optional[Path] = DEFAULT_CHART,
    chart_title: str = "Monitoring History",
    timestamp: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
) -> Dict[str, object]:
    logger = logger or LOGGER

    summary = _load_json(summary_path)
    metrics = _load_json(metrics_path)

    signals = int(summary.get("total_signals", 0))
    unique_instruments = summary.get("unique_instruments") or []
    unique_dates = int(summary.get("unique_dates", 0))
    average_weight = summary.get("average_weight")

    rows = int(metrics.get("rows", 0))
    placeholder = bool(metrics.get("placeholder", False))
    loss = metrics.get("loss")
    if isinstance(loss, str):
        try:
            loss = float(loss)
        except ValueError:
            loss = None

    report = {
        "summary_path": str(summary_path),
        "metrics_path": str(metrics_path),
        "signals": signals,
        "unique_instruments": unique_instruments,
        "unique_dates": unique_dates,
        "average_weight": average_weight,
        "rows": rows,
        "placeholder": placeholder,
        "loss": loss,
        "violations": [],
    }

    if min_signals is not None and signals < min_signals:
        report["violations"].append({
            "type": "min_signals",
            "expected": min_signals,
            "actual": signals,
        })
    if min_rows is not None and rows < min_rows:
        report["violations"].append({
            "type": "min_rows",
            "expected": min_rows,
            "actual": rows,
        })
    if max_loss is not None and loss is not None and loss > max_loss:
        report["violations"].append({
            "type": "max_loss",
            "expected": max_loss,
            "actual": loss,
        })

    # Persist when requested
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    history = None
    if history_path:
        history = _update_history(report, history_path, history_limit, timestamp, logger)

    if chart_path and history:
        _render_chart(history, chart_path, chart_title)

    if report["violations"]:
        for violation in report["violations"]:
            logger.warning(
                "Monitoring violation type=%s expected=%s actual=%s",
                violation.get("type"),
                violation.get("expected"),
                violation.get("actual"),
            )
        logger.warning(
            "Violations detected for metrics summary=%s metrics=%s",
            summary_path,
            metrics_path,
        )
    else:
        logger.info(
            "Monitoring metrics collected",
            extra={
                "signals": signals,
                "rows": rows,
                "loss": loss,
                "unique_instruments": len(unique_instruments),
            },
        )

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect monitoring metrics and check thresholds")
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--min-signals", type=int)
    parser.add_argument("--min-rows", type=int)
    parser.add_argument("--max-loss", type=float)
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    parser.add_argument("--history-limit", type=int, default=DEFAULT_HISTORY_LIMIT)
    parser.add_argument("--chart", type=Path, default=DEFAULT_CHART)
    parser.add_argument("--chart-title", type=str, default="Monitoring History")
    args = parser.parse_args()

    report = collect_metrics(
        summary_path=args.summary,
        metrics_path=args.metrics,
        output_path=args.output,
        min_signals=args.min_signals,
        min_rows=args.min_rows,
        max_loss=args.max_loss,
        history_path=args.history,
        history_limit=args.history_limit,
        chart_path=args.chart,
        chart_title=args.chart_title,
    )

    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["violations"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
