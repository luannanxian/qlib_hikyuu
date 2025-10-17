# Qlib-Hikyuu 缺陷修复实施方案

## 执行摘要

基于两份分析报告（`task_completion_analysis.md` 和 `code_analysis_report.md`），本方案提供了详细的缺陷修复策略、具体实现代码和验证方法。方案按照问题严重程度分为P0（严重）、P1（中等）、P2（轻微）三个级别，确保最严重的问题优先得到解决。

## 一、P0级严重缺陷修复方案

### 1. 前视偏差（Lookahead Bias）修复

#### 问题描述
训练和预测使用相同的数据处理逻辑，导致预测时包含未来信息。

#### 修复方案

**文件**: `hikyuu_integration.py`

```python
# 修复后的代码
from typing import Optional
import pandas as pd

@dataclass
class HikyuuDataLoader(DataLoader):
    """基于 Hikyuu 的数据加载器，分离训练和预测数据处理"""

    fields: Sequence[str] = ("OPEN", "HIGH", "LOW", "CLOSE", "VOLUME", "AMOUNT")
    freq: str = "day"
    label_shift: int = 1
    mode: str = "train"  # 新增：区分训练和预测模式

    def load(
        self,
        instruments: Iterable[str],
        start_time: Optional[str],
        end_time: Optional[str],
    ) -> pd.DataFrame:
        """根据模式加载数据"""
        if self.mode == "train":
            return self._load_for_training(instruments, start_time, end_time)
        else:
            return self._load_for_prediction(instruments, start_time, end_time)

    def _load_for_training(
        self,
        instruments: Iterable[str],
        start_time: Optional[str],
        end_time: Optional[str],
    ) -> pd.DataFrame:
        """训练模式：包含标签"""
        frames = []
        for inst in instruments:
            hk_code = _to_hikyuu_code(inst)
            stock = self._sm[hk_code]
            if not _is_valid_stock(stock):
                logger.warning("Hikyuu 中找不到标的 %s，跳过。", inst)
                continue

            query = self._build_query(start_time, end_time)
            k_data = self._get_kdata(stock, query)
            if len(k_data) == 0:
                continue

            df = self._to_dataframe(k_data)
            df["instrument"] = inst

            # 训练模式：计算未来收益作为标签
            # 注意：这里使用未来数据是合理的，因为是训练时的目标值
            future_close = df["close"].shift(-self.label_shift)
            df["label"] = (future_close / df["close"]) - 1

            # 标记哪些数据有有效标签（用于训练）
            df["has_label"] = ~df["label"].isna()

            # 只保留有标签的数据用于训练
            df = df[df["has_label"]].copy()
            df.drop(columns=["has_label"], inplace=True)

            frames.append(df)

        if not frames:
            raise ValueError("未能从 Hikyuu 中加载到任何训练数据")

        return self._format_output(frames, include_label=True)

    def _load_for_prediction(
        self,
        instruments: Iterable[str],
        start_time: Optional[str],
        end_time: Optional[str],
    ) -> pd.DataFrame:
        """预测模式：不包含未来信息"""
        frames = []
        for inst in instruments:
            hk_code = _to_hikyuu_code(inst)
            stock = self._sm[hk_code]
            if not _is_valid_stock(stock):
                logger.warning("Hikyuu 中找不到标的 %s，跳过。", inst)
                continue

            query = self._build_query(start_time, end_time)
            k_data = self._get_kdata(stock, query)
            if len(k_data) == 0:
                continue

            df = self._to_dataframe(k_data)
            df["instrument"] = inst

            # 预测模式：不计算标签，避免使用未来信息
            # 可以添加占位符，但值为 NaN
            df["label"] = np.nan

            frames.append(df)

        if not frames:
            raise ValueError("未能从 Hikyuu 中加载到任何预测数据")

        return self._format_output(frames, include_label=False)

    def _format_output(self, frames: List[pd.DataFrame], include_label: bool) -> pd.DataFrame:
        """格式化输出数据"""
        data = pd.concat(frames, axis=0)
        data.set_index(["datetime", "instrument"], inplace=True)

        # 特征列
        feature_columns = []
        for field in self.fields:
            lower = field.lower()
            if lower in data.columns:
                feature_columns.append(("feature", field))

        feature_index = pd.MultiIndex.from_tuples(feature_columns, names=["group", "field"])
        feature_df = data[[f.lower() for f in self.fields if f.lower() in data.columns]]
        feature_df.columns = feature_index

        if include_label:
            # 训练模式：包含标签
            label_index = pd.MultiIndex.from_tuples([("label", "LABEL0")], names=["group", "field"])
            label_df = data[["label"]]
            label_df.columns = label_index
            return pd.concat([feature_df, label_df], axis=1).sort_index()
        else:
            # 预测模式：只返回特征
            return feature_df.sort_index()


class HikyuuAlphaHandler(DataHandlerLP):
    """改进的 Handler，支持训练和预测模式分离"""

    def __init__(
        self,
        instruments: Sequence[str] | str = "csi300",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        freq: str = "day",
        infer_processors: Optional[List] = None,
        learn_processors: Optional[List] = None,
        fit_start_time: Optional[str] = None,
        fit_end_time: Optional[str] = None,
        filter_pipe: Optional[List] = None,
        fields: Sequence[str] = ("OPEN", "HIGH", "LOW", "CLOSE", "VOLUME", "AMOUNT"),
        label_shift: int = 1,
        mode: str = "train",  # 新增：模式参数
    ):
        # 根据模式创建不同的 DataLoader
        loader = HikyuuDataLoader(
            fields=fields,
            freq=freq,
            label_shift=label_shift,
            mode=mode  # 传递模式参数
        )

        # 根据模式调整处理器
        if mode == "predict":
            # 预测模式：不处理标签
            learn_processors = [
                p for p in (learn_processors or [])
                if "label" not in str(p).lower()
            ]

        super().__init__(
            instruments=instruments,
            start_time=start_time,
            end_time=end_time,
            data_loader=loader,
            infer_processors=infer_processors,
            learn_processors=learn_processors,
            fit_start_time=fit_start_time,
            fit_end_time=fit_end_time,
            filter_pipe=filter_pipe,
        )
```

