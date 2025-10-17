import csv
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
    compat_check,
    compare_reports,
    export_signals,
    generate_features,
    generate_report,
    monitor_metrics,
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
    versioned = list(output.parent.glob("features_v*.csv"))
    assert versioned
    manifest = output.with_suffix(".csv.versions.json")
    assert manifest.exists()


def test_generate_features_uses_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import pandas as pd

    cache_path = tmp_path / "cache.pkl"
    dates = pd.date_range("2025-01-01", periods=4, freq="D")
    instruments = ["AAA", "BBB"]
    index = pd.MultiIndex.from_product([dates, instruments], names=["datetime", "instrument"])
    df = pd.DataFrame(
        {
            ("feature", "CLOSE"): range(len(index)),
            ("feature", "VOLUME"): [100, 200] * 4,
            ("label", "LABEL0"): [0.1] * len(index),
        },
        index=index,
    )
    df.to_pickle(cache_path)
    monkeypatch.setattr(generate_features, "HIKYUU_CACHE_PATH", cache_path)

    template = tmp_path / "template.yaml"
    template.write_text(
        """
name: cache_test
frequency: day
instruments:
  - AAA
  - BBB
start: "2025-01-01"
end: "2025-01-04"
indicators:
  - name: close_sma_2
    type: SMA
    field: $close
    window: 2
  - name: custom_expr
    expression: "EMA($close, 2) - Ref($close, 1)"
"""
    )
    output = tmp_path / "features.csv"
    generate_features.run_from_config(template, output)
    content = pd.read_csv(output)
    assert {"close_sma_2", "custom_expr"}.issubset(content.columns)
    assert not content["close_sma_2"].dropna().empty


def test_generate_features_uses_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import pandas as pd

    cache_path = tmp_path / "cache.pkl"
    dates = pd.date_range("2025-01-01", periods=4, freq="D")
    instruments = ["AAA", "BBB"]
    index = pd.MultiIndex.from_product([dates, instruments], names=["datetime", "instrument"])
    df = pd.DataFrame(
        {
            ("feature", "CLOSE"): range(len(index)),
            ("feature", "VOLUME"): [100, 200] * 4,
            ("label", "LABEL0"): [0.1] * len(index),
        },
        index=index,
    )
    df.to_pickle(cache_path)
    monkeypatch.setattr(generate_features, "HIKYUU_CACHE_PATH", cache_path)

    template = tmp_path / "template.yaml"
    template.write_text(
        """
name: cache_test
frequency: day
instruments:
  - AAA
  - BBB
start: "2025-01-01"
end: "2025-01-04"
indicators:
  - name: close_sma_2
    type: SMA
    field: $close
    window: 2
  - name: custom_expr
    expression: "EMA($close, 2) - Ref($close, 1)"
"""
    )
    output = tmp_path / "features.csv"
    generate_features.run_from_config(template, output)
    content = pd.read_csv(output)
    assert {"close_sma_2", "custom_expr"}.issubset(content.columns)
    assert not content["close_sma_2"].dropna().empty


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


def test_export_signals_includes_sell_side(tmp_path: Path) -> None:
    pred_path = tmp_path / "pred.pkl"
    data = [
        {"datetime": "2025-01-01", "instrument": "AAA", "score": 0.8},
        {"datetime": "2025-01-01", "instrument": "BBB", "score": -1.2},
        {"datetime": "2025-01-01", "instrument": "CCC", "score": -0.3},
    ]
    with pred_path.open("wb") as fp:
        pickle.dump(data, fp)
    output = tmp_path / "signals.csv"
    export_signals.run(pred_path, output, top_k=1, top_k_sell=1)
    rows = list(csv.DictReader(output.open()))
    assert len(rows) == 2
    action_map = {row["instrument"]: row["action"] for row in rows}
    assert action_map["AAA"] == "buy"
    assert action_map["BBB"] == "sell"
    weights = {row["instrument"]: float(row["weight"]) for row in rows}
    assert weights["AAA"] == pytest.approx(0.4, rel=1e-4)
    assert weights["BBB"] == pytest.approx(0.6, rel=1e-4)
    score_map = {row["instrument"]: float(row["score"]) for row in rows}
    assert score_map["AAA"] == pytest.approx(0.8, rel=1e-4)
    assert score_map["BBB"] == pytest.approx(-1.2, rel=1e-4)


