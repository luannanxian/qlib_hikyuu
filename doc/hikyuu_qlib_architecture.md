# Hikyuu × Qlib 个人量化工作站架构设计

> 适用范围：PRD《Hikyuu × Qlib 个人量化工作站》配套技术方案  
> 当前硬件目标：macOS (Apple Silicon) 本地桌面环境

---

## 1. 架构总览

```
┌──────────────────────────────────────────────────────────────────┐
│                        用户交互与自动化层                         │
│  • CLI / shell 脚本：check_env.py, run_all.py, prepare_data.py... │
│  • （未来）轻量 UI（Streamlit/Gradio）                            │
└───────────────▲──────────────────┬───────────────────────────────┘
                │数据指令/配置       │日志、报告
┌───────────────┴───────────────────▼──────────────────────────────┐
│                         工作流编排层                              │
│  Workflow Manager                                                │
│  • Step 调度：数据 → 特征 → 训练 → 信号 → 回测 → 复盘            │
│  • 任务管理：依赖关系、失败重试、状态跟踪                        │
│  • 配置管理：config.yaml/JSON（股票池、日期、模型参数…）        │
└───────────────▲───────────────────┬──────────────────────────────┘
                │调用 API            │事件/日志
┌───────────────┴─────────┐ ┌───────▼─────────────────────────────┐
│  数据与特征服务层        │ │   训练与实验层                      │
│  • Hikyuu DataLoader     │ │  • Qlib Trainer                    │
│  • 指标计算 Pipeline     │ │  • Experiment Logger (R/MLflow)   │
│  • 数据缓存（HDF5/MySQL）│ │  • 模型仓库 (model.pkl, pred.pkl) │
└───────────────▲─────────┘ └───────┬─────────────────────────────┘
                │行情/指标数据        │预测/模型
┌───────────────┴───────────────────▼──────────────────────────────┐
│                         策略执行与分析层                          │
│  • Signal Adapter → Hikyuu Selector/Signal                       │
│  • Portfolio Runner / TradeManager                               │
│  • 结果分析：收益、风险、报告输出（CSV/HTML/图表）              │
└───────────────▲───────────────────┬──────────────────────────────┘
                │调仓建议/回测结果    │执行反馈
┌───────────────┴───────────────────▼──────────────────────────────┐
│                     日志、监控与资产存储层                        │
│  • 日志中心：log/                                               │
│  • 实验资产：mlruns/、experiments/                               │
│  • 数据资产：~/.qlib/、~/.hikyuu/、cache/                        │
│  • 监控与告警：指标汇总、异常检测、邮件/桌面提醒                │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. 模块职责与接口

### 2.1 数据与特征层

| 模块 | 职责 | 关键接口/数据格式 | 备注 |
| --- | --- | --- | --- |
| **HikyuuDataLoader** | 从 Hikyuu 抽取行情与指标数据，输出 Qlib 所需 DataFrame | `load(instruments, start, end)` → MultiIndex DataFrame (datetime, instrument, feature/label) | 默认加载 O/H/L/C/V/AMOUNT/ADJFACTOR，可配置字段；支持分片加载 |
| **Indicator Pipeline** | 批量生成技术指标（EMA/MACD/RSI/自定义），落盘供 Qlib 使用 | `generate(config)` 读取指标模板 → CSV/Parquet/DF | 结合 YAML 模板，实现复用与版本管理 |
| **Data Cache** | 存放中间数据（如提取后的 HDF5、缓存的指标结果） | `cache/` 目录 + 元数据 JSON | 控制缓存大小/生命周期 |

### 2.2 训练与实验层

| 模块 | 职责 | 关键接口/数据格式 | 备注 |
| --- | --- | --- | --- |
| **Trainer** | 调用 Qlib，按照配置训练模型并输出预测信号 | `train(config)` → `model.pkl`, `pred.pkl`, `metrics.json` | 默认 LGBModel，可扩展其它模型 |
| **Experiment Logger** | 记录训练参数、指标、artifact；管理实验版本 | 默认 Qlib `R` 模块：`R.save_objects`, `R.log_metrics` | 可选集成 MLflow（P2） |
| **Model Repository** | 存储模型、预测结果，便于复用与回滚 | `experiments/<exp_id>/` | 包含模型文件、预测结果、训练配置 |

### 2.3 策略执行层

| 模块 | 职责 | 关键接口/数据格式 | 备注 |
| --- | --- | --- | --- |
| **Signal Adapter** | 将 `pred.pkl` 转换为 Hikyuu Selector/信号文件 | 输入：`pred.pkl`（MultiIndex） → 输出：`signals.csv` (datetime, instrument, action, weight/score) | 支持 Top-K 选股与择时信号；提供 format 规范 |
| **Portfolio Runner** | 调用 Hikyuu Portfolio/TradeManager 执行回测或模拟调仓 | `run_portfolio(config, signals)` → 报告 | 输出收益曲线/风险指标（CSV/HTML/图） |
| **Semi-auto Executor** | 在 CLI/HTML 中展示调仓建议，用户确认后执行 | CLI 表格 / HTML 报告 | 可接入 Hikyuu GUI |

### 2.4 工作流编排层

| 模块 | 职责 | 关键接口/数据格式 | 备注 |
| --- | --- | --- | --- |
| **Workflow Manager** | 根据配置执行各阶段任务，处理依赖与错误恢复 | `run_step(step_name)` / `run_all()` | 维护状态机（待执行、执行中、成功、失败） |
| **Config Manager** | 统一管理配置文件（config.yaml/json） | `load_config()` → Python dict；`validate_config()` | 将股票池、时间区间、特征、模型参数抽离至配置 |
| **Task Scheduler（可选）** | 定时任务、增量训练与数据更新 | 计划阶段采用 cron/launchd；未来可接 Tiger/Moon | MVP 可暂存为脚本或用户自定义 |

### 2.5 日志监控层

| 模块 | 职责 | 关键接口/数据格式 | 备注 |
| --- | --- | --- | --- |
| **Logging Manager** | 收集各模块日志，统一格式输出 | Python logging；logrotate 控制大小 | 通过 `log/` 目录管理 |
| **Metrics Collector** | 汇总收益、回撤、训练耗时等关键指标 | `metrics.json` / SQLite | 预留与监控/可视化对接 |
| **Alert Service（可选）** | 指标超限、信号缺失等触发邮件/桌面提醒 | MVP 可使用 macOS 通知/邮件脚本 | 纳入 P1/P2 |

---

## 3. 数据流与流程

### 3.1 端到端流程

1. **环境检测**：`check_env.py` 检查 Python 版本、依赖、Hikyuu 数据路径、环境变量。  
2. **数据准备**：`prepare_data.py` 调用 HikyuuDataLoader + 指标 Pipeline → 输出 `dataset.pkl`/`dataset.h5`。  
3. **模型训练**：`train_model.py` 读取配置 → 训练 → 保存 `pred.pkl`、模型文件、日志。  
4. **信号转换**：`export_signals.py` 将 `pred.pkl` 转为 `signals.csv`，生成可视化报告（HTML/PNG）。  
5. **回测/调仓**：`run_backtest.py` 调用 Hikyuu Portfolio → 输出收益曲线、风险指标。  
6. **复盘输出**：将指标、图表、日志整合为报告，存放在 `reports/日期/`。  
7. **主控脚本**：`run_all.py --steps prepare,train,backtest` 支持整合执行。

### 3.2 关键数据结构

| 名称 | 描述 | 示例 |
| --- | --- | --- |
| `pred.pkl` | Qlib 预测结果，MultiIndex（datetime, instrument），列包含 score/rank | ![pred-structure](images/pred_structure.png) |
| `signals.csv` | Hikyuu 接收的信号，字段 `datetime,instrument,action,weight,score` | `2024-01-02,SH600000,buy,0.05,0.87` |
| `config.yaml` | 用户配置文件 | 股票池、时间区间、特征模板、模型参数、回测设置等 |
| `metrics.json` | 模型训练/回测指标 | `{"train_loss":..., "IC":..., "IR":...}` |

---

## 4. 模块交互详解

### 4.1 Hikyuu ↔ Qlib 适配
- **数据读取接口**：使用 Hikyuu Python API（`StockManager`, `Stock.get_kdata`），将 Query 转为日期区间。
- **数据格式约定**：输出 DataFrame 的 columns 为 MultiIndex (`('feature','OPEN')`...), label 列为 (`('label','LABEL0')`)。
- **性能策略**：  
  - 对大数据集采用分标的、分时间段批次加载。  
  - 支持缓存（Pickle/HDF5）避免重复 IO。  
  - 利用 Apple Silicon 的多核 + Python multiprocessing（注意 GIL）或 joblib。

### 4.2 信号转换
- **Top-K 选股**：对 `pred.pkl` 按日期排序，取前 K 名生成 `action=buy`, `weight=1/K`；盈亏不佳者生成 `action=sell`。  
- **择时信号**：根据预测分数门限（如 >0.5 买入、<-0.5 卖出），输出买卖信号。  
- **输出格式**：默认 CSV，配套生成 `signal_summary.html`（表格 + 图表）供用户审核。  
- **兼容性**：信号文件可直接在 Hikyuu Portfolio 选择器中加载；也可由脚本读入。

### 4.3 半自动执行
- 在 Hikyuu 交互式环境打印表格或生成 HTML 报告（可使用 `tabulate` + `jinja2`）。  
- 用户确认后，通过 Hikyuu 的交易接口发出调仓指令或执行回测。  
- 保留执行日志，记录实际成交与差异。

---

## 5. 配置与扩展

### 5.1 配置体系

```
config/
├── base.yaml          # 通用配置（数据路径、默认参数）
├── dataset.yaml       # 股票池、时间范围、指标模板
├── model.yaml         # 模型参数、训练窗口、评估方案
├── backtest.yaml      # 策略、回测参数、资金管理
└── user_override.yaml # 用户自定义覆盖
```

- `Config Manager` 负责加载并合并配置，支持多环境（dev/prod）。  
- `check_env.py` 验证配置合法性，输出诊断报告。

### 5.2 示例策略

- 默认示例：`examples/alpha158_csi500`  
  - 数据：沪深 A 股 + 中证 500 成分  
  - 特征：Alpha158 + Hikyuu EMA/RSI  
  - 模型：LightGBM  
  - 输出：信号 CSV + 回测报告 + 复盘 HTML

---

## 6. 部署与运行

### 6.1 环境依赖
- 操作系统：macOS 13+（Apple Silicon）  
- Python：3.10/3.11（conda 或 venv）  
- 关键包：`hikyuu`, `pyqlib`, `lightgbm`, `pandas`, `numpy`, `yaml`, `jinja2`, `plotly` 等  
- 建议提供 `environment.yml` 与 `pip install -r requirements.txt`

### 6.2 目录结构

```
project-root/
├── config/
├── data/                 # 本地缓存，可软链接至 Hikyuu 数据
├── doc/
├── examples/
├── logs/
├── mlruns/               # Qlib 实验输出
├── scripts/              # 主要 CLI 脚本
├── src/                  # 核心模块实现
└── reports/
```

### 6.3 安全策略
- 所有脚本默认在用户本地执行，不上传敏感数据。  
- 若启用云端组件（如 MLflow 远程服务器），需提示用户配置访问控制。  
- 提供数据备份与恢复指南。

---

## 7. 可观测性与运维

- **日志**：按模块划分（data_loader.log、trainer.log、backtest.log），支持 logrotate。  
- **指标**：统一写入 `metrics.json` 或 SQLite，用于生成监控报表。  
- **告警**：支持简单规则（模型指标下降、数据缺失），后续可对接邮件/API。  
- **诊断工具**：`debug_report.py` 收集环境/日志/配置以便问题追踪。

---

## 8. 扩展规划

- **UI 层**：基于 Streamlit/Gradio，展示策略状态、图表、日志，支持交互操作。  
- **自动调度**：支持 cron/launchd 自动执行数据更新与训练。  
- **集成实盘 API**：在风控与测试充分后接入券商或交易接口，实现自动下单。  
- **云端/多平台**：逐步支持 Windows/Linux，增加容器化部署、远程协同能力。

---

## 9. 风险与对策

| 风险 | 描述 | 缓解措施 |
| --- | --- | --- |
| 数据规模过大 | 全市场 + 长周期导致内存不足 | 分片加载、缓存、明确数据规模建议 |
| 模型训练过慢 | Apple Silicon 架构下模型耗时 | 优化参数、使用 joblib/多进程、可选 GPU 或云端训练 |
| 信号误用 | 用户直接将信号用于实盘 | 在 UI/报告中提示“AI 信号为建议”，保留人工确认步骤 |
| 环境配置复杂 | 依赖较多 | 提供一键脚本、环境检测、文档与 FAQ |

---

通过上述架构设计，可以在保证灵活性与扩展性的同时，满足个人投资者“快、稳、易用”的核心诉求，为后续功能迭代和平台化发展打下坚实基础。