#### 验证测试

```python
# tests/test_lookahead_bias.py
import pytest
import pandas as pd
from hikyuu_integration import HikyuuDataLoader

def test_no_future_data_in_prediction():
    """确保预测模式不包含未来信息"""
    # 预测模式加载器
    loader = HikyuuDataLoader(mode="predict")

    # 加载数据
    data = loader.load(
        instruments=["SH600000"],
        start_time="2023-01-01",
        end_time="2023-01-31"
    )

    # 验证：预测数据不应包含有效的标签值
    if ("label", "LABEL0") in data.columns:
        label_data = data[("label", "LABEL0")]
        assert label_data.isna().all(), "预测模式包含了未来信息！"

def test_training_has_labels():
    """确保训练模式包含标签"""
    # 训练模式加载器
    loader = HikyuuDataLoader(mode="train")

    # 加载数据
    data = loader.load(
        instruments=["SH600000"],
        start_time="2023-01-01",
        end_time="2023-01-31"
    )

    # 验证：训练数据应包含标签
    assert ("label", "LABEL0") in data.columns
    label_data = data[("label", "LABEL0")]
    assert not label_data.isna().all(), "训练模式缺少标签！"

def test_data_consistency():
    """确保训练和预测的特征数据一致"""
    train_loader = HikyuuDataLoader(mode="train")
    pred_loader = HikyuuDataLoader(mode="predict")

    # 相同时间范围
    params = {
        "instruments": ["SH600000"],
        "start_time": "2023-01-01",
        "end_time": "2023-01-31"
    }

    train_data = train_loader.load(**params)
    pred_data = pred_loader.load(**params)

    # 验证特征列一致
    train_features = [col for col in train_data.columns if col[0] == "feature"]
    pred_features = [col for col in pred_data.columns if col[0] == "feature"]

    assert train_features == pred_features, "特征列不一致！"
```

---

### 2. 实现真实回测引擎

#### 问题描述
当前的 `run_backtest.py` 只是信号统计，没有真实的回测逻辑。

#### 修复方案

**新文件**: `scripts/run_real_backtest.py`

