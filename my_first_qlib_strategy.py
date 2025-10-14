# --------------------------------------------------------------------------
# 完整的 Qlib Alpha 360 工作流代码
# 修复了 multiprocessing 错误
# --------------------------------------------------------------------------

import os
import sys

try:
    import gymnasium as _gymnasium
except ImportError:
    try:
        import gym_notices.notices as _gym_notices

        for _key in list(_gym_notices.notices.keys()):
            _gym_notices.notices[_key] = ""
    except Exception:
        pass
else:
    sys.modules.setdefault("gym", _gymnasium)

import qlib
from qlib.config import C
from qlib.constant import REG_CN
from qlib.utils import init_instance_by_config, get_date_by_shift
from qlib.workflow import R
from qlib.workflow.record_temp import SignalRecord, PortAnaRecord

# ==========================================================================
# 步骤 1: 定义配置 (这部分代码可以安全地放在主代码块之外)
# ==========================================================================

# 定义运行模式，"quick" 模式默认使用较小的数据范围与股票池提高速度
RUN_MODE = os.environ.get("QLIB_RUN_MODE", "quick").lower()
IS_QUICK_MODE = RUN_MODE in {"quick", "fast"}
DATA_SOURCE = os.environ.get("QLIB_DATA_SOURCE", "qlib").lower()
USE_HIKYUU = DATA_SOURCE == "hikyuu"

if USE_HIKYUU:
    from hikyuu_integration import HikyuuAlphaHandler  # 自定义 handler

# 基准指数维持沪深300，方便对比；股票池根据模式调整
benchmark = "SH000300"
market = "csi100" if IS_QUICK_MODE else "csi300"

# 根据模式调整时间切片
if IS_QUICK_MODE:
    handler_start = "2012-01-01"
    handler_end = "2020-12-31"
    fit_start = "2012-01-01"
    fit_end = "2017-12-31"
    segments = {
        "train": ("2012-01-01", "2017-12-31"),
        "valid": ("2018-01-01", "2018-12-31"),
        "test": ("2019-01-01", "2020-12-31"),
    }
    lgb_fast_params = {
        "n_estimators": 120,
        "num_leaves": 160,
        "learning_rate": 0.06,
    }
else:
    handler_start = "2010-01-01"
    handler_end = "2020-12-31"
    fit_start = "2010-01-01"
    fit_end = "2017-12-31"
    segments = {
        "train": ("2010-01-01", "2017-12-31"),
        "valid": ("2018-01-01", "2018-12-31"),
        "test": ("2019-01-01", "2020-12-31"),
    }
    lgb_fast_params = {}

if USE_HIKYUU:
    env_instruments = os.environ.get("QLIB_HIKYUU_INSTRUMENTS")
    instruments_seq = (
        [code.strip().upper() for code in env_instruments.split(",") if code.strip()]
        if env_instruments
        else ["SH000300", "SH600000", "SZ000001"]
    )
    field_tokens = [
        token.strip().upper()
        for token in os.environ.get("QLIB_HIKYUU_FIELDS", "OPEN,HIGH,LOW,CLOSE,VOLUME").split(",")
        if token.strip()
    ]
    data_handler_config = {
        "instruments": instruments_seq,
        "start_time": handler_start,
        "end_time": handler_end,
        "fit_start_time": fit_start,
        "fit_end_time": fit_end,
        "freq": os.environ.get("QLIB_HIKYUU_FREQ", "day"),
        "fields": tuple(field_tokens) or ("OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"),
        "label_shift": int(os.environ.get("QLIB_HIKYUU_LABEL_SHIFT", "1")),
    }
else:
    # 定义数据处理器 (Data Handler) 的配置
    # 它负责数据获取、预处理和特征工程
    data_handler_config = {
        "start_time": handler_start,
        "end_time": handler_end,
        "fit_start_time": fit_start,
        "fit_end_time": fit_end,
        "instruments": market,
        "drop_raw": True,
        # 标签数据的预处理流程
        "learn_processors": [
            {"class": "DropnaLabel"},
            {"class": "CSRankNorm", "kwargs": {"fields_group": "label"}}, # 对标签进行横截面排序归一化
        ],
        # 定义标签 (Label)。这里我们预测的是未来1天的收益率: (翌日收盘价 / 今日收盘价) - 1
        "label": ["Ref($close, -1) / $close - 1"],
    }

