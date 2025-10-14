import json
import pickle
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import (
    export_signals,
    generate_features,
    prepare_data,
    render_report,
    review_decision,
    run_backtest,
    summary,
    train_model,
)
from scripts.config_utils import load_yaml


def test_prepare_data_creates_file(tmp_path: Path) -> None:
    output = tmp_path / "prepared.txt"
    prepare_data.run(output)
    assert output.exists()
    assert "Placeholder" in output.read_text()


def test_generate_features_from_template(tmp_path: Path) -> None:
    template = tmp_path / "template.yaml"
    template.write_text(
        """
name: test
frequency: day
indicators:
  - type: EMA
    window: 5
"""
    )
    output = tmp_path / "features.csv"
    generate_features.run_from_config(template, output)
    content = output.read_text().splitlines()
    assert content[0] == "indicator,value"
    assert len(content) == 2


def test_export_signals_from_placeholder(tmp_path: Path) -> None:
    pred_path = tmp_path / "pred.pkl"
    data = [
        {"datetime": "2025-01-01", "instrument": "SH600000", "score": 1.0},
        {"datetime": "2025-01-01", "instrument": "SZ000001", "score": 0.5},
    ]
    with pred_path.open("wb") as fp:
        pickle.dump(data, fp)
    output = tmp_path / "signals.csv"
    export_signals.run(pred_path, output, top_k=1)
    rows = output.read_text().strip().splitlines()
    assert rows[0].startswith("datetime,instrument")
    assert len(rows) == 2  # header + top1


def test_run_backtest_summary(tmp_path: Path) -> None:
    signals = tmp_path / "signals.csv"
    signals.write_text(
        """datetime,instrument,action,weight,score\n2025-01-01,SH600000,buy,0.5,1.0\n2025-01-01,SZ000001,buy,0.5,0.8\n"""
    )
    report = tmp_path / "summary.json"
    run_backtest.run(signals, report)
    data = json.loads(report.read_text())
    assert data["total_signals"] == 2
    assert data["unique_instruments"] == 2


def test_render_report_outputs_html(tmp_path: Path) -> None:
    signals = tmp_path / "signals.csv"
    signals.write_text(
        """datetime,instrument,action,weight,score\n2025-01-01,SH600000,buy,0.5,1.0\n"""
    )
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps({"total_signals": 1}))
    output = tmp_path / "review.html"
    render_report.run(signals, summary_path, output)
    html = output.read_text()
    assert "Strategy Review" in html
    assert "SH600000" in html


def test_review_decision_auto(tmp_path: Path) -> None:
    signals = tmp_path / "signals.csv"
    signals.write_text(
        """datetime,instrument,action,weight,score\n2025-01-01,SH600000,buy,0.5,1.0\n"""
    )
    report = tmp_path / "decision.json"
    approved = tmp_path / "approved.csv"
    result = review_decision.run_review(signals, report, approved, auto=True)
    assert result == 0
    data = json.loads(report.read_text())
    assert data["approved"] == 1
    assert approved.read_text().count("SH600000") == 1


def test_summary_collects_metrics(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    metrics_dir = tmp_path / "experiments" / "run1"
    metrics_dir.mkdir(parents=True)
    (metrics_dir / "metrics.json").write_text(json.dumps({"rows": 10, "instruments": ["A", "B"]}))
    summary.summarize(tmp_path / "experiments")
    out = capsys.readouterr().out
    assert "run1" in out
    assert "10" in out


def test_train_model_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Force qlib training to fail and ensure placeholder runs
    def fake_train(*args, **kwargs):
        raise RuntimeError("fail")

    captured = {}

    def fake_placeholder(pred_path: Path, metrics_path: Path) -> None:
        pred_path.parent.mkdir(parents=True, exist_ok=True)
        metrics_path.write_text(json.dumps({"placeholder": True}))
        captured["done"] = True

    monkeypatch.setattr(train_model, "_train_with_qlib", fake_train)
    monkeypatch.setattr(train_model, "_train_placeholder", fake_placeholder)
    pred = tmp_path / "pred.pkl"
    metrics = tmp_path / "metrics.json"
    train_model.run_with_config({}, pred, metrics)
    assert captured.get("done")
    assert json.loads(metrics.read_text())["placeholder"]


def test_config_utils_load_yaml_fallback(tmp_path: Path) -> None:
    path = tmp_path / "missing.yaml"
    data = load_yaml(path, fallback={"name": "fallback"})
    assert data["name"] == "fallback"