```python
#!/usr/bin/env python3
"""真实的回测引擎，包含交易执行和收益计算"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

@dataclass
class BacktestConfig:
    """回测配置"""
    initial_capital: float = 1_000_000.0  # 初始资金
    commission_rate: float = 0.0003      # 手续费率
    slippage_rate: float = 0.001        # 滑点
    t_plus: int = 1                     # T+N 交易延迟
    max_position_pct: float = 0.95      # 最大仓位比例

class BacktestEngine:
    """真实的回测引擎"""

    def __init__(self, config: BacktestConfig):
        self.config = config
        self.capital = config.initial_capital
        self.positions: Dict[str, int] = {}  # 当前持仓
        self.trades: List[Dict] = []         # 交易记录
        self.daily_values: List[Dict] = []   # 每日净值

    def run(
        self,
        signals: pd.DataFrame,
        prices: pd.DataFrame,
    ) -> Dict:
        """执行回测

        Args:
            signals: 交易信号 DataFrame，包含 date, instrument, weight 列
            prices: 价格数据 DataFrame，包含 date, instrument, open, close 列

        Returns:
            回测结果字典
        """
        # 确保数据按日期排序
        signals = signals.sort_values("date")
        prices = prices.sort_values("date")

        # 获取所有交易日
        trading_days = sorted(prices["date"].unique())

        for i, date in enumerate(trading_days):
            # T+N 执行延迟：使用 N 天前的信号
            signal_date_idx = i - self.config.t_plus
            if signal_date_idx < 0:
                # 初始几天没有信号
                self._record_daily_value(date, prices)
                continue

            signal_date = trading_days[signal_date_idx]

            # 获取当天信号
            today_signals = signals[signals["date"] == signal_date]

            # 获取当天价格
            today_prices = prices[prices["date"] == date]

            # 执行交易
            self._execute_trades(date, today_signals, today_prices)

            # 记录每日净值
            self._record_daily_value(date, today_prices)

        # 计算回测指标
        return self._calculate_metrics()

    def _execute_trades(
        self,
        date: str,
        signals: pd.DataFrame,
        prices: pd.DataFrame,
    ):
        """执行交易"""
        # 计算目标仓位
        target_positions = {}
        if not signals.empty:
            # 根据权重计算目标仓位
            total_weight = signals["weight"].abs().sum()
            if total_weight > 0:
                available_capital = self.capital * self.config.max_position_pct
                for _, row in signals.iterrows():
                    instrument = row["instrument"]
                    weight = row["weight"] / total_weight

                    # 获取执行价格（使用开盘价）
                    price_row = prices[prices["instrument"] == instrument]
                    if price_row.empty:
                        continue

                    exec_price = price_row.iloc[0]["open"]

                    # 考虑滑点
                    if weight > 0:  # 买入
                        exec_price *= (1 + self.config.slippage_rate)
                    else:  # 卖出
                        exec_price *= (1 - self.config.slippage_rate)

                    # 计算目标股数
                    target_value = available_capital * abs(weight)
                    target_shares = int(target_value / exec_price / 100) * 100  # 按手取整

                    if weight < 0:
                        target_shares = -target_shares

                    target_positions[instrument] = target_shares

        # 执行调仓
        for instrument, target_shares in target_positions.items():
            current_shares = self.positions.get(instrument, 0)
            trade_shares = target_shares - current_shares

            if trade_shares == 0:
                continue

            # 获取执行价格
            price_row = prices[prices["instrument"] == instrument]
            if price_row.empty:
                continue

            exec_price = price_row.iloc[0]["open"]

            # 考虑滑点
            if trade_shares > 0:
                exec_price *= (1 + self.config.slippage_rate)
            else:
                exec_price *= (1 - self.config.slippage_rate)

            # 计算交易金额和手续费
            trade_value = abs(trade_shares * exec_price)
            commission = trade_value * self.config.commission_rate

            # 更新资金
            if trade_shares > 0:  # 买入
                self.capital -= (trade_value + commission)
            else:  # 卖出
                self.capital += (trade_value - commission)

            # 更新持仓
            self.positions[instrument] = target_shares

            # 记录交易
            self.trades.append({
                "date": date,
                "instrument": instrument,
                "shares": trade_shares,
                "price": exec_price,
                "value": trade_value,
                "commission": commission,
                "capital_after": self.capital,
            })

        # 清理空仓
        self.positions = {k: v for k, v in self.positions.items() if v != 0}

    def _record_daily_value(self, date: str, prices: pd.DataFrame):
        """记录每日净值"""
        # 计算持仓市值
        position_value = 0
        for instrument, shares in self.positions.items():
            price_row = prices[prices["instrument"] == instrument]
            if not price_row.empty:
                close_price = price_row.iloc[0]["close"]
                position_value += shares * close_price

        # 总净值
        total_value = self.capital + position_value

        self.daily_values.append({
            "date": date,
            "capital": self.capital,
            "position_value": position_value,
            "total_value": total_value,
            "return": (total_value / self.config.initial_capital) - 1,
        })

    def _calculate_metrics(self) -> Dict:
        """计算回测指标"""
        if not self.daily_values:
            return {}

        df = pd.DataFrame(self.daily_values)
        df["daily_return"] = df["total_value"].pct_change()

        # 计算指标
        total_return = df["return"].iloc[-1]

        # 年化收益率（假设252个交易日）
        n_days = len(df)
        annual_return = (1 + total_return) ** (252 / n_days) - 1

        # 夏普比率
        daily_returns = df["daily_return"].dropna()
        if len(daily_returns) > 0:
            sharpe = np.sqrt(252) * daily_returns.mean() / daily_returns.std()
        else:
            sharpe = 0

        # 最大回撤
        cumulative = (1 + daily_returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        max_drawdown = drawdown.min()

        # 胜率
        n_trades = len(self.trades)
        if n_trades > 0:
            profitable_trades = sum(1 for t in self.trades if t["shares"] < 0)  # 卖出时判断
            win_rate = profitable_trades / n_trades
        else:
            win_rate = 0

        return {
            "total_return": total_return,
            "annual_return": annual_return,
            "sharpe_ratio": sharpe,
            "max_drawdown": max_drawdown,
            "win_rate": win_rate,
            "n_trades": n_trades,
            "final_value": df["total_value"].iloc[-1],
            "daily_values": df.to_dict("records"),
            "trades": self.trades,
        }

def load_signals(signal_path: Path) -> pd.DataFrame:
    """加载信号文件"""
    return pd.read_csv(signal_path)

def load_prices(data_path: Path) -> pd.DataFrame:
    """加载价格数据"""
    # 这里需要根据实际数据格式调整
    return pd.read_csv(data_path)

def main():
    parser = argparse.ArgumentParser(description="真实回测引擎")
    parser.add_argument("--signals", type=Path, required=True, help="信号文件路径")
    parser.add_argument("--prices", type=Path, required=True, help="价格数据路径")
    parser.add_argument("--output", type=Path, default=Path("reports/backtest_results.json"))
    parser.add_argument("--capital", type=float, default=1_000_000, help="初始资金")
    parser.add_argument("--commission", type=float, default=0.0003, help="手续费率")

    args = parser.parse_args()

    # 配置回测
    config = BacktestConfig(
        initial_capital=args.capital,
        commission_rate=args.commission,
    )

    # 加载数据
    signals = load_signals(args.signals)
    prices = load_prices(args.prices)

    # 执行回测
    engine = BacktestEngine(config)
    results = engine.run(signals, prices)

    # 保存结果
    import json
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)

    # 打印摘要
    print(f"回测完成:")
    print(f"  总收益率: {results['total_return']:.2%}")
    print(f"  年化收益率: {results['annual_return']:.2%}")
    print(f"  夏普比率: {results['sharpe_ratio']:.2f}")
    print(f"  最大回撤: {results['max_drawdown']:.2%}")
    print(f"  交易次数: {results['n_trades']}")

if __name__ == "__main__":
    main()
```

