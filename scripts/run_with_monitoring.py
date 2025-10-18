#!/usr/bin/env python3
"""
策略运行与监控集成

将回测引擎与监控系统集成，实现实时监控
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from backtest.unified_backtest import UnifiedBacktest, UnifiedBacktestConfig
from monitoring.monitoring_system import (
    MonitorConfig,
    MonitoringSystem,
    MetricType,
    AlertLevel
)
from monitoring.dashboard import MonitoringDashboardApp
from reports.report_generator import ReportGenerator, ReportConfig

logger = logging.getLogger(__name__)


# ============================================================================
# 策略监控集成器
# ============================================================================

class StrategyMonitor:
    """策略监控集成器"""

    def __init__(
        self,
        backtest: UnifiedBacktest,
        monitor_config: Optional[MonitorConfig] = None
    ):
        """
        Args:
            backtest: 回测引擎实例
            monitor_config: 监控配置
        """
        self.backtest = backtest
        self.monitor_config = monitor_config or MonitorConfig()

        # 创建监控系统
        self.monitoring_system = MonitoringSystem(self.monitor_config)

        # 注册数据源
        self._register_data_sources()

        # 监控线程
        self.monitor_thread = None
        self.is_monitoring = False

        # 数据缓存
        self.portfolio_values = []
        self.daily_returns = []
        self.positions = pd.DataFrame()
        self.trades = pd.DataFrame()

    def _register_data_sources(self):
        """注册监控数据源"""
        # 注册各个指标的数据源
        self.monitoring_system.register_data_source(
            "drawdown",
            lambda: self._get_portfolio_values()
        )
        self.monitoring_system.register_data_source(
            "sharpe",
            lambda: self._get_portfolio_values()
        )
        self.monitoring_system.register_data_source(
            "volatility",
            lambda: self._get_portfolio_values()
        )
        self.monitoring_system.register_data_source(
            "var",
            lambda: self._get_portfolio_values()
        )
        self.monitoring_system.register_data_source(
            "exposure",
            lambda: self._get_exposure()
        )
        self.monitoring_system.register_data_source(
            "turnover",
            lambda: self._get_turnover()
        )

    def _get_portfolio_values(self) -> pd.Series:
        """获取组合净值序列"""
        if not self.portfolio_values:
            return pd.Series([self.backtest.config.initial_capital])
        return pd.Series(self.portfolio_values)

    def _get_exposure(self) -> float:
        """获取当前仓位暴露"""
        if self.positions.empty:
            return 0.0

        # 计算当前持仓市值
        total_value = self.portfolio_values[-1] if self.portfolio_values else self.backtest.config.initial_capital
        position_value = self.positions["value"].sum() if "value" in self.positions.columns else 0

        exposure = position_value / total_value if total_value > 0 else 0
        return exposure

    def _get_turnover(self) -> float:
        """获取换手率"""
        if self.trades.empty or not self.portfolio_values:
            return 0.0

        # 计算最近N天的换手率
        lookback_days = 20
        recent_trades = self.trades.tail(lookback_days)

        if recent_trades.empty:
            return 0.0

        # 换手率 = 交易金额 / 平均持仓市值
        trade_value = recent_trades["value"].sum() if "value" in recent_trades.columns else 0
        avg_portfolio = np.mean(self.portfolio_values[-lookback_days:]) if len(self.portfolio_values) > lookback_days else self.portfolio_values[-1]

        turnover = trade_value / avg_portfolio if avg_portfolio > 0 else 0
        return turnover

    def run_with_monitoring(
        self,
        signals: pd.DataFrame,
        start_dashboard: bool = False,
        dashboard_port: int = 5000
    ) -> Dict[str, Any]:
        """
        运行回测并启动监控

        Args:
            signals: 交易信号
            start_dashboard: 是否启动Web仪表板
            dashboard_port: 仪表板端口

        Returns:
            回测结果
        """
        # 启动监控系统
        self.monitoring_system.start()
        logger.info("监控系统已启动")

        # 启动Web仪表板
        if start_dashboard:
            dashboard_app = MonitoringDashboardApp(
                self.monitoring_system,
                port=dashboard_port
            )
            dashboard_thread = threading.Thread(
                target=dashboard_app.run,
                kwargs={"debug": False}
            )
            dashboard_thread.daemon = True
            dashboard_thread.start()
            logger.info(f"Web仪表板已启动: http://localhost:{dashboard_port}")

        # 启动监控线程
        self.is_monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitoring_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()

        try:
            # 运行回测
            logger.info("开始运行回测...")
            results = self._run_backtest_with_updates(signals)

            # 生成报告
            logger.info("生成回测报告...")
            self._generate_report(results)

            return results

        finally:
            # 停止监控
            self.is_monitoring = False
            if self.monitor_thread:
                self.monitor_thread.join(timeout=5)

            self.monitoring_system.stop()
            logger.info("监控系统已停止")

    def _run_backtest_with_updates(self, signals: pd.DataFrame) -> Dict[str, Any]:
        """运行回测并更新监控数据"""
        # 这里简化处理，实际应该在回测过程中实时更新
        results = self.backtest.run(signals)

        # 更新监控数据
        if "daily_values" in results:
            self.portfolio_values = results["daily_values"]["total_value"].tolist()

        if "trades" in results:
            self.trades = pd.DataFrame(results["trades"])

        if "positions" in results:
            self.positions = pd.DataFrame(results["positions"])

        return results

    def _monitoring_loop(self):
        """监控循环"""
        while self.is_monitoring:
            try:
                # 模拟实时数据更新（实际应该从回测引擎获取）
                self._update_monitoring_data()
                time.sleep(1)
            except Exception as e:
                logger.error(f"监控循环错误: {e}")

    def _update_monitoring_data(self):
        """更新监控数据（模拟）"""
        # 在实际应用中，这里应该从回测引擎获取实时数据
        # 这里只是模拟数据变化
        if self.portfolio_values:
            # 模拟净值变化
            last_value = self.portfolio_values[-1]
            change = np.random.randn() * 0.001  # 0.1%的随机变化
            new_value = last_value * (1 + change)
            self.portfolio_values.append(new_value)

            # 限制数据长度
            if len(self.portfolio_values) > 1000:
                self.portfolio_values = self.portfolio_values[-1000:]

    def _generate_report(self, results: Dict[str, Any]):
        """生成回测报告"""
        # 创建报告生成器
        report_config = ReportConfig(
            output_dir=Path("reports/backtest_results"),
            output_formats=["html", "md"]
        )
        generator = ReportGenerator(report_config)

        # 生成报告
        report_files = generator.generate(results)
        logger.info(f"报告已生成: {report_files}")


# ============================================================================
# 运行脚本
# ============================================================================

def main():
    """主函数"""
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    logger.info("=" * 60)
    logger.info("策略回测与监控系统")
    logger.info("=" * 60)

    # 配置回测
    backtest_config = UnifiedBacktestConfig(
        initial_capital=1_000_000,
        commission_rate=0.0003,
        slippage_rate=0.001,
        t_plus=1,
        engine="qlib"  # 或 "hikyuu"
    )

    # 创建回测引擎
    backtest = UnifiedBacktest(backtest_config)

    # 配置监控
    monitor_config = MonitorConfig(
        check_interval=5,  # 5秒检查一次
        thresholds={
            MetricType.DRAWDOWN: {"warning": -0.05, "critical": -0.10, "emergency": -0.15},
            MetricType.SHARPE: {"warning": 0.5, "critical": 0, "emergency": -0.5},
            MetricType.VOLATILITY: {"warning": 0.20, "critical": 0.30, "emergency": 0.40},
            MetricType.VAR: {"warning": -0.03, "critical": -0.05, "emergency": -0.10},
        },
        notification_channels=["log", "file"]
    )

    # 创建策略监控器
    monitor = StrategyMonitor(backtest, monitor_config)

    # 生成模拟信号（实际应该从策略生成）
    logger.info("生成交易信号...")
    dates = pd.date_range("2023-01-01", "2023-12-31", freq="D")
    signals = pd.DataFrame({
        "datetime": dates,
        "SH600000": np.random.choice([-1, 0, 1], size=len(dates), p=[0.3, 0.4, 0.3]),
        "SH600036": np.random.choice([-1, 0, 1], size=len(dates), p=[0.3, 0.4, 0.3]),
        "SZ000001": np.random.choice([-1, 0, 1], size=len(dates), p=[0.3, 0.4, 0.3]),
    })
    signals.set_index("datetime", inplace=True)

    # 运行回测并监控
    logger.info("开始运行回测与监控...")
    try:
        results = monitor.run_with_monitoring(
            signals,
            start_dashboard=True,  # 启动Web仪表板
            dashboard_port=5000
        )

        # 显示结果摘要
        logger.info("\n" + "=" * 60)
        logger.info("回测结果摘要")
        logger.info("=" * 60)

        if "metrics" in results:
            metrics = results["metrics"]
            logger.info(f"总收益率: {metrics.get('total_return', 0)*100:.2f}%")
            logger.info(f"年化收益率: {metrics.get('annual_return', 0)*100:.2f}%")
            logger.info(f"夏普比率: {metrics.get('sharpe_ratio', 0):.3f}")
            logger.info(f"最大回撤: {metrics.get('max_drawdown', 0)*100:.2f}%")

        # 获取监控系统状态
        monitor_status = monitor.monitoring_system.get_status()
        logger.info("\n监控系统状态:")
        logger.info(f"告警总数: {monitor_status['alerts']['total']}")

        # 保持程序运行以查看仪表板
        logger.info("\n仪表板运行中，按 Ctrl+C 退出...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("\n正在关闭系统...")

    except Exception as e:
        logger.error(f"运行失败: {e}", exc_info=True)
    finally:
        # 保存监控状态
        monitor.monitoring_system.save_state()
        logger.info("监控状态已保存")


if __name__ == "__main__":
    main()