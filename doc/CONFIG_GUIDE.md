# 配置指南（Config Guide）

本文帮助用户理解并调整 `config/base.yaml` 及相关模板，实现灵活的策略配置。

## 1. 配置入口

- `config/base.yaml`：主配置文件，定义运行模式、数据源、模型参数、输出路径等。
- `config/templates/*.yaml`：指标模板，用于生成特征数据。

## 2. 主配置结构

```yaml
run_modes:             # 运行模式
  default: quick
  supported: [quick, full]

data:                  # 数据与输出目录
  provider_uri: "~/.qlib/qlib_data/cn_data"
  output_dir: data
  features_dir: features
  data_source: hikyuu   # 默认使用 Hikyuu 数据源，可改为 qlib

workflow:              # 默认工作流步骤
  steps: [check, prepare, train, features, signals, backtest, summary, review]

features:              # 特征配置
  template: config/templates/default_indicators.yaml
  templates:
    - config/templates/default_indicators.yaml
    - config/templates/basic_volume.yaml
    - config/templates/advanced_momentum.yaml
  output: features/features.csv

signals:
  output: artifacts/signals.csv
  top_k: 3

reports:
  summary: reports/latest/backtest_summary.json
  html: reports/latest/review.html

experiments:
  base: experiments

hikyuu:
  instruments: [SH600000, SH600009, SZ000001, SZ000002]

model:
  class: LGBModel
  module_path: qlib.contrib.model.gbdt
  kwargs:
    loss: mse
    learning_rate: 0.0421
    n_estimators: 200
    # ... 其他 LightGBM 参数

dataset:
  quick:
    instruments: csi100
    start_time: "2012-01-01"
    end_time: "2020-12-31"
    fit_start_time: "2012-01-01"
    fit_end_time: "2017-12-31"
    segments:
      train: ["2012-01-01", "2017-12-31"]
      valid: ["2018-01-01", "2018-12-31"]
      test:  ["2019-01-01", "2020-12-31"]
  full:
    instruments: csi300
    start_time: "2010-01-01"
    end_time: "2022-12-31"
    fit_start_time: "2010-01-01"
    fit_end_time: "2018-12-31"
    segments:
      train: ["2010-01-01", "2018-12-31"]
      valid: ["2019-01-01", "2019-12-31"]
      test:  ["2020-01-01", "2022-12-31"]
```

## 3. 常用配置调整

### 3.1 更换运行模式
```bash
export QLIB_RUN_MODE=full
python scripts/run_all.py --config config/base.yaml --steps train
```
若需要自定义模式，可在 `dataset` 下新增配置。

### 3.2 使用 Hikyuu 数据源
在 `config/base.yaml` 的 `data.data_source` 填写 `hikyuu` 即可，也可通过环境变量覆盖：
```bash
export QLIB_DATA_SOURCE=hikyuu
export QLIB_HIKYUU_INSTRUMENTS="SH600000,SZ000001"
```
确保安装 `hikyuu` 并可访问对应数据源。

### 3.3 调整 LightGBM 参数
修改 `model.kwargs` 即可，例如：
```yaml
model:
  kwargs:
    learning_rate: 0.02
    num_leaves: 256
```

### 3.4 自定义指标模板
新增 `config/templates/my_template.yaml`：
```yaml
name: my_template
frequency: day
indicators:
  - type: EMA
    source: CLOSE
    window: 5
  - type: MACD
    fast: 12
    slow: 26
    signal: 9
```
并在 `features.templates` 中追加路径。
运行：
```bash
python scripts/run_all.py --steps features
```

### 3.5 临时覆写配置项

无需修改 YAML 文件即可覆盖单个配置：
```bash
python scripts/run_all.py --set signals.top_k=5 --set "reports.summary='reports/latest/custom.json'"
```
如需传递列表或数字，请使用 Python 字面量，例如 `--set features.templates=['config/templates/default_indicators.yaml']`。

### 3.6 快速预览信号

生成信号后，可用 CLI 汇总查看：
```bash
python scripts/preview_signals.py --signals artifacts/signals.csv --top 10 --by-date
```
输出包含信号数量、动作分布以及得分最高的标的列表。

## 4. 输出目录说明

- `experiments/`：存放 `pred.pkl` 与 `metrics.json`。
- `artifacts/`：导出的信号 CSV。
- `features/`：生成的特征文件。
- `reports/`：回测摘要 (`backtest_summary.json`) 与 HTML 复盘 (`review.html`)。
- `logs/`：JSON Lines 结构日志（例如 `run_all.jsonl`），便于后续接入日志分析或 MLflow。
- `features/`、`tmp/` 等临时目录按需可清理。

## 5. 配置加载优先级

`run_all.py` 支持 `--config` 多文件叠加加载。例如：
```bash
python scripts/run_all.py --config config/base.yaml config/override.yaml --steps train
```
后加载的文件会覆盖先前配置。

此外还可借助 `scripts/summary.py` 汇总实验：
```bash
python scripts/summary.py --format json --output reports/latest/experiment_summary.json
```
默认输出表格，也支持 JSON/CSV 形式，统计成功次数、占位次数以及覆盖的标的列表。

---
如需更多示例，可参考 `doc/README.md` 与 `doc/hikyuu_qlib_work_plan.md`。
