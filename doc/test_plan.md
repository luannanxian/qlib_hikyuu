# 集成测试计划（基于用户旅程）

本文梳理 `doc/hikyuu_qlib_personal_prd.md` 中的用户旅程，将每一步转化为可重复的测试用例，覆盖占位流程与配置化特性。

## 测试环境

- 操作系统：macOS (Apple Silicon)
- Python 环境：`conda activate qlib_env`
- 代码分支：`feature/beta-enhancements`
- 项目根目录：`/Users/zhenkunliu/project/qlib-project`
- 依赖：`mlflow`、`pytest`

## 测试总览

| 序号 | 测试目标 | 关键命令/动作 | 预期结果 |
| ---- | -------- | ------------- | -------- |
| 1 | 环境检测 | `python scripts/check_env.py --verbose` | 打印 Python/依赖/环境变量/路径检查信息，不致命的缺包时提供提示 |
| 2 | 工作流整合 | `python scripts/run_all.py --config config/base.yaml --steps prepare train features signals backtest summary review decision --verbose` | 全流程完成，占位训练、生成特征/信号/回测摘要/HTML 报告与审核结果，无异常退出 |
| 3 | 手动审核流程 | `python scripts/review_decision.py --signals artifacts/signals.csv --report artifacts/manual_review.json --approved artifacts/manual_signals.csv` | CLI 逐条询问，选择不同应答后生成对应报告与 approved 文件 |
| 4 | MLflow 可选 | `QLIB_USE_MLFLOW=true python scripts/train_model.py --config config/base.yaml --pred-path tmp/pred.pkl --metrics-path tmp/metrics.json` | 训练后在 `mlruns/` 或指定 URI 中生成新 run，包含 metrics / artifact（需已安装 mlflow） |
| 5 | 配置切换 | 修改 `config/base.yaml` 的 `run_modes.default` 或 `signals.top_k` 再执行工作流 | 工作流根据配置变化生成不同输出（如 Top-K 减少、报告文件名变化） |
| 6 | 单元测试回归 | `pytest tests -q` | 14 条测试全部通过 |

## 详细测试步骤

### 用例 1：环境检测
1. 激活环境：`conda activate qlib_env`
2. 运行 `python scripts/check_env.py --verbose`
3. 预期：输出 Python 版本、依赖可用性（缺失包给出提示但不中断）、环境变量状态与数据路径检查。

### 用例 2：工作流整合（Quick 模式）
1. 清理旧输出（可选）：删除 `artifacts/`, `reports/`, `experiments/`, `features/`
2. 执行命令：
   ```bash
   python scripts/run_all.py --config config/base.yaml --steps prepare train features signals backtest summary review decision --verbose
   ```
3. 预期：
   - `experiments/latest/pred.pkl`, `metrics.json` 创建；若 Qlib 数据缺失，fallback 仍生成占位
   - `features/features.csv`、`artifacts/signals.csv`、`reports/latest/backtest_summary.json`、`reports/latest/review.html` 存在
   - `artifacts/review_decision.json` 与 `artifacts/approved_signals.csv` 生成（默认 auto=true）
   - 命令退出码 0，无未捕获异常

### 用例 3：手动审核
1. 在工作流运行后执行：
   ```bash
   python scripts/review_decision.py --signals artifacts/signals.csv --report artifacts/manual_review.json --approved artifacts/manual_signals.csv
   ```
2. 当 CLI 提示 “Accept this signal?” 时，分别输入 `y`、`n` 或直接回车验证逻辑
3. 预期：最终生成的 `manual_review.json` 中 `approved` 数量与输入一致；`manual_signals.csv` 仅包含已批准项

### 用例 4：MLflow 集成
1. 确保已安装 mlflow (`pip install mlflow`)
2. 设置环境变量：
   ```bash
   export QLIB_USE_MLFLOW=true
   export MLFLOW_TRACKING_URI=""
   ```
3. 执行训练：
   ```bash
   python scripts/train_model.py --config config/base.yaml --pred-path tmp/pred.pkl --metrics-path tmp/metrics.json
   ```
4. 预期：
   - 若有 MLflow 服务未启动，脚本会提示并继续
   - 若使用本地存储（默认为 `mlruns/`），应有新 run 记录指标
   - 可使用 `mlflow ui` 在另一个终端验证记录存在

### 用例 5：配置切换
1. 修改 `config/base.yaml`：例如将 `signals.top_k` 改为 2 或切换 `run_modes.default` 为 `full`
2. 重跑工作流：
   ```bash
   python scripts/run_all.py --config config/base.yaml --steps prepare train signals backtest --verbose
   ```
3. 预期：输出中的信号数量或时间范围随配置变化，日志反映新的参数

### 用例 6：单元测试回归
1. 运行 `pytest tests -q`
2. 预期：14 条测试全部通过，无错误或失败

## 故障排查

- 若出现 `ModuleNotFoundError`（如 torch、tianshou），表示误运行了 Qlib 原仓库的测试套件；需执行 `pytest tests` 限定目录
- 若 Qlib 数据缺失导致训练失败，脚本会自动 fallback，但建议提前准备 `~/.qlib/qlib_data`
- MLflow 日志失败时请检查环境变量、服务器状态或升级 mlflow 版本

## 记录

| 日期 | 版本 | 测试结果 | 备注 |
| ---- | ---- | -------- | ---- |
| 2025-10-15 | feature/beta-enhancements | 通过 | 初版测试计划 |
