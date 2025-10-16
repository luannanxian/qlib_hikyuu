# Hikyuu × Qlib 个人量化工作站

本项目提供一套适用于个人投资者的量化工作站脚手架，整合 Hikyuu 数据与策略能力、Qlib 的机器学习与回测能力，为本地桌面环境（当前支持 macOS Apple Silicon）提供端到端的策略研发流程。

## 功能概览

- **环境检测**：`scripts/check_env.py` 快速验证 Python 环境、依赖包与关键环境变量。
- **数据准备**：`scripts/prepare_data.py` 直接调用 Hikyuu/Qlib 数据源生成训练集，支持分片抓取、增量写入，并同步产出 CSV/HDF5/Parquet 缓存。
- **特征生成**：`scripts/generate_features.py` 基于 YAML 模板生成技术指标特征。
- **模型训练**：`scripts/train_model.py` 读取配置自动构建数据集与模型，若 Qlib 环境不可用则自动回退到 placeholder。
- **信号导出**：`scripts/export_signals.py` 将预测结果转换为 Hikyuu 友好的信号格式（CSV）。
- **回测与报告**：
  - `scripts/run_backtest.py` 汇总信号生成回测摘要。
  - `scripts/summary.py` 汇总实验指标。
  - `scripts/render_report.py` 生成 HTML 调研报告。
- **工作流编排**：`scripts/run_all.py` 以配置驱动的方式串联上述步骤，支持灵活指定执行步骤。

## 快速开始

1. **克隆仓库并进入目录**
   ```bash
   git clone <repo-url> qlib-workstation
   cd qlib-workstation
   ```

2. **安装依赖环境**
   ```bash
   bash scripts/setup_env.sh qlib_hikyuu
   conda activate qlib_hikyuu  # 若脚本检测不到 conda，会提示使用 venv
   ```
   > 脚本会自动创建虚拟环境并根据 `requirements.txt` 安装依赖。若你已经有现成的 Qlib/Hikyuu 环境，可直接跳过此步并激活对应环境。

3. **检查环境**
   ```bash
   python scripts/check_env.py --verbose
   ```

4. **运行全流程示例**
   ```bash
   python scripts/run_all.py --config config/base.yaml --steps prepare train features signals backtest summary review --verbose
   ```
以上命令将在 `experiments/`, `artifacts/`, `reports/` 等目录输出占位数据。若 Qlib 环境可用，将自动调用真实训练流程。

生成的数据默认同时保存为 `CSV/HDF5/Parquet` 三种格式（位于 `data/` 目录），也可以通过 `prepare_data.py --cache-format csv --cache-format parquet` 明确指定所需格式。

5. **性能参考**
   Apple Silicon (M1) + 本地 Hikyuu/MySQL 环境下，`prepare → review` 全流程耗时约 12 秒，满足“1 小时内跑通”的验收目标。数据量更大时，耗时取决于下载窗口及数据库吞吐。

> 如果环境中未安装或版本过旧的 `pyarrow`，Parquet 缓存会跳过写入并提示警告，可使用 `pip install --upgrade pyarrow` 补齐依赖。

## 配置说明

主配置位于 `config/base.yaml`，涵盖：

- `run_modes`：支持 quick/full 等不同数据范围。
- `dataset`：按运行模式定义时间区间、分段、数据源。
- `model`：默认的 LightGBM 超参数，可按需调整。
- `features.templates`：技术指标模板列表；可自定义 YAML 文件。
- `signals` 与 `reports`：指定信号文件、回测摘要、HTML 报告的输出路径。

额外模板示例位于 `config/templates/`：
- `default_indicators.yaml`：基础 EMA/RSI 等指标。
- `basic_volume.yaml`：包含量价与波动指标。
- `advanced_momentum.yaml`：扩展动量指标（MACD、Stochastic 等）。

## 目录结构

```
config/                 # 配置文件与指标模板
doc/                    # PRD、架构设计、工作计划与 README
scripts/                # CLI 工作流脚本
manual/                 # Hikyuu 官方文档快照
experiments/            # 训练输出（pred.pkl、metrics.json 等）
artifacts/              # 导出的信号
reports/                # 回测摘要与 HTML 报告
features/               # 生成的特征文件
```

## 约束与注意事项

- 当前仅验证在 macOS Apple Silicon 上运行；其他平台需评估。
- 真实数据与模型逻辑尚在开发中，现阶段脚本包含占位逻辑，仅用于演示流程。
- 使用前请确保遵守数据与交易合规要求；实盘前务必加上止损、仓位控制等安全措施。

## 后续工作

详见 `doc/hikyuu_qlib_work_plan.md`。Beta 阶段将继续完善半自动调仓、文档、实验管理；GA 阶段会加入监控、复盘报告、跨平台支持等功能。