# 定义任务 (Task) 配置
# Task 整合了模型 (Model) 和数据集 (Dataset)
task = {
    "model": {
        "class": "LGBModel",  # 使用 LightGBM 模型
        "module_path": "qlib.contrib.model.gbdt",
        "kwargs": { # 模型的超参数
            "loss": "mse",
            "colsample_bytree": 0.8879,
            "learning_rate": 0.0421,
            "subsample": 0.8789,
            "lambda_l1": 205.6999,
            "lambda_l2": 580.9768,
            "max_depth": 8,
            "num_leaves": 210,
            "n_estimators": 200,
        },
    },
    "dataset": {
        "class": "DatasetH",
        "module_path": "qlib.data.dataset",
        "kwargs": {
            "handler": (
                {
                    "class": "HikyuuAlphaHandler",
                    "module_path": "hikyuu_integration",
                    "kwargs": data_handler_config,
                }
                if USE_HIKYUU
                else {
                    "class": "Alpha158",
                    "module_path": "qlib.contrib.data.handler",
                    "kwargs": data_handler_config,
                }
            ),
            "segments": { # 数据集切分: 训练集、验证集、测试集
                "train": segments["train"],
                "valid": segments["valid"],
                "test": segments["test"],
            },
        },
    },
}

# 根据模式对 LightGBM 进行快速配置
task["model"]["kwargs"].update(lgb_fast_params)

# ==========================================================================
# 步骤 2: 主执行逻辑 (必须放在 if __name__ == "__main__": 中)
# ==========================================================================

# 这个 if 语句是解决您遇到的问题的关键。
# 它确保了只有当这个脚本被直接执行时，下面的代码才会被运行。
# 当 Qlib 创建子进程进行数据处理时，子进程会导入此文件，但不会执行 if 块内的代码。
if __name__ == "__main__":

    # --- 初始化 Qlib ---
    # provider_uri 指向数据存放路径
    print("=" * 50)
    print("Step 1: Initializing Qlib...")
    qlib.init(provider_uri="~/.qlib/qlib_data/cn_data", region=REG_CN)
    # 启用多进程后端；如需切换，可通过环境变量 QLIB_JOBLIB_BACKEND 调整
    C.joblib_backend = os.environ.get("QLIB_JOBLIB_BACKEND", "multiprocessing")
    C.maxtasksperchild = None
    print("Qlib initialized successfully.")
    print("=" * 50)

    # --- 构建数据集和模型 ---
    print("Step 2: Building dataset and model...")
    dataset = init_instance_by_config(task["dataset"])
    model = init_instance_by_config(task["model"])
    print("Dataset and model built successfully.")
    print("=" * 50)

    # --- 训练、预测、回测与评估 ---
    # R 是 Qlib 的实验记录管理器 (Recorder)，它会记录所有实验产出
    experiment_name = "my_first_experiment"
    print(f"Step 3: Starting experiment '{experiment_name}'...")
    with R.start(experiment_name=experiment_name, resume=True):
        
        # 训练模型
        print("Training model...")
        model.fit(dataset)
        R.save_objects(trained_model=model)
        print("Model training finished.")
        
        recorder = R.get_recorder()
        signal_record = SignalRecord(model=model, dataset=dataset, recorder=recorder)

        # 在测试集上生成信号并保存到实验记录中
        print("Generating and logging prediction signals...")
        signal_record.generate()
        prediction_df = signal_record.load("pred.pkl")
        prediction = prediction_df.iloc[:, 0]
        R.save_objects(pred=prediction_df)
        print("Prediction saved.")

        # 准备回测配置
        strategy_config = {
            "class": "TopkDropoutStrategy",
            "module_path": "qlib.contrib.strategy.signal_strategy",
            "kwargs": {"signal": prediction, "topk": 30, "n_drop": 5},
        }

        executor_config = {
            "class": "SimulatorExecutor",
            "module_path": "qlib.backtest.executor",
            "kwargs": {
                "time_per_step": "day",
                "generate_portfolio_metrics": True,
            },
        }

        date_index = prediction_df.index.get_level_values("datetime")
        backtest_config = {
            "start_time": None,
            "end_time": None,
            "account": 100000000,
            "benchmark": benchmark,
            "exchange_kwargs": {
                "limit_threshold": 0.095,
                "deal_price": "close",
                "open_cost": 0.0005,
                "close_cost": 0.0015,
                "min_cost": 5,
            },
        }
        if len(date_index) > 0:
            backtest_config["start_time"] = date_index.min()
            try:
                backtest_config["end_time"] = get_date_by_shift(date_index.max(), -1)
            except ValueError:
                # 当无法向前偏移时，回落到使用最后一个交易日
                backtest_config["end_time"] = date_index.max()

        port_analysis_config = {
            "strategy": strategy_config,
            "executor": executor_config,
            "backtest": backtest_config,
        }
        
        # 使用 PortAnaRecord 来执行回测并生成详细的投资组合分析报告
        print("Backtesting and generating portfolio analysis...")
        port_ana_record = PortAnaRecord(recorder, port_analysis_config)
        port_ana_record.generate()
        print("Backtesting finished.")

    print("=" * 50)
    print(f"Workflow finished! Experiment '{experiment_name}' results are saved.")
    print("You can find the results in the folder: ./mlruns/")
    print("=" * 50)
