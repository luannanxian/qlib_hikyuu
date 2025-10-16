# 实操示例：从数据准备到调仓确认

以下示例演示如何在 macOS Apple Silicon 环境中快速跑通一次完整流程，并在回测后进行人工确认。

## 1. 环境准备
```bash
bash scripts/setup_env.sh qlib_hikyuu
conda activate qlib_hikyuu
python scripts/check_env.py --verbose
```

## 2. 数据准备（按分片、生成缓存）
```bash
python scripts/prepare_data.py \
  --config config/base.yaml \
  --output data/prepared_dataset.csv \
  --chunk-days 90 \
  --cache-format csv --cache-format parquet
```
日志会说明各分片抓取进度，并在 `data/` 目录生成带版本号的 CSV/Parquet 文件。

## 3. 特征生成与训练
```bash
python scripts/generate_features.py --template config/templates/default_indicators.yaml --output features/features.csv
python scripts/train_model.py
```
若 Qlib 环境有效，训练完成后会在 `experiments/latest/` 下生成 `pred.pkl` 与 `metrics.json`。

## 4. 回测与报告
```bash
python scripts/export_signals.py
python scripts/run_backtest.py
python scripts/render_report.py
```
默认输出：
- `artifacts/signals.csv`
- `reports/latest/backtest_summary.json`
- `reports/latest/review.html`

## 5. 信号预览与调仓确认
```bash
python scripts/preview_signals.py --signals artifacts/signals.csv --top 5 --by-date
python scripts/review_decision.py --summary reports/latest/backtest_summary.json --confirm
```
`review_decision.py` 会先展示回测摘要，之后逐条提示是否接受信号，最终生成：
- `artifacts/review_decision.json`
- `artifacts/approved_signals.csv`

## 6. 一键跑全流程
上述步骤也可通过工作流脚本一次完成：
```bash
python scripts/run_all.py \
  --config config/base.yaml \
  --steps prepare train features signals backtest summary review decision \
  --verbose
```
在默认配置下，整个流程约 12 秒可完成；若将 `decision.auto` 设为 `false`、`require_confirm` 设为 `true`，脚本会在回测后等待人工确认。

更多配置细节请参考 `doc/CONFIG_GUIDE.md`。