---

### 3. 修复环境变量污染

#### 问题描述
模块导入时修改全局 HOME 环境变量，可能影响其他模块。

#### 修复方案

**文件**: `hikyuu_integration.py`

```python
# 修复后的代码
import contextlib
import os
from pathlib import Path
from typing import Generator

@contextlib.contextmanager
def temporary_env_vars(**kwargs) -> Generator[None, None, None]:
    """临时修改环境变量的上下文管理器"""
    old_environ = dict(os.environ)
    os.environ.update(kwargs)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(old_environ)

def initialize_hikyuu():
    """安全地初始化 Hikyuu"""
    hk_home = _resolve_hikyuu_home()

    # 使用上下文管理器临时修改环境变量
    with temporary_env_vars(HKU_HOME=hk_home):
        try:
            import hikyuu as hk

            # 初始化配置
            config_path = Path(hk_home) / "hikyuu.ini"
            if config_path.exists():
                hk.hikyuu_init(str(config_path))

            return hk
        except ImportError as exc:
            raise ImportError("请先安装 hikyuu (pip install hikyuu)") from exc

# 延迟导入，避免模块加载时的副作用
_hikyuu = None

def get_hikyuu():
    """获取 Hikyuu 实例"""
    global _hikyuu
    if _hikyuu is None:
        _hikyuu = initialize_hikyuu()
    return _hikyuu

# 在需要使用 Hikyuu 的地方
class HikyuuDataLoader(DataLoader):
    def __post_init__(self):
        hk = get_hikyuu()  # 延迟初始化
        freq_map = {"day": hk.Query.DAY, "week": hk.Query.WEEK}
        self._hk_freq = freq_map[self.freq]
        self._sm = hk.StockManager.instance()
```

