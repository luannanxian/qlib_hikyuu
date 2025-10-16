# Hikyuu × Qlib 个人量化工作站工作计划

> 基于 PRD 与架构设计汇总的落地执行任务  
> 目标：在 Apple Silicon (macOS) 环境完成 MVP → Beta → GA 的交付

---

## 1. 阶段划分与里程碑

| 阶段 | 时间（建议） | 核心目标 | 主要产物 |
| --- | --- | --- | --- |
| **MVP** | 第 1 ~ 3 周 | 打通“数据 → 训练 → 信号 → 回测”主流程 | 数据适配脚本、快速训练脚本、信号转换、回测脚本、基础文档、示例策略 |
| **Beta** | 第 4 ~ 5 周 | 丰富特征、半自动执行、完善实验管理与日志 | 指标模板、半自动调仓工具、实验日志、配置模板优化 |
| **GA** | 第 6 ~ 8 周 | 加入监控/告警、复盘工具、跨平台评估 | 监控组件、复盘报告生成、兼容性验证、UI/自动化预研 |

---

## 2. MVP 阶段任务（第 1 ~ 3 周）

### 2.1 环境与基础设施
- [x] 提供一键安装脚本（conda/venv）与 `check_env.py`
- [x] 建立项目目录结构、配置文件模板（config/base.yaml 等）
- [x] 整理基础文档：README、CONFIG_GUIDE、FAQ（初稿）

### 2.2 数据适配
- [x] 实现 `HikyuuDataLoader`（默认加载 O/H/L/C/V/AMOUNT/ADJFACTOR）
- [x] 支持分片/增量加载与数据异常检测
- [x] 编写 `prepare_data.py`，输出 Qlib/Hikyuu 数据集
- [x] 完成数据缓存策略（HDF5/Parquet）

### 2.3 特征与指标（基础）
- [x] 整合 Hikyuu 指标（EMA/MACD/ROC 等）生成脚本
- [x] 提供指标准入 Qlib 的模板示例

### 2.4 模型训练
- [x] 编写 `train_model.py`，实现默认 LightGBM 训练与预测输出（pred.pkl）
- [x] 集成 Qlib `R` 模块记录训练指标、参数
- [x] 输出 `metrics.json`、模型文件、训练日志

### 2.5 信号转换与回测
- [x] 编写 `export_signals.py`，定义统一信号格式（CSV/JSON）
- [x] 支持 Top-K 选股、择时信号规则配置
- [x] 编写 `run_backtest.py`，调用 Hikyuu Portfolio/TradeManager（mock：当前为统计型回测摘要）
- [x] 输出回测报告（收益曲线、指标 CSV/HTML）

### 2.6 示例策略与主控脚本
- [x] 完成端到端示例（Alpha158 + LGB + 中证 500）
- [x] 编写 `run_all.py`，支持按步骤执行完整流程
- [x] 验证“1 小时内跑通”验收标准，修正文档与脚本（本机 12s 完成 prepare→review）

---

## 3. Beta 阶段任务（第 4 ~ 5 周）

### 3.1 指标与特征扩展
- [x] 提供指标模板库（YAML/JSON），支持自定义参数
- [x] 增加量价组合、动量、波动等扩展特征
- [x] 优化缓存与命名管理（特征版本化）

### 3.2 半自动执行与 UX 提升
- [x] 开发 CLI/HTML 调仓建议展示工具（表格、图表）
- [x] 支持用户确认后执行回测/调仓逻辑
- [x] 增强 `run_all.py` 参数化能力，允许用户指定步骤

### 3.3 实验与日志
- [x] 引入统一日志管理（按模块划分日志文件）
- [x] 提供实验汇总脚本，生成指标对比表
- [x] 评估接入 MLflow 的可行性并撰写使用指南（可选）

### 3.4 文档与 FAQ 更新
- [ ] 完善 README/CONFIG_GUIDE/FAQ，加入截图与示例（部分完成：CONFIG_GUIDE 已更新）
- [x] 制作实操范例（博客/Markdown 教程）

---

## 4. GA 阶段任务（第 6 ~ 8 周）

### 4.1 监控与告警
- [ ] Metrics Collector：汇总收益、最大回撤、训练耗时、信号数量等
- [ ] 构建指标曲线展示（CSV/图表）
- [ ] 实现基础告警（指标低于阈值、信号缺失），支持邮件/桌面通知

### 4.2 复盘与报告
- [ ] `generate_report.py`：汇总策略表现、持仓结构、指标分布
- [ ] 自动生成周/月度报告（HTML/PDF）
- [ ] 支持对比多次实验结果

### 4.3 兼容性与扩展预研
- [ ] 测试 Windows/Linux 下的关键组件，记录兼容性情况
- [ ] 设计 Streamlit/Gradio UI 原型（展示数据、信号、回测）
- [ ] 评估自动调度（cron/launchd）与自动下单接口的接入条件

### 4.4 文档与发布
- [ ] 更新文档至 GA 版本，整理升级指南
- [ ] 编写发布日志、版本说明
- [ ] 收集种子用户反馈并形成改进 backlog

---

## 5. 交付物汇总清单

| 类别 | MVP | Beta | GA |
| --- | --- | --- | --- |
| 脚本 | check_env.py, prepare_data.py, train_model.py, export_signals.py, run_backtest.py, run_all.py | 指标模板脚本、半自动执行工具 | generate_report.py、监控脚本 |
| 核心模块 | HikyuuDataLoader、Signal Adapter、Config Manager、Workflow Manager（基础） | 指标模板库、日志管理、Workflow Manager 扩展 | 监控/告警、报告生成、UI 原型 |
| 数据资产 | 示例数据/特征、模型、信号、回测结果 | 扩展指标缓存、实验对比结果 | 周/月度报告、指标监控数据 |
| 文档 | README、CONFIG_GUIDE、FAQ（初稿）、示例教程 | 文档完善、FAQ 更新、实操案例 | GA 文档、发布说明、用户反馈汇总 |

---

## 6. 风险与依赖管理

- **技术风险**：Hikyuu 版本兼容、数据量大导致性能问题 → 在 MVP 即纳入性能测试与异常处理。  
- **资源风险**：单人/小团队执行，注意节奏与自动化工具（如 makefile、脚本）提高效率。  
- **反馈风险**：尽早邀请种子用户试用 MVP 收集反馈，避免闭门造车。  
- **扩展风险**：UI/实盘等扩展在 GA 阶段仅做预研，避免范围膨胀。

---

## 7. 后续迭代议题（Backlog）

- MLflow 集成与远程实验存储（团队模式）  
- Streamlit/Gradio UI 正式版  
- 自动调度与实盘接口对接  
- Windows/Linux 全兼容与容器部署  
- 策略模板市场（共享策略、特征配置）

---

该工作计划旨在确保“小步快跑、可控迭代”，在满足 MVP 目标后持续扩展功能深度与用户体验，最终打造适合个人投资者的量化工作站。
