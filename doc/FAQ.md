# 常见问题（FAQ）

## 环境相关

### Q: `scripts/check_env.py` 显示缺少 pyqlib/hikyuu/lightgbm
A: 请在虚拟环境中安装依赖，例如：
```bash
pip install pyqlib lightgbm pandas numpy pyyaml
pip install hikyuu  # 需参考官方文档进行编译/安装
```
如果暂时无法安装，可继续使用占位逻辑进行流程演示。

### Q: 运行 `scripts/run_all.py` 提示 `ModuleNotFoundError: No module named 'scripts'`
A: 请确保在项目根目录执行该命令，或将项目根目录加入 `PYTHONPATH`。

### Q: 激活了 conda 环境但脚本仍报错
A: 确认执行命令前运行 `conda activate qlib_env`，并在同一 shell 中执行脚本。

## 训练与数据

### Q: 训练阶段提示 `qlib workflow failed: 'feature'`
A: 当前配置的 handler 可能无法从数据源返回带 `feature` 列的数据，可暂时使用默认数据源或检查 Hikyuu 数据是否齐全。脚本会自动切换到 placeholder 模式保持流程运行。

### Q: 如何切换到 Hikyuu 数据源？
A: 设置环境变量：
```bash
export QLIB_DATA_SOURCE=hikyuu
export QLIB_HIKYUU_INSTRUMENTS="SH600000,SZ000001"
```
同时确保已安装 hikyuu，并在 `config/base.yaml` 中配置好标的、时间范围。

### Q: 生成的 `pred.pkl` 是什么格式？
A: 真实训练时为包含 MultiIndex（datetime, instrument）的 DataFrame；占位逻辑则输出相同结构的随机数据。

## 工作流与输出

### Q: 如何只运行部分步骤？
A: 使用 `--steps` 参数，例如：
```bash
python scripts/run_all.py --steps prepare train
```

### Q: 生成的报告在哪里？
A: 默认在 `reports/latest/` 下，包括 `backtest_summary.json` 和 `review.html`。

### Q: `run_all.py` 报日志权限错误？
A: 确保 `logs/` 目录可写，或修改 `LOG_PATH` 指向可写目录。

## 其他

### Q: 是否支持 Windows / Linux？
A: 目前仅验证 macOS Apple Silicon 环境，其他平台待后续 GA 阶段适配。

### Q: 实盘接入如何实现？
A: 当前仅提供研发环境脚手架，实盘接入需在 GA 阶段评估风控、接口以及合规要求。

如未找到答案，请查看 `doc/hikyuu_qlib_work_plan.md` 或在 issue 中反馈。
