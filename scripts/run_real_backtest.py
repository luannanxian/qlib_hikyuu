#!/usr/bin/env python3
"""真实的回测引擎，包含交易执行和收益计算"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

@dataclass
class BacktestConfig:
    """回测配置"""
    initial_capital: float = 1_000_000.0  # 初始资金
    commission_rate: float = 0.0003       # 手续费率（万三）
    slippage_rate: float = 0.001         # 滑点（千一）
    t_plus: int = 1                      # T+N 交易延迟
    max_position_pct: float = 0.95       # 最大仓位比例
    min_trade_value: float = 10000.0     # 最小交易金额

    def to_dict(self) -> Dict:
        """转换为字典"""
        return asdict(self)


class Position:
    """持仓信息"""

    def __init__(self, instrument: str):
        self.instrument = instrument
        self.shares = 0
        self.avg_cost = 0.0
        self.market_value = 0.0
        self.unrealized_pnl = 0.0

    def update_price(self, price: float):
        """更新市值和未实现盈亏"""
        self.market_value = self.shares * price
        if self.shares > 0:
            self.unrealized_pnl = (price - self.avg_cost) * self.shares
        else:
            self.unrealized_pnl = 0.0

    def add_shares(self, shares: int, price: float, commission: float):
        """增加持仓"""
        if self.shares == 0:
            self.avg_cost = price + commission / shares
        else:
            total_cost = self.avg_cost * self.shares + price * shares + commission
            self.shares += shares
            self.avg_cost = total_cost / self.shares if self.shares > 0 else 0

    def reduce_shares(self, shares: int, price: float, commission: float) -> float:
        """减少持仓，返回实现盈亏"""
        if shares > self.shares:
            shares = self.shares

        realized_pnl = (price - self.avg_cost) * shares - commission
        self.shares -= shares

        if self.shares == 0:
            self.avg_cost = 0.0

        return realized_pnl


class BacktestEngine:
    """真实的回测引擎"""

    def __init__(self, config: BacktestConfig):
        self.config = config
        self.capital = config.initial_capital
        self.cash = config.initial_capital
        self.positions: Dict[str, Position] = {}  # 当前持仓
        self.trades: List[Dict] = []             # 交易记录
        self.daily_values: List[Dict] = []       # 每日净值
        self.pending_orders: List[Dict] = []     # 待执行订单（T+N）

    def run(
        self,
        signals: pd.DataFrame,
        prices: pd.DataFrame,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict:
        """执行回测

        Args:
            signals: 交易信号 DataFrame，columns=[datetime, instrument, weight]
            prices: 价格数据 DataFrame，columns=[datetime, instrument, open, high, low, close, volume]
            start_date: 回测开始日期
            end_date: 回测结束日期

        Returns:
            回测结果字典
        """
        # 数据预处理
        signals = self._preprocess_signals(signals)
        prices = self._preprocess_prices(prices, start_date, end_date)

        if prices.empty:
            raise ValueError("价格数据为空，无法执行回测")

        # 获取所有交易日
        trading_days = sorted(prices["datetime"].unique())
        logger.info(f"回测期间: {trading_days[0]} 至 {trading_days[-1]}, 共 {len(trading_days)} 个交易日")

        for i, date in enumerate(trading_days):
            # 处理 T+N 延迟的订单
            self._process_pending_orders(date, prices)

            # 生成新订单（T+N 后执行）
            if i >= self.config.t_plus:
                signal_date = trading_days[i - self.config.t_plus]
                today_signals = signals[signals["datetime"] == signal_date]

                if not today_signals.empty:
                    self._generate_orders(date, today_signals, prices)

            # 更新持仓市值
            self._update_positions(date, prices)

            # 记录每日净值
            self._record_daily_value(date)

        # 计算回测指标
        results = self._calculate_metrics()
        results["config"] = self.config.to_dict()

        return results

    def _preprocess_signals(self, signals: pd.DataFrame) -> pd.DataFrame:
        """预处理信号数据"""
        signals = signals.copy()

        # 确保有必要的列
        required_cols = ["datetime", "instrument", "weight"]
        for col in required_cols:
            if col not in signals.columns:
                raise ValueError(f"信号数据缺少必要的列: {col}")

        # 转换日期格式
        signals["datetime"] = pd.to_datetime(signals["datetime"])

        # 标准化权重
        signals = signals.groupby("datetime").apply(self._normalize_weights).reset_index(drop=True)

        return signals.sort_values("datetime")

    def _normalize_weights(self, group: pd.DataFrame) -> pd.DataFrame:
        """标准化权重到 [-1, 1]"""
        total_weight = group["weight"].abs().sum()
        if total_weight > 0:
            group["weight"] = group["weight"] / total_weight
        return group

    def _preprocess_prices(
        self,
        prices: pd.DataFrame,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """预处理价格数据"""
        prices = prices.copy()

        # 确保有必要的列
        required_cols = ["datetime", "instrument", "open", "close"]
        for col in required_cols:
            if col not in prices.columns:
                raise ValueError(f"价格数据缺少必要的列: {col}")

        # 转换日期格式
        prices["datetime"] = pd.to_datetime(prices["datetime"])

        # 过滤日期范围
        if start_date:
            prices = prices[prices["datetime"] >= pd.to_datetime(start_date)]
        if end_date:
            prices = prices[prices["datetime"] <= pd.to_datetime(end_date)]

        return prices.sort_values(["datetime", "instrument"])

    def _generate_orders(
        self,
        date: pd.Timestamp,
        signals: pd.DataFrame,
        prices: pd.DataFrame
    ):
        """根据信号生成订单（T+N 后执行）"""
        execution_date = date + pd.Timedelta(days=self.config.t_plus)

        for _, signal in signals.iterrows():
            instrument = signal["instrument"]
            weight = signal["weight"]

            if abs(weight) < 0.001:  # 忽略太小的权重
                continue

            # 创建订单
            order = {
                "generate_date": date,
                "execution_date": execution_date,
                "instrument": instrument,
                "weight": weight,
                "status": "pending"
            }

            self.pending_orders.append(order)

    def _process_pending_orders(self, date: pd.Timestamp, prices: pd.DataFrame):
        """处理待执行订单"""
        # 找出今天要执行的订单
        orders_to_execute = [
            order for order in self.pending_orders
            if order["execution_date"] <= date and order["status"] == "pending"
        ]

        if not orders_to_execute:
            return

        # 获取当日价格
        today_prices = prices[prices["datetime"] == date]

        # 计算目标仓位
        target_positions = self._calculate_target_positions(orders_to_execute, today_prices)

        # 执行调仓
        self._rebalance_positions(date, target_positions, today_prices)

        # 标记订单已执行
        for order in orders_to_execute:
            order["status"] = "executed"

    def _calculate_target_positions(
        self,
        orders: List[Dict],
        prices: pd.DataFrame
    ) -> Dict[str, int]:
        """计算目标仓位"""
        target_positions = {}

        # 计算总权重
        total_weight = sum(abs(order["weight"]) for order in orders)
        if total_weight == 0:
            return target_positions

        # 计算可用资金
        total_value = self._get_total_value(prices)
        available_capital = total_value * self.config.max_position_pct

        for order in orders:
            instrument = order["instrument"]
            weight = order["weight"] / total_weight  # 归一化权重

            # 获取当前价格
            price_row = prices[prices["instrument"] == instrument]
            if price_row.empty:
                logger.warning(f"无法获取 {instrument} 在 {prices.iloc[0]['datetime']} 的价格")
                continue

            current_price = price_row.iloc[0]["open"]  # 使用开盘价执行

            # 计算目标股数
            target_value = available_capital * abs(weight)
            if target_value < self.config.min_trade_value:
                continue  # 金额太小，跳过

            target_shares = int(target_value / current_price / 100) * 100  # 按手取整

            if weight < 0:
                target_shares = -target_shares

            target_positions[instrument] = target_shares

        return target_positions

    def _rebalance_positions(
        self,
        date: pd.Timestamp,
        target_positions: Dict[str, int],
        prices: pd.DataFrame
    ):
        """调仓到目标仓位"""
        # 先卖出
        for instrument in list(self.positions.keys()):
            current_pos = self.positions[instrument]
            target_shares = target_positions.get(instrument, 0)

            if current_pos.shares > target_shares:
                # 需要卖出
                self._execute_trade(
                    date,
                    instrument,
                    current_pos.shares - target_shares,
                    "sell",
                    prices
                )

        # 再买入
        for instrument, target_shares in target_positions.items():
            current_shares = self.positions.get(instrument, Position(instrument)).shares

            if target_shares > current_shares:
                # 需要买入
                self._execute_trade(
                    date,
                    instrument,
                    target_shares - current_shares,
                    "buy",
                    prices
                )

    def _execute_trade(
        self,
        date: pd.Timestamp,
        instrument: str,
        shares: int,
        side: str,
        prices: pd.DataFrame
    ):
        """执行交易"""
        if shares <= 0:
            return

        # 获取执行价格
        price_row = prices[prices["instrument"] == instrument]
        if price_row.empty:
            logger.warning(f"无法执行交易：找不到 {instrument} 的价格")
            return

        exec_price = price_row.iloc[0]["open"]

        # 考虑滑点
        if side == "buy":
            exec_price *= (1 + self.config.slippage_rate)
        else:
            exec_price *= (1 - self.config.slippage_rate)

        # 计算手续费
        trade_value = shares * exec_price
        commission = trade_value * self.config.commission_rate

        # 检查资金是否充足（买入时）
        if side == "buy":
            required_cash = trade_value + commission
            if required_cash > self.cash:
                # 资金不足，调整购买数量
                available_cash = self.cash * 0.99  # 留一点余量
                shares = int(available_cash / (exec_price * (1 + self.config.commission_rate)) / 100) * 100
                if shares <= 0:
                    logger.warning(f"资金不足，无法买入 {instrument}")
                    return
                trade_value = shares * exec_price
                commission = trade_value * self.config.commission_rate

        # 更新持仓
        if instrument not in self.positions:
            self.positions[instrument] = Position(instrument)

        position = self.positions[instrument]

        if side == "buy":
            position.add_shares(shares, exec_price, commission)
            self.cash -= (trade_value + commission)
            realized_pnl = 0
        else:
            realized_pnl = position.reduce_shares(shares, exec_price, commission)
            self.cash += (trade_value - commission)

        # 记录交易
        trade = {
            "datetime": date,
            "instrument": instrument,
            "side": side,
            "shares": shares,
            "price": exec_price,
            "value": trade_value,
            "commission": commission,
            "realized_pnl": realized_pnl,
            "cash_after": self.cash
        }

        self.trades.append(trade)

        logger.debug(f"{date}: {side} {shares} shares of {instrument} at {exec_price:.2f}")

    def _update_positions(self, date: pd.Timestamp, prices: pd.DataFrame):
        """更新持仓市值"""
        today_prices = prices[prices["datetime"] == date]

        for instrument, position in self.positions.items():
            if position.shares == 0:
                continue

            price_row = today_prices[today_prices["instrument"] == instrument]
            if not price_row.empty:
                current_price = price_row.iloc[0]["close"]
                position.update_price(current_price)

    def _get_total_value(self, prices: pd.DataFrame) -> float:
        """计算总资产价值"""
        total = self.cash

        for instrument, position in self.positions.items():
            if position.shares > 0:
                price_row = prices[prices["instrument"] == instrument]
                if not price_row.empty:
                    current_price = price_row.iloc[0]["close"]
                    total += position.shares * current_price

        return total

    def _record_daily_value(self, date: pd.Timestamp):
        """记录每日净值"""
        # 计算总市值
        total_position_value = sum(pos.market_value for pos in self.positions.values())
        total_value = self.cash + total_position_value

        # 计算收益
        returns = (total_value / self.config.initial_capital - 1) * 100

        daily_record = {
            "datetime": date,
            "cash": self.cash,
            "position_value": total_position_value,
            "total_value": total_value,
            "returns": returns
        }

        self.daily_values.append(daily_record)

    def _calculate_metrics(self) -> Dict:
        """计算回测指标"""
        if not self.daily_values:
            return {"error": "没有交易记录"}

        # 转换为 DataFrame
        df = pd.DataFrame(self.daily_values)
        df["daily_return"] = df["total_value"].pct_change()

        # 计算指标
        total_return = (df["total_value"].iloc[-1] / self.config.initial_capital - 1) * 100

        # 年化收益率（假设252个交易日）
        trading_days = len(df)
        years = trading_days / 252
        annual_return = (np.power(df["total_value"].iloc[-1] / self.config.initial_capital, 1/years) - 1) * 100 if years > 0 else 0

        # 夏普比率
        daily_returns = df["daily_return"].dropna()
        if len(daily_returns) > 0:
            sharpe_ratio = np.sqrt(252) * daily_returns.mean() / daily_returns.std() if daily_returns.std() > 0 else 0
        else:
            sharpe_ratio = 0

        # 最大回撤
        cumulative = df["total_value"] / self.config.initial_capital
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max * 100
        max_drawdown = drawdown.min()

        # 交易统计
        total_trades = len(self.trades)
        if total_trades > 0:
            trades_df = pd.DataFrame(self.trades)
            winning_trades = trades_df[trades_df["realized_pnl"] > 0]
            losing_trades = trades_df[trades_df["realized_pnl"] < 0]

            win_rate = len(winning_trades) / total_trades * 100
            avg_win = winning_trades["realized_pnl"].mean() if len(winning_trades) > 0 else 0
            avg_loss = losing_trades["realized_pnl"].mean() if len(losing_trades) > 0 else 0
            total_commission = trades_df["commission"].sum()
        else:
            win_rate = 0
            avg_win = 0
            avg_loss = 0
            total_commission = 0

        metrics = {
            "total_return": round(total_return, 2),
            "annual_return": round(annual_return, 2),
            "sharpe_ratio": round(sharpe_ratio, 3),
            "max_drawdown": round(max_drawdown, 2),
            "total_trades": total_trades,
            "win_rate": round(win_rate, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "total_commission": round(total_commission, 2),
            "final_value": round(df["total_value"].iloc[-1], 2),
            "trading_days": trading_days
        }

        return metrics

    def save_results(self, output_dir: Path):
        """保存回测结果"""
        output_dir.mkdir(parents=True, exist_ok=True)

        # 保存交易记录
        if self.trades:
            trades_df = pd.DataFrame(self.trades)
            trades_df.to_csv(output_dir / "trades.csv", index=False)

        # 保存每日净值
        if self.daily_values:
            values_df = pd.DataFrame(self.daily_values)
            values_df.to_csv(output_dir / "daily_values.csv", index=False)

        # 保存指标
        metrics = self._calculate_metrics()
        with open(output_dir / "metrics.json", "w") as f:
            json.dump(metrics, f, indent=2, default=str)

        logger.info(f"回测结果已保存到 {output_dir}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="真实回测引擎")
    parser.add_argument("--signals", type=Path, required=True, help="信号文件路径")
    parser.add_argument("--prices", type=Path, required=True, help="价格文件路径")
    parser.add_argument("--output", type=Path, default=Path("reports/backtest"), help="输出目录")
    parser.add_argument("--capital", type=float, default=1_000_000, help="初始资金")
    parser.add_argument("--commission", type=float, default=0.0003, help="手续费率")
    parser.add_argument("--slippage", type=float, default=0.001, help="滑点")
    parser.add_argument("--t-plus", type=int, default=1, help="T+N 延迟")
    parser.add_argument("--start-date", type=str, help="回测开始日期")
    parser.add_argument("--end-date", type=str, help="回测结束日期")
    parser.add_argument("--verbose", action="store_true", help="详细输出")

    args = parser.parse_args()

    # 设置日志
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )

    # 创建配置
    config = BacktestConfig(
        initial_capital=args.capital,
        commission_rate=args.commission,
        slippage_rate=args.slippage,
        t_plus=args.t_plus
    )

    # 加载数据
    logger.info("加载数据...")
    signals = pd.read_csv(args.signals)
    prices = pd.read_csv(args.prices)

    # 执行回测
    engine = BacktestEngine(config)
    logger.info("开始执行回测...")

    results = engine.run(
        signals=signals,
        prices=prices,
        start_date=args.start_date,
        end_date=args.end_date
    )

    # 保存结果
    engine.save_results(args.output)

    # 打印结果摘要
    print("\n" + "=" * 60)
    print("回测结果摘要")
    print("=" * 60)
    for key, value in results.items():
        if key != "config":
            print(f"{key:20}: {value}")

    return 0


if __name__ == "__main__":
    exit(main())