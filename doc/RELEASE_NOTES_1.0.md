## Hikyuu × Qlib 工作站 GA 1.0 发布说明

### 新增内容
- **训练 & 特征**：`train_model.py` 支持 Hikyuu 缓存，`generate_features.py` 复用缓存生成指标。
- **复盘报告**：`generate_report.py` 支持周/月度报告输出，并可结合 `compare_reports.py` 对比基线结果。
- **监控告警**：`monitor_metrics.py` 加入阈值检测、历史记录与告警日志。
- **兼容性自检**：`compat_check.py` 提供跨平台依赖探测。
- **UI 原型**：Streamlit dashboard 展示关键指标、信号预览。

### 已知限制
- 仅在 macOS (Apple Silicon) 验证；Windows/Linux 仍需实测。
- 邮件/桌面通知暂未接入，告警以日志为主。
- Streamlit 原型用于演示，非正式交互界面。
