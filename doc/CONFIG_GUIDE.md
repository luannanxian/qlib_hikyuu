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

## 4. 输出目录说明

- `experiments/`：存放 `pred.pkl` 与 `metrics.json`。
- `artifacts/`：导出的信号 CSV。
- `features/`：生成的特征文件。
- `reports/`：回测摘要 (`backtest_summary.json`) 与 HTML 复盘 (`review.html`)。

## 5. 配置加载优先级

`run_all.py` 支持 `--config` 多文件叠加加载。例如：
```bash
python scripts/run_all.py --config config/base.yaml config/override.yaml --steps train
```
后加载的文件会覆盖先前配置。

---
如需更多示例，可参考 `doc/README.md` 与 `doc/hikyuu_qlib_work_plan.md`。