---

## 二、P1级中等缺陷修复方案

### 4. 改进错误处理机制

#### 修复方案

**文件**: `scripts/prepare_data.py`

```python
# 修复后的错误处理
import sys
from enum import Enum

class ErrorSeverity(Enum):
    """错误严重程度"""
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class DataPreparationError(Exception):
    """数据准备异常"""
    pass

def handle_error(exc: Exception, severity: ErrorSeverity, context: str):
    """统一的错误处理"""
    message = f"[{severity.value}] {context}: {exc}"

    if severity == ErrorSeverity.WARNING:
        logger.warning(message)
        # 记录但继续执行
    elif severity == ErrorSeverity.ERROR:
        logger.error(message)
        # 根据配置决定是否继续
        if not ALLOW_ERRORS:
            raise DataPreparationError(message) from exc
    elif severity == ErrorSeverity.CRITICAL:
        logger.critical(message)
        # 立即终止
        raise DataPreparationError(message) from exc

# 使用示例
try:
    data = load_data(instruments)
except FileNotFoundError as e:
    handle_error(e, ErrorSeverity.CRITICAL, "数据文件不存在")
except ValueError as e:
    handle_error(e, ErrorSeverity.ERROR, "数据格式错误")
except Exception as e:
    handle_error(e, ErrorSeverity.WARNING, "非关键错误")
```

### 5. 统一数据处理流程

#### 修复方案

**文件**: `scripts/train_model.py`

```python
# 创建统一的数据处理器
class UnifiedDataProcessor:
    """统一的数据预处理器，确保训练和预测一致"""

    def __init__(self, config: Dict):
        self.config = config
        self.fitted = False
        self.preprocessors = []

    def fit(self, data: pd.DataFrame):
        """训练时拟合预处理器"""
        self.preprocessors = [
            StandardScaler(),
            FeatureSelector(n_features=self.config.get("n_features", 20)),
        ]

        for prep in self.preprocessors:
            prep.fit(data)

        self.fitted = True

        # 保存预处理器
        self.save_preprocessors()

    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """应用预处理"""
        if not self.fitted:
            raise ValueError("预处理器未拟合")

        for prep in self.preprocessors:
            data = prep.transform(data)

        return data

    def save_preprocessors(self):
        """保存预处理器状态"""
        import pickle
        with open("models/preprocessors.pkl", "wb") as f:
            pickle.dump(self.preprocessors, f)

    def load_preprocessors(self):
        """加载预处理器状态"""
        import pickle
        with open("models/preprocessors.pkl", "rb") as f:
            self.preprocessors = pickle.load(f)
        self.fitted = True
```

---

## 三、未完成任务实施方案

### 6. 实现报告生成功能

