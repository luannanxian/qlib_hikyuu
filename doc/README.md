# Hikyuu × Qlib 个人量化工作站

本项目提供一套适用于个人投资者的量化工作站脚手架，整合 Hikyuu 数据与策略能力、Qlib 的机器学习与回测能力，为本地桌面环境（当前支持 macOS Apple Silicon）提供端到端的策略研发流程。

## 功能概览

- **环境检测**：`scripts/check_env.py` 快速验证 Python 环境、依赖包与关键环境变量。
- **数据准备**：`scripts/prepare_data.py` 占位逻辑，后续可接入 Hikyuu 数据提取。
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

2. **安装依赖（推荐使用 conda）**
   ```bash
   conda create -n qlib_env python=3.11
   conda activate qlib_env
   pip install -r requirements.txt  # TODO: 提供精简依赖列表
   ```
   > 若已安装 Qlib、Hikyuu，可直接激活对应环境。

3. **检查环境**
   ```bash
   python scripts/check_env.py --verbose
   ```

4. **运行全流程示例**
   ```bash
   python scripts/run_all.py --config config/base.yaml --steps prepare train features signals backtest summary review --verbose
   ```
   以上命令将在 `experiments/`, `artifacts/`, `reports/` 等目录输出占位数据。若 Qlib 环境可用，将自动调用真实训练流程。

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