def test_run_backtest_summary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import pandas as pd

    def fake_load_close_prices(instruments, start, end):
        dates = pd.to_datetime(["2025-01-01", "2025-01-02"])
        price_map = {
            "SH600000": [10.0, 11.0],
            "SZ000001": [20.0, 18.0],
        }
        data = {inst: price_map.get(inst, [10.0, 10.0]) for inst in instruments}
        return pd.DataFrame(data, index=dates)

    def fake_benchmark(dates, *_):
        return {date: 0.0 for date in dates}

    signals = tmp_path / "signals.csv"
    signals.write_text(
        """datetime,instrument,action,weight,score
2025-01-01,SH600000,buy,0.6,1.0
2025-01-01,SZ000001,sell,0.4,-0.5
"""
    )
    report = tmp_path / "summary.json"
    monkeypatch.setattr(run_backtest, "_load_close_prices", fake_load_close_prices)
    monkeypatch.setattr(run_backtest, "_load_benchmark_returns", fake_benchmark)
    run_backtest.run(signals, report)
    data = json.loads(report.read_text())
    assert data["total_signals"] == 2
    assert len(data["unique_instruments"]) == 2
    assert data["long_signals"] == 1
    assert data["short_signals"] == 1
    assert data["benchmark_symbol"] == "SH000300"
    assert data["total_return"] == pytest.approx(0.1, rel=1e-4)
    daily_returns = data["daily_returns"]
    assert len(daily_returns) == 1
    assert daily_returns[0]["value"] == pytest.approx(0.1, rel=1e-4)
    assert data["cumulative_returns"][-1]["value"] == pytest.approx(0.1, rel=1e-4)


def test_render_report_outputs_html(tmp_path: Path) -> None:
    signals = tmp_path / "signals.csv"
    signals.write_text(
        """datetime,instrument,action,weight,score\n2025-01-01,SH600000,buy,0.5,1.0\n"""
    )
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps({"total_signals": 1}))
    output = tmp_path / "review.html"
    detail = tmp_path / "review_detail.html"
    render_report.run(signals, summary_path, output, detail)
    summary_html = output.read_text()
    detail_html = detail.read_text()
    assert "Strategy Review" in summary_html
    assert "review_detail.html" in summary_html
    assert "SH600000" in detail_html


def test_generate_report_outputs(tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "total_return": 0.1,
                "annualized_return": 0.2,
                "sharpe_ratio": 1.1,
                "max_drawdown": -0.2,
                "total_signals": 2,
                "daily_returns": [
                    {"date": "2025-01-01", "value": 0.01},
                    {"date": "2025-01-02", "value": -0.02},
                    {"date": "2025-01-08", "value": 0.03},
                ],
            }
        )
    )
    signals = tmp_path / "signals.csv"
    signals.write_text(
        """datetime,instrument,action,weight,score
2025-01-01,AAA,buy,0.5,1.0
2025-01-02,AAA,sell,0.4,-0.5
"""
    )
    output = tmp_path / "report.html"
    generate_report.run(summary_path, signals, output, detail_link="detail.html", summary_link="summary.html")
    html = output.read_text()
    assert "Performance Report" in html
    assert "detail.html" in html
    assert "2025-01" in html
    assert output.with_name(f"{output.stem}_weekly{output.suffix}").exists()
    assert output.with_name(f"{output.stem}_monthly{output.suffix}").exists()
    assert not output.with_suffix(".pdf").exists()


def test_compare_reports(tmp_path: Path) -> None:
    before = tmp_path / "before.json"
    after = tmp_path / "after.json"
    before.write_text(json.dumps({
        "total_return": 0.1,
        "annualized_return": 0.2,
        "annualized_vol": 0.05,
        "sharpe_ratio": 4.0,
        "max_drawdown": -0.2,
        "total_signals": 5,
        "avg_gross_exposure": 0.5,
    }))
    after.write_text(json.dumps({
        "total_return": 0.15,
        "annualized_return": 0.22,
        "annualized_vol": 0.06,
        "sharpe_ratio": 3.5,
        "max_drawdown": -0.18,
        "total_signals": 6,
        "avg_gross_exposure": 0.55,
    }))
    output = tmp_path / "compare.csv"
    compare_reports.run(before, after, output)
    content = output.read_text().splitlines()
    assert "Metric,After (Δ)" in content[0]
    assert any("total_return" in line for line in content[1:])


def test_compat_check_run() -> None:
    results = compat_check.run_checks()
    assert "python_version" in results
    assert "platform" in results
    assert isinstance(results["python_version"], dict)


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