**新文件**: `scripts/generate_report.py`

```python
#!/usr/bin/env python3
"""生成策略分析报告"""

import argparse
import json
from datetime import datetime
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
from jinja2 import Template

class ReportGenerator:
    """报告生成器"""

    def __init__(self, template_path: Path = None):
        self.template_path = template_path or Path("templates/report.html")

    def generate(
        self,
        backtest_results: Dict,
        output_path: Path,
        format: str = "html"
    ):
        """生成报告"""
        if format == "html":
            self._generate_html(backtest_results, output_path)
        elif format == "pdf":
            self._generate_pdf(backtest_results, output_path)
        else:
            self._generate_markdown(backtest_results, output_path)

    def _generate_html(self, results: Dict, output_path: Path):
        """生成HTML报告"""
        template = Template(self.template_path.read_text())

        # 准备数据
        context = {
            "title": "策略回测报告",
            "date": datetime.now().strftime("%Y-%m-%d"),
            "metrics": {
                "总收益率": f"{results['total_return']:.2%}",
                "年化收益率": f"{results['annual_return']:.2%}",
                "夏普比率": f"{results['sharpe_ratio']:.2f}",
                "最大回撤": f"{results['max_drawdown']:.2%}",
                "胜率": f"{results['win_rate']:.2%}",
            },
            "charts": self._generate_charts(results),
        }

        # 渲染模板
        html = template.render(context)
        output_path.write_text(html)

    def _generate_charts(self, results: Dict) -> Dict:
        """生成图表"""
        charts = {}

        # 净值曲线
        df = pd.DataFrame(results["daily_values"])

        fig, axes = plt.subplots(2, 2, figsize=(12, 8))

        # 1. 净值曲线
        ax = axes[0, 0]
        ax.plot(pd.to_datetime(df["date"]), df["total_value"])
        ax.set_title("净值曲线")
        ax.set_xlabel("日期")
        ax.set_ylabel("净值")

        # 2. 收益率曲线
        ax = axes[0, 1]
        ax.plot(pd.to_datetime(df["date"]), df["return"] * 100)
        ax.set_title("累计收益率")
        ax.set_xlabel("日期")
        ax.set_ylabel("收益率 (%)")

        # 3. 回撤曲线
        ax = axes[1, 0]
        cumulative = (1 + df["daily_return"]).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        ax.fill_between(df.index, drawdown * 100, alpha=0.3, color="red")
        ax.set_title("回撤")
        ax.set_xlabel("日期")
        ax.set_ylabel("回撤 (%)")

        # 4. 收益分布
        ax = axes[1, 1]
        ax.hist(df["daily_return"].dropna() * 100, bins=50, alpha=0.7)
        ax.set_title("日收益率分布")
        ax.set_xlabel("日收益率 (%)")
        ax.set_ylabel("频数")

        plt.tight_layout()

        # 保存图表
        chart_path = Path("reports/charts/performance.png")
        chart_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(chart_path)
        plt.close()

        charts["performance"] = str(chart_path)

        return charts

def main():
    parser = argparse.ArgumentParser(description="生成回测报告")
    parser.add_argument("--results", type=Path, required=True, help="回测结果文件")
    parser.add_argument("--output", type=Path, default=Path("reports/report.html"))
    parser.add_argument("--format", choices=["html", "pdf", "md"], default="html")

    args = parser.parse_args()

    # 加载回测结果
    with open(args.results) as f:
        results = json.load(f)

    # 生成报告
    generator = ReportGenerator()
    generator.generate(results, args.output, args.format)

    print(f"报告已生成: {args.output}")

if __name__ == "__main__":
    main()
```

### 7. 实现告警通知

**新文件**: `scripts/alert_manager.py`

