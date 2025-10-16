# MLflow 集成指南

本文介绍如何在本项目中启用 MLflow，记录训练指标与工件，便于对比与溯源。

## 1. 安装与启动 MLflow

### 1.1 安装 MLflow

在你的虚拟环境中安装 MLflow（若已安装可跳过）：

```bash
pip install mlflow
```

### 1.2 启动本地 Tracking Server（可选）

默认情况下，MLflow 会将数据写入本地的 `mlruns/` 目录。如果希望使用 Web UI 或远程存储，可以启动 Tracking Server：

```bash
mlflow server \
  --backend-store-uri sqlite:///mlruns.db \
  --default-artifact-root file:$(pwd)/mlartifacts \
  --host 0.0.0.0 --port 5000
```

启动后，可通过浏览器访问 `http://127.0.0.1:5000` 查看实验记录。

## 2. 在工作流中启用 MLflow

`scripts/train_model.py` 已内置对 MLflow 的支持，只需在运行前设置以下环境变量：

```bash
export QLIB_USE_MLFLOW=1                       # 打开 MLflow 记录功能
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000  # 指向你的 Tracking Server，可选
```

随后正常执行工作流，例如：

```bash
python scripts/run_all.py --steps prepare train
```

运行完成后，训练指标（如 `rows`、`placeholder` 等）会被写入指定的 Tracking Server 或默认的本地 `mlruns/` 目录。

## 3. 常见问题

- **没有看到任何实验记录？**
  确认是否设置了 `QLIB_USE_MLFLOW=1`，以及命令运行时与 MLflow Server 位于同一终端会话或脚本中。

- **提示 "MLflow not available"？**
  说明环境中未安装 MLflow，请先执行 `pip install mlflow`。

- **需要自定义实验名/Run 名？**
  可在 `config/base.yaml` 的 `mlflow` 字段中增加配置，例如：
  ```yaml
  mlflow:
    experiment_name: my_experiment
    run_name: demo-run
  ```
  该配置会被 `log_to_mlflow` 捕获并应用。

## 4. 后续扩展建议

- 将 MLflow Tracking Server 部署在团队可访问的服务器上，配合 S3/OSS 等对象存储保存工件。
- 利用 MLflow Projects 或 Pipelines 将训练脚本打包，支持参数化实验。
- 若需与指标告警结合，可在实验完成后订阅 Webhook 或使用 MLflow Model Registry。

如需更多示例，可参考 [MLflow 官方文档](https://mlflow.org/docs/latest/index.html)。