def test_review_decision_summary_confirm(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    signals = tmp_path / "signals.csv"
    signals.write_text(
        """datetime,instrument,action,weight,score\n2025-01-01,SH600000,buy,0.5,1.0\n"""
    )
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({"total_signals": 1, "unique_instruments": ["SH600000"]}))
    report = tmp_path / "decision.json"
    approved = tmp_path / "approved.csv"
    monkeypatch.setattr("builtins.input", lambda _: "n")
    result = review_decision.run_review(
        signals,
        report,
        approved,
        auto=False,
        summary_path=summary,
        require_confirm=True,
    )
    assert result == 1
    assert not report.exists()


def test_summary_collects_metrics(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    metrics_dir = tmp_path / "experiments" / "run1"
    metrics_dir.mkdir(parents=True)
    (metrics_dir / "metrics.json").write_text(json.dumps({"rows": 10, "instruments": ["A", "B"]}))
    summary.summarize(tmp_path / "experiments")
    out = capsys.readouterr().out
    assert "run1" in out
    assert "10" in out


def test_monitor_metrics(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import pandas as pd

    def fake_load_close_prices(instruments, start, end):
        dates = pd.to_datetime(["2025-01-01", "2025-01-02"])
        price_map = {
            "SH600000": [10.0, 11.0],
            "SZ000001": [20.0, 18.0],
        }
        data = {inst: price_map.get(inst, [10.0, 10.0]) for inst in instruments}
        return pd.DataFrame(data, index=dates)

    def fake_benchmark(dates, *_):
        return {date: 0.0 for date in dates}

    summary_path = tmp_path / "summary.json"
    monkeypatch.setattr(run_backtest, "_load_close_prices", fake_load_close_prices)
    monkeypatch.setattr(run_backtest, "_load_benchmark_returns", fake_benchmark)
    # Create synthetic run_backtest output to feed monitor
    signals = tmp_path / "signals.csv"
    signals.write_text(
        """datetime,instrument,action,weight,score
2025-01-01,SH600000,buy,0.6,1.0
2025-01-01,SZ000001,sell,0.4,-0.5
"""
    )
    run_backtest.run(signals, summary_path)
    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text(json.dumps({"rows": 10, "placeholder": False, "loss": 0.5}))
    output = tmp_path / "monitoring.json"
    history = tmp_path / "history.csv"
    chart = tmp_path / "chart.html"
    report = monitor_metrics.collect_metrics(
        summary_path,
        metrics_path,
        output,
        min_signals=1,
        min_rows=5,
        max_loss=1.0,
        history_path=history,
        history_limit=5,
        chart_path=chart,
        chart_title="Test Monitoring History",
        timestamp="2025-01-01T00:00:00",
    )
    assert report["violations"] == []
    assert output.exists()
    assert history.exists()
    assert chart.exists()
    assert "Test Monitoring History" in chart.read_text()
    history_lines = history.read_text().strip().splitlines()
    assert history_lines[0].startswith("timestamp")
    assert len(history_lines) == 2


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
        "reports": {"summary": str(tmp_path / "summary.json"), "html": str(tmp_path / "review.html"), "detail": str(tmp_path / "detail.html"), "report": str(tmp_path / "report.html")},
        "decision": {"report": str(tmp_path / "decision.json"), "approved": str(tmp_path / "approved.csv"), "auto": True},
        "experiments": {"base": str(tmp_path / "experiments")},
        "compare": {"baseline": str(tmp_path / "baseline.json"), "output": str(tmp_path / "compare.csv")},
    }
    (tmp_path / "signals.csv").write_text("datetime,instrument,action,weight,score\n2025-01-01,SH600000,buy,1,0.5\n")
    (tmp_path / "summary.json").write_text(json.dumps({
        "total_return": 0.1,
        "annualized_return": 0.2,
        "annualized_vol": 0.05,
        "sharpe_ratio": 1.0,
        "max_drawdown": -0.1,
        "total_signals": 1,
        "avg_gross_exposure": 0.5,
    }))
    (tmp_path / "baseline.json").write_text(json.dumps({
        "total_return": 0.05,
        "annualized_return": 0.1,
        "annualized_vol": 0.04,
        "sharpe_ratio": 0.8,
        "max_drawdown": -0.12,
        "total_signals": 1,
        "avg_gross_exposure": 0.4,
    }))
    registry = run_all.build_registry(config)
    assert "decision" in registry
    assert "report" in registry
    assert "monitor" in registry
    assert "compare" in registry
    registry["decision"]()
    assert (tmp_path / "decision.json").exists()
    registry["compare"]()
    assert (tmp_path / "compare.csv").exists()


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
    dataset_cfg, _, data_source = train_model._build_dataset_and_model(config)
    handler = dataset_cfg["kwargs"]["handler"]
    assert handler["module_path"] == "hikyuu_integration"
    assert data_source == "hikyuu"


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