```python
#!/usr/bin/env python3
"""告警管理器"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict
import json
from pathlib import Path

class AlertManager:
    """告警管理器"""

    def __init__(self, config_path: Path):
        with open(config_path) as f:
            self.config = json.load(f)

    def check_thresholds(self, metrics: Dict) -> List[str]:
        """检查阈值"""
        alerts = []

        thresholds = self.config.get("thresholds", {})

        # 检查各项指标
        if metrics.get("sharpe_ratio", 0) < thresholds.get("min_sharpe", 0.5):
            alerts.append(f"夏普比率过低: {metrics['sharpe_ratio']:.2f}")

        if abs(metrics.get("max_drawdown", 0)) > thresholds.get("max_drawdown", 0.2):
            alerts.append(f"回撤过大: {metrics['max_drawdown']:.2%}")

        if metrics.get("n_trades", 0) < thresholds.get("min_trades", 10):
            alerts.append(f"交易次数过少: {metrics['n_trades']}")

        return alerts

    def send_email(self, subject: str, body: str, to: List[str]):
        """发送邮件告警"""
        smtp_config = self.config.get("smtp", {})

        msg = MIMEMultipart()
        msg["From"] = smtp_config["sender"]
        msg["To"] = ", ".join(to)
        msg["Subject"] = subject

        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(smtp_config["host"], smtp_config["port"]) as server:
            if smtp_config.get("use_tls"):
                server.starttls()
            server.login(smtp_config["username"], smtp_config["password"])
            server.send_message(msg)

    def send_desktop_notification(self, title: str, message: str):
        """发送桌面通知"""
        try:
            import plyer
            plyer.notification.notify(
                title=title,
                message=message,
                timeout=10
            )
        except ImportError:
            print(f"桌面通知: {title} - {message}")

    def process_alerts(self, alerts: List[str]):
        """处理告警"""
        if not alerts:
            return

        # 构建告警消息
        message = "策略告警:\n\n" + "\n".join(f"- {alert}" for alert in alerts)

        # 发送邮件
        if self.config.get("email_enabled"):
            self.send_email(
                subject="量化策略告警",
                body=message,
                to=self.config.get("email_recipients", [])
            )

        # 发送桌面通知
        if self.config.get("desktop_enabled"):
            self.send_desktop_notification(
                title="策略告警",
                message=alerts[0]  # 显示第一条告警
            )

        # 记录日志
        with open("logs/alerts.log", "a") as f:
            f.write(f"{datetime.now()}: {message}\n")
```

### 8. 实现 Streamlit UI

**新文件**: `app.py`

```python
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path
import json

st.set_page_config(
    page_title="Qlib-Hikyuu 量化平台",
    page_icon="📈",
    layout="wide"
)

# 侧边栏
with st.sidebar:
    st.title("📊 量化交易平台")

    page = st.selectbox(
        "选择功能",
        ["回测分析", "实时监控", "策略管理", "数据管理"]
    )

# 主页面
if page == "回测分析":
    st.title("回测分析")

    # 文件上传
    uploaded_file = st.file_uploader(
        "上传回测结果文件",
        type=["json"]
    )

    if uploaded_file:
        results = json.load(uploaded_file)

        # 显示关键指标
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "总收益率",
                f"{results['total_return']:.2%}",
                f"{results['annual_return']:.2%} 年化"
            )

        with col2:
            st.metric(
                "夏普比率",
                f"{results['sharpe_ratio']:.2f}"
            )

        with col3:
            st.metric(
                "最大回撤",
                f"{results['max_drawdown']:.2%}"
            )

        with col4:
            st.metric(
                "交易次数",
                results['n_trades']
            )

        # 净值曲线
        st.subheader("净值曲线")

        df = pd.DataFrame(results["daily_values"])

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=pd.to_datetime(df["date"]),
            y=df["total_value"],
            mode='lines',
            name='净值'
        ))

        fig.update_layout(
            xaxis_title="日期",
            yaxis_title="净值",
            hovermode='x unified'
        )

        st.plotly_chart(fig, use_container_width=True)

        # 交易记录
        if st.checkbox("显示交易记录"):
            trades_df = pd.DataFrame(results["trades"])
            st.dataframe(trades_df)

elif page == "实时监控":
    st.title("实时监控")

    # 监控指标
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("系统状态")
        st.success("✅ 系统运行正常")
        st.info(f"最后更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    with col2:
        st.subheader("告警信息")

        # 读取告警日志
        alert_file = Path("logs/alerts.log")
        if alert_file.exists():
            alerts = alert_file.read_text().split("\n")[-5:]
            for alert in alerts:
                if alert:
                    st.warning(alert)
        else:
            st.success("无告警")

elif page == "策略管理":
    st.title("策略管理")

    # 策略列表
    strategies = [
        {"name": "Alpha158", "status": "运行中", "return": "12.5%"},
        {"name": "MACD策略", "status": "已停止", "return": "-2.3%"},
    ]

    df = pd.DataFrame(strategies)
    st.dataframe(df)

    # 新建策略
    if st.button("新建策略"):
        st.text_input("策略名称")
        st.text_area("策略代码")
        st.button("保存")

elif page == "数据管理":
    st.title("数据管理")

    # 数据源状态
    st.subheader("数据源状态")

    col1, col2 = st.columns(2)

    with col1:
        st.metric("Hikyuu 数据", "已连接", "实时")

    with col2:
        st.metric("Qlib 数据", "已同步", "2024-01-01")

    # 数据更新
    if st.button("更新数据"):
        with st.spinner("正在更新数据..."):
            # 执行数据更新
            st.success("数据更新完成")

# 运行: streamlit run app.py
```

