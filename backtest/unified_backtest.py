#!/usr/bin/env python3
"""
统一的回测接口，集成 Qlib 和 Hikyuu 的回测引擎
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Union
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class UnifiedBacktestConfig:
    """统一的回测配置"""
    # 基础配置
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    initial_capital: float = 1_000_000.0
    benchmark: Optional[str] = "SH000300"  # 沪深300

    # 交易成本
    commission_rate: float = 0.0003  # 手续费率
    slippage_rate: float = 0.001    # 滑点
    min_commission: float = 5.0      # 最低手续费

    # 执行配置
    t_plus: int = 1                  # T+N 交易延迟
    price_type: str = "close"         # 成交价类型: open, close, vwap

    # 风险控制
    max_position_pct: float = 0.95   # 最大仓位比例
    position_limit: int = 30          # 最大持仓数量

    # 回测引擎选择
    engine: str = "qlib"              # "qlib" 或 "hikyuu"


class BaseBacktestEngine(ABC):
    """回测引擎基类"""

    def __init__(self, config: UnifiedBacktestConfig):
        self.config = config

    @abstractmethod
    def run(self, signals: pd.DataFrame, **kwargs) -> Dict:
        """执行回测"""
        pass

    @abstractmethod
    def get_portfolio_metrics(self) -> pd.DataFrame:
        """获取组合指标"""
        pass


class QlibBacktestEngine(BaseBacktestEngine):
    """Qlib 回测引擎封装"""

    def __init__(self, config: UnifiedBacktestConfig):
        super().__init__(config)
        self.executor = None
        self.strategy = None
        self.report = None

    def run(self, signals: pd.DataFrame, **kwargs) -> Dict:
        """
        使用 Qlib 执行回测

        Args:
            signals: 预测信号 DataFrame，MultiIndex (datetime, instrument)
        """
        try:
            from qlib.backtest import get_exchange
            from qlib.backtest.executor import SimulatorExecutor
            from qlib.contrib.strategy.signal_strategy import TopkDropoutStrategy
            from qlib.contrib.evaluate import backtest_daily
            from qlib.contrib.evaluate import risk_analysis
        except ImportError:
            logger.error("Qlib 未安装或导入失败")
            raise

        # 准备交易所配置
        exchange_config = {
            "limit_threshold": 0.095,        # 涨跌停限制
            "deal_price": self.config.price_type,
            "open_cost": self.config.commission_rate,
            "close_cost": self.config.commission_rate + 0.001,  # 卖出印花税
            "min_cost": self.config.min_commission,
        }

        # 创建策略
        strategy_config = {
            "topk": min(self.config.position_limit, 30),
            "n_drop": 5,  # 每天卖出排名下降的股票数
            "signal": signals.iloc[:, 0] if isinstance(signals, pd.DataFrame) else signals,
        }

        self.strategy = TopkDropoutStrategy(**strategy_config)

        # 创建执行器
        executor_config = {
            "time_per_step": "day",
            "generate_portfolio_metrics": True,
            "verbose": kwargs.get("verbose", False),
        }

        self.executor = SimulatorExecutor(**executor_config)

        # 获取时间范围
        if signals.index.nlevels == 2:  # MultiIndex
            date_index = signals.index.get_level_values("datetime")
        else:
            date_index = signals.index

        start_time = self.config.start_time or str(date_index.min())
        end_time = self.config.end_time or str(date_index.max())

        # 执行回测
        logger.info(f"使用 Qlib 引擎执行回测: {start_time} 至 {end_time}")

        with get_exchange(
            start_time=start_time,
            end_time=end_time,
            codes=None,  # 使用所有股票
            deal_price=exchange_config["deal_price"],
            open_cost=exchange_config["open_cost"],
            close_cost=exchange_config["close_cost"],
            min_cost=exchange_config["min_cost"],
            limit_threshold=exchange_config["limit_threshold"],
            executor=self.executor,
        ) as exchange:
            # 运行策略
            trade_decisions = self.strategy.generate_trade_decision(exchange)

            # 获取回测报告
            report_df, positions = backtest_daily(
                start_time=start_time,
                end_time=end_time,
                strategy=self.strategy,
                executor=self.executor,
                backtest_config={
                    "account": self.config.initial_capital,
                    "benchmark": self.config.benchmark,
                    "exchange_kwargs": exchange_config,
                }
            )

            self.report = report_df

        # 计算风险指标
        metrics = self._calculate_metrics(report_df)

        return {
            "engine": "qlib",
            "metrics": metrics,
            "report": report_df,
            "positions": positions
        }

    def _calculate_metrics(self, report_df: pd.DataFrame) -> Dict:
        """计算回测指标"""
        if report_df is None or report_df.empty:
            return {}

        # 计算收益率
        total_return = (report_df["cum_return"].iloc[-1] - 1) * 100 if "cum_return" in report_df else 0

        # 计算年化收益
        days = len(report_df)
        annual_return = (np.power(1 + total_return/100, 252/days) - 1) * 100 if days > 0 else 0

        # 计算夏普比率
        if "return" in report_df:
            daily_returns = report_df["return"]
            sharpe = np.sqrt(252) * daily_returns.mean() / daily_returns.std() if daily_returns.std() > 0 else 0
        else:
            sharpe = 0

        # 计算最大回撤
        if "cum_return" in report_df:
            cum_returns = report_df["cum_return"]
            running_max = cum_returns.expanding().max()
            drawdown = (cum_returns - running_max) / running_max
            max_drawdown = drawdown.min() * 100
        else:
            max_drawdown = 0

        return {
            "total_return": round(total_return, 2),
            "annual_return": round(annual_return, 2),
            "sharpe_ratio": round(sharpe, 3),
            "max_drawdown": round(max_drawdown, 2),
            "trading_days": days
        }

    def get_portfolio_metrics(self) -> pd.DataFrame:
        """获取组合指标"""
        return self.report if self.report is not None else pd.DataFrame()


class HikyuuBacktestEngine(BaseBacktestEngine):
    """Hikyuu 回测引擎封装"""

    def __init__(self, config: UnifiedBacktestConfig):
        super().__init__(config)
        self.sys = None
        self.tm = None

    def run(self, signals: pd.DataFrame, **kwargs) -> Dict:
        """
        使用 Hikyuu 执行回测

        Args:
            signals: 预测信号 DataFrame
        """
        try:
            import hikyuu as hk
        except ImportError:
            logger.error("Hikyuu 未安装或导入失败")
            raise

        # 初始化 Hikyuu
        hk.hikyuu_init()

        # 获取股票池
        if signals.index.nlevels == 2:  # MultiIndex
            stocks = signals.index.get_level_values("instrument").unique()
            date_index = signals.index.get_level_values("datetime")
        else:
            stocks = signals.columns if signals.columns.size > 1 else ["SH000001"]
            date_index = signals.index

        # 创建交易系统
        self.sys = hk.System()

        # 设置资金管理
        self.tm = hk.TM()
        self.tm.init_cash = self.config.initial_capital
        self.tm.init_datetime = hk.Datetime(str(date_index.min()))

        # 设置交易成本
        tc = hk.TC_FixedA(
            buy_cost=self.config.commission_rate,
            sell_cost=self.config.commission_rate + 0.001,  # 印花税
            min_cost=self.config.min_commission
        )
        self.tm.cost_func = tc

        # 创建信号指示器
        sg = self._create_signal_indicator(signals, stocks)

        # 设置止损策略
        st = hk.ST_FixedPercent(0.1)  # 10% 止损

        # 设置资金分配策略
        mm = hk.MM_FixedCount(self.config.initial_capital / self.config.position_limit)

        # 组装系统
        self.sys.tm = self.tm
        self.sys.sg = sg
        self.sys.st = st
        self.sys.mm = mm

        # 运行回测
        logger.info(f"使用 Hikyuu 引擎执行回测")

        # 对每个股票运行系统
        results = []
        for stock_code in stocks:
            try:
                stock = hk.get_stock(stock_code)
                if stock.is_null():
                    logger.warning(f"股票 {stock_code} 不存在")
                    continue

                # 运行系统
                self.sys.run(stock, hk.Query(-1))

                # 获取交易记录
                trade_list = self.tm.get_trade_list()
                for trade in trade_list:
                    results.append({
                        "datetime": str(trade.datetime),
                        "stock": trade.stock.market_code,
                        "business": "BUY" if trade.business == hk.BUSINESS.BUY else "SELL",
                        "price": trade.real_price,
                        "number": trade.number,
                        "cost": trade.cost,
                        "cash": trade.cash
                    })

            except Exception as e:
                logger.error(f"处理股票 {stock_code} 时出错: {e}")
                continue

        # 计算指标
        metrics = self._calculate_hikyuu_metrics()

        return {
            "engine": "hikyuu",
            "metrics": metrics,
            "trades": pd.DataFrame(results) if results else pd.DataFrame(),
            "final_cash": self.tm.current_cash if self.tm else self.config.initial_capital
        }

    def _create_signal_indicator(self, signals: pd.DataFrame, stocks: List[str]):
        """创建 Hikyuu 信号指示器"""
        import hikyuu as hk

        # 简单的信号指示器：基于预测值的阈值
        # 这里需要根据具体的信号格式来调整
        class CustomSignal(hk.SignalBase):
            def __init__(self, signals_df):
                super().__init__()
                self.signals = signals_df

            def _calculate(self):
                # 根据信号生成买卖点
                # 这里简化处理，实际应根据信号强度判断
                pass

        return CustomSignal(signals)

    def _calculate_hikyuu_metrics(self) -> Dict:
        """计算 Hikyuu 回测指标"""
        if self.tm is None:
            return {}

        # 获取资金曲线
        funds_curve = self.tm.get_funds_curve()

        if len(funds_curve) == 0:
            return {}

        # 计算收益率
        initial = self.config.initial_capital
        final = funds_curve[-1] if len(funds_curve) > 0 else initial
        total_return = (final / initial - 1) * 100

        # 计算年化收益
        days = len(funds_curve)
        annual_return = (np.power(final / initial, 252/days) - 1) * 100 if days > 0 else 0

        # 计算最大回撤
        max_value = initial
        max_dd = 0
        for value in funds_curve:
            if value > max_value:
                max_value = value
            dd = (value - max_value) / max_value
            if dd < max_dd:
                max_dd = dd

        # 获取交易统计
        trade_list = self.tm.get_trade_list() if self.tm else []
        total_trades = len(trade_list)

        win_trades = [t for t in trade_list if t.profit > 0]
        win_rate = len(win_trades) / total_trades * 100 if total_trades > 0 else 0

        return {
            "total_return": round(total_return, 2),
            "annual_return": round(annual_return, 2),
            "max_drawdown": round(max_dd * 100, 2),
            "total_trades": total_trades,
            "win_rate": round(win_rate, 2),
            "final_value": round(final, 2)
        }

    def get_portfolio_metrics(self) -> pd.DataFrame:
        """获取组合指标"""
        if self.tm is None:
            return pd.DataFrame()

        # 返回资金曲线
        funds_curve = self.tm.get_funds_curve()
        return pd.DataFrame({
            "value": funds_curve,
            "returns": pd.Series(funds_curve).pct_change()
        })


class UnifiedBacktest:
    """统一的回测接口"""

    def __init__(self, config: UnifiedBacktestConfig):
        self.config = config
        self.engine = self._create_engine()

    def _create_engine(self) -> BaseBacktestEngine:
        """创建回测引擎"""
        if self.config.engine.lower() == "qlib":
            return QlibBacktestEngine(self.config)
        elif self.config.engine.lower() == "hikyuu":
            return HikyuuBacktestEngine(self.config)
        else:
            raise ValueError(f"不支持的回测引擎: {self.config.engine}")

    def run(self, signals: pd.DataFrame, **kwargs) -> Dict:
        """
        执行统一回测

        Args:
            signals: 交易信号
            **kwargs: 额外参数

        Returns:
            回测结果字典
        """
        logger.info(f"使用 {self.config.engine} 引擎执行回测")

        # 数据验证
        if signals is None or signals.empty:
            raise ValueError("信号数据为空")

        # 执行回测
        try:
            results = self.engine.run(signals, **kwargs)

            # 添加配置信息
            results["config"] = {
                "engine": self.config.engine,
                "initial_capital": self.config.initial_capital,
                "commission_rate": self.config.commission_rate,
                "t_plus": self.config.t_plus,
                "benchmark": self.config.benchmark
            }

            return results

        except Exception as e:
            logger.error(f"回测执行失败: {e}")
            raise

    def compare_engines(self, signals: pd.DataFrame) -> pd.DataFrame:
        """
        使用两个引擎对比回测结果

        Args:
            signals: 交易信号

        Returns:
            对比结果 DataFrame
        """
        results = []

        # 使用 Qlib 回测
        try:
            self.config.engine = "qlib"
            self.engine = QlibBacktestEngine(self.config)
            qlib_result = self.run(signals)
            results.append({
                "engine": "Qlib",
                **qlib_result.get("metrics", {})
            })
        except Exception as e:
            logger.error(f"Qlib 回测失败: {e}")
            results.append({"engine": "Qlib", "error": str(e)})

        # 使用 Hikyuu 回测
        try:
            self.config.engine = "hikyuu"
            self.engine = HikyuuBacktestEngine(self.config)
            hikyuu_result = self.run(signals)
            results.append({
                "engine": "Hikyuu",
                **hikyuu_result.get("metrics", {})
            })
        except Exception as e:
            logger.error(f"Hikyuu 回测失败: {e}")
            results.append({"engine": "Hikyuu", "error": str(e)})

        # 返回对比结果
        return pd.DataFrame(results)

    def save_results(self, results: Dict, output_dir: Path):
        """保存回测结果"""
        output_dir.mkdir(parents=True, exist_ok=True)

        # 保存指标
        import json
        metrics_file = output_dir / "metrics.json"
        with open(metrics_file, "w") as f:
            json.dump(results.get("metrics", {}), f, indent=2, default=str)

        # 保存报告
        if "report" in results and results["report"] is not None:
            report_file = output_dir / "report.csv"
            results["report"].to_csv(report_file)

        # 保存交易记录
        if "trades" in results and results["trades"] is not None:
            trades_file = output_dir / "trades.csv"
            results["trades"].to_csv(trades_file, index=False)

        logger.info(f"结果已保存到 {output_dir}")


def main():
    """测试统一回测接口"""
    import argparse

    parser = argparse.ArgumentParser(description="统一回测接口")
    parser.add_argument("--signals", type=Path, required=True, help="信号文件")
    parser.add_argument("--engine", choices=["qlib", "hikyuu", "both"], default="qlib", help="回测引擎")
    parser.add_argument("--output", type=Path, default=Path("reports/unified_backtest"), help="输出目录")
    parser.add_argument("--capital", type=float, default=1_000_000, help="初始资金")
    parser.add_argument("--benchmark", type=str, default="SH000300", help="基准指数")

    args = parser.parse_args()

    # 设置日志
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    # 加载信号
    signals = pd.read_csv(args.signals, index_col=[0, 1] if "instrument" in pd.read_csv(args.signals, nrows=1).columns else 0)

    # 创建配置
    config = UnifiedBacktestConfig(
        initial_capital=args.capital,
        benchmark=args.benchmark,
        engine=args.engine if args.engine != "both" else "qlib"
    )

    # 执行回测
    backtest = UnifiedBacktest(config)

    if args.engine == "both":
        # 对比两个引擎
        comparison = backtest.compare_engines(signals)
        print("\n引擎对比结果:")
        print(comparison)
        comparison.to_csv(args.output / "comparison.csv", index=False)
    else:
        # 单引擎回测
        results = backtest.run(signals)
        backtest.save_results(results, args.output)

        print(f"\n{args.engine.upper()} 回测结果:")
        for key, value in results.get("metrics", {}).items():
            print(f"{key:20}: {value}")

    return 0


if __name__ == "__main__":
    exit(main())