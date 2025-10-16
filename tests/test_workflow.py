import json
import pickle
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import (
    check_env,
    export_signals,
    generate_features,
    preview_signals,
    prepare_data,
    render_report,
    review_decision,
    run_all,
    run_backtest,
    summary,
    train_model,
)
from scripts.config_utils import load_runtime_config, load_yaml


def test_prepare_data_creates_file(tmp_path: Path) -> None:
    output = tmp_path / "prepared.txt"
    prepare_data.run(output, cache_formats=["csv"])
    assert output.exists()
    content = output.read_text()
    assert content.strip()


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
    assert content
    header = content[0].split(",")
    assert "indicator" in header or "datetime" in header
    assert len(content) >= 2


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


def test_preview_signals_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    signals = tmp_path / "signals.csv"
    signals.write_text(
        """datetime,instrument,action,weight,score
2025-01-01,SH600000,buy,0.5,1.0
2025-01-01,SZ000001,buy,0.5,0.8
2025-01-02,SH600009,sell,0.3,-0.5
"""
    )
    preview_signals.summarize(signals, top=2, by_date=True)
    out = capsys.readouterr().out
    assert "signals:" in out
    assert "top 2 signals" in out


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


def test_load_runtime_config_merge(tmp_path: Path) -> None:
    base = tmp_path / "base.yaml"
    override = tmp_path / "override.yaml"
    base.write_text("run_modes:\n  default: quick\nvalue: 1\n")
    override.write_text("value: 2\nextra: true\n")
    config = load_runtime_config([base, override])
    assert config["run_modes"]["default"] == "quick"
    assert config["value"] == 2
    assert config["extra"] is True


def test_check_env_helpers():
    ok, _ = check_env.check_python()
    assert isinstance(ok, bool)
    ok, _ = check_env.check_env_vars()
    assert isinstance(ok, bool)


def test_run_all_build_registry(tmp_path: Path):
    template = tmp_path / "template.yaml"
    template.write_text("name: t\nfrequency: day\nindicators:\n  - type: EMA\n")
    config = {
        "features": {"template": str(template), "output": str(tmp_path / "features.csv")},
        "signals": {"output": str(tmp_path / "signals.csv"), "top_k": 1},
        "reports": {"summary": str(tmp_path / "summary.json"), "html": str(tmp_path / "review.html")},
        "decision": {"report": str(tmp_path / "decision.json"), "approved": str(tmp_path / "approved.csv"), "auto": True},
        "experiments": {"base": str(tmp_path / "experiments")},
    }
    (tmp_path / "signals.csv").write_text("datetime,instrument,action,weight,score\n2025-01-01,SH600000,buy,1,0.5\n")
    (tmp_path / "summary.json").write_text("{}")
    registry = run_all.build_registry(config)
    assert "decision" in registry
    registry["decision"]()
    assert (tmp_path / "decision.json").exists()


def test_apply_overrides_updates_nested_dict():
    config = {"signals": {"top_k": 3}, "reports": {"summary": "foo"}}
    updated = run_all.apply_overrides(config, ["signals.top_k=5", "new.key='value'"])
    assert updated["signals"]["top_k"] == 5
    assert updated["new"]["key"] == "value"


def test_train_model_honors_config_data_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("QLIB_DATA_SOURCE", raising=False)
    config = {
        "run_modes": {"default": "quick", "supported": ["quick"]},
        "dataset": {
            "quick": {
                "start_time": "2020-01-01",
                "end_time": "2020-12-31",
                "fit_start_time": "2020-01-01",
                "fit_end_time": "2020-06-30",
                "instruments": "csi100",
                "segments": {
                    "train": ["2020-01-01", "2020-06-30"],
                    "valid": ["2020-07-01", "2020-09-30"],
                    "test": ["2020-10-01", "2020-12-31"],
                },
            }
        },
        "data": {"data_source": "hikyuu"},
        "hikyuu": {"instruments": ["SH600000"]},
        "model": {"class": "LGBModel", "module_path": "qlib.contrib.model.gbdt", "kwargs": {}},
    }
    dataset_cfg, _ = train_model._build_dataset_and_model(config)
    handler = dataset_cfg["kwargs"]["handler"]
    assert handler["module_path"] == "hikyuu_integration"


def test_review_decision_manual(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    signals = tmp_path / "signals.csv"
    signals.write_text("datetime,instrument,action,weight,score\n2025-01-01,SH600000,buy,0.5,1.0\n")
    report = tmp_path / "decision.json"
    approved = tmp_path / "approved.csv"
    responses = iter(["n"])
    monkeypatch.setattr("builtins.input", lambda _: next(responses))
    result = review_decision.run_review(signals, report, approved, auto=False)
    assert result == 0
    data = json.loads(report.read_text())
    assert data["approved"] == 0
    assert "SH600000" not in approved.read_text()


def test_log_to_mlflow(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    module = types.SimpleNamespace()
    records = {"metrics": [], "artifacts": []}

    def start_run(**kwargs):
        records["run"] = kwargs.get("run_name")

        class Dummy:
            def __enter__(self_inner):
                return None

            def __exit__(self_inner, exc_type, exc, tb):
                return False

        return Dummy()

    module.set_tracking_uri = lambda uri: records.setdefault("uri", uri)
    module.set_experiment = lambda name: records.setdefault("exp", name)
    module.start_run = start_run
    module.log_metric = lambda key, value: records["metrics"].append((key, value))
    module.log_artifact = lambda path: records["artifacts"].append(Path(path).name)
    monkeypatch.setitem(sys.modules, "mlflow", module)
    monkeypatch.setenv("QLIB_USE_MLFLOW", "1")
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)

    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text(json.dumps({"rows": 5, "placeholder": False}))
    config = {"mlflow": {"experiment_name": "demo", "run_name": "test-run"}}
    train_model.log_to_mlflow(config, metrics_path)
    assert records["exp"] == "demo"
    assert records["run"] == "test-run"
    assert ("metrics.json" in records["artifacts"]) if records["artifacts"] else True