---

## 四、验证和测试方案

### 1. 前视偏差测试套件

```python
# tests/test_lookahead_suite.py
import pytest
import pandas as pd
import numpy as np

class TestLookaheadBias:
    """前视偏差测试套件"""

    def test_train_test_split_no_overlap(self):
        """确保训练集和测试集没有时间重叠"""
        train_end = "2023-06-30"
        test_start = "2023-07-01"

        # 验证没有重叠
        assert pd.Timestamp(train_end) < pd.Timestamp(test_start)

    def test_feature_calculation_no_future(self):
        """确保特征计算不使用未来数据"""
        # 所有特征应该使用历史数据
        # shift(正数) 或不 shift
        pass

    def test_signal_execution_delay(self):
        """确保信号执行有延迟"""
        signal_date = "2023-01-01"
        execution_date = "2023-01-02"  # T+1

        # 验证执行延迟
        assert execution_date > signal_date
```

### 2. 集成测试

```python
# tests/test_integration.py
def test_end_to_end_workflow():
    """端到端工作流测试"""
    # 1. 数据准备
    subprocess.run(["python", "scripts/prepare_data.py"], check=True)

    # 2. 模型训练
    subprocess.run(["python", "scripts/train_model.py"], check=True)

    # 3. 信号生成
    subprocess.run(["python", "scripts/export_signals.py"], check=True)

    # 4. 回测执行
    subprocess.run(["python", "scripts/run_real_backtest.py"], check=True)

    # 5. 报告生成
    subprocess.run(["python", "scripts/generate_report.py"], check=True)

    # 验证输出文件存在
    assert Path("reports/report.html").exists()
```

---

## 五、实施计划

### 第1周：P0级修复
- [ ] Day 1-2: 修复前视偏差
- [ ] Day 3-4: 实现真实回测引擎
- [ ] Day 5: 修复环境变量污染

### 第2周：P1级修复 + 核心功能
- [ ] Day 1-2: 改进错误处理
- [ ] Day 3: 统一数据处理流程
- [ ] Day 4-5: 实现报告生成和告警

### 第3周：UI和测试
- [ ] Day 1-2: 实现 Streamlit UI
- [ ] Day 3-4: 完善测试套件
- [ ] Day 5: 集成测试和文档更新

### 第4周：优化和发布
- [ ] Day 1-2: 性能优化
- [ ] Day 3: 跨平台测试
- [ ] Day 4-5: 发布准备

---

## 六、成功标准

### 技术指标
- [ ] 前视偏差测试 100% 通过
- [ ] 回测结果与标准框架偏差 < 5%
- [ ] 测试覆盖率 > 80%
- [ ] 无 P0/P1 级缺陷

### 功能完整性
- [ ] 完整的回测功能
- [ ] 自动报告生成
- [ ] 告警通知机制
- [ ] 基础 UI 界面

### 性能指标
- [ ] 100万条数据回测 < 1分钟
- [ ] 内存占用 < 4GB
- [ ] UI 响应时间 < 1秒

---

*方案生成时间：2024-10-18*
*预计完成时间：4周*
*总体工作量：约160小时*