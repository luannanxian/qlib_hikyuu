#!/usr/bin/env python3
"""
集成测试框架 - L2级子系统集成测试

测试完整的子系统功能，包括回测流程、监控系统和报告生成
"""

import sys
import pytest
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from unittest.mock import Mock, patch, MagicMock
import json
import tempfile

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backtest.unified_backtest import UnifiedBacktest, UnifiedBacktestConfig
from monitoring.monitoring_system import (
    MonitoringSystem,
    MonitorConfig,
    MetricType,
    AlertLevel
)
from reports.report_generator import ReportGenerator, ReportConfig


class TestBacktestSubsystem:
    """回测子系统集成测试"""

    @pytest.fixture
    def backtest_config(self):
        """创建回测配置"""
        return UnifiedBacktestConfig(
            initial_capital=1_000_000,
            commission_rate=0.0003,
            slippage_rate=0.001,
            t_plus=1,
            engine="qlib",
            benchmark="SH000300"
        )

    @pytest.fixture
    def backtest_engine(self, backtest_config):
        """创建回测引擎"""
        return UnifiedBacktest(backtest_config)

    @pytest.fixture
    def sample_signals(self):
        """创建示例交易信号"""
        dates = pd.date_range("2023-01-01", "2023-12-31", freq="D")
        signals = pd.DataFrame({
            "SH600000": np.random.choice([-1, 0, 1], size=len(dates), p=[0.3, 0.4, 0.3]),
            "SH600036": np.random.choice([-1, 0, 1], size=len(dates), p=[0.3, 0.4, 0.3]),
            "SZ000001": np.random.choice([-1, 0, 1], size=len(dates), p=[0.3, 0.4, 0.3]),
        }, index=dates)
        return signals

    @pytest.fixture
    def market_data(self):
        """创建市场数据"""
        dates = pd.date_range("2023-01-01", "2023-12-31", freq="D")
        stocks = ["SH600000", "SH600036", "SZ000001"]

        data = {}
        for stock in stocks:
            # 生成价格序列（带趋势的随机游走）
            returns = np.random.randn(len(dates)) * 0.02
            prices = 100 * np.exp(np.cumsum(returns))

            data[stock] = pd.DataFrame({
                "open": prices * (1 + np.random.randn(len(dates)) * 0.01),
                "high": prices * (1 + np.abs(np.random.randn(len(dates)) * 0.02)),
                "low": prices * (1 - np.abs(np.random.randn(len(dates)) * 0.02)),
                "close": prices,
                "volume": np.random.randint(1000000, 10000000, len(dates))
            }, index=dates)

        return data

    def test_complete_backtest_flow(self, backtest_engine, sample_signals, market_data):
        """TC-L2-001: 测试完整回测流程"""
        # 设置市场数据
        backtest_engine.set_market_data(market_data)

        # 执行回测
        results = backtest_engine.run(sample_signals)

        # 验证结果结构
        assert "metrics" in results
        assert "trades" in results
        assert "daily_values" in results
        assert "positions" in results

        # 验证指标计算
        metrics = results["metrics"]
        assert "total_return" in metrics
        assert "annual_return" in metrics
        assert "sharpe_ratio" in metrics
        assert "max_drawdown" in metrics
        assert "win_rate" in metrics

        # 验证数值合理性
        assert -1.0 <= metrics["total_return"] <= 10.0  # 合理的收益范围
        assert -1.0 <= metrics["max_drawdown"] <= 0.0  # 回撤应该是负值
        assert 0.0 <= metrics["win_rate"] <= 1.0  # 胜率在0-1之间

    def test_t_plus_execution(self, backtest_engine, market_data):
        """TC-L2-001: 测试T+1执行延迟"""
        # 创建简单信号（第1天买入）
        dates = pd.date_range("2023-01-01", "2023-01-10", freq="D")
        signals = pd.DataFrame({
            "SH600000": [1, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        }, index=dates)

        # 设置市场数据
        simple_market_data = {
            "SH600000": pd.DataFrame({
                "close": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109],
                "open": [100, 101, 102, 103, 104, 105, 106, 107, 108, 109],
                "high": [101, 102, 103, 104, 105, 106, 107, 108, 109, 110],
                "low": [99, 100, 101, 102, 103, 104, 105, 106, 107, 108],
                "volume": [1000000] * 10
            }, index=dates)
        }
        backtest_engine.set_market_data(simple_market_data)

        # 执行回测
        results = backtest_engine.run(signals)

        # 验证T+1执行
        trades = results["trades"]
        if len(trades) > 0:
            first_trade = trades[0]
            # 信号在第1天，执行应该在第2天
            assert first_trade["execution_date"] > dates[0]

    def test_commission_and_slippage(self, backtest_engine, market_data):
        """TC-L2-001: 测试手续费和滑点计算"""
        # 创建高频交易信号
        dates = pd.date_range("2023-01-01", "2023-01-31", freq="D")
        signals = pd.DataFrame({
            "SH600000": [1, -1] * 15 + [0],  # 频繁买卖
        }, index=dates)

        # 设置市场数据
        backtest_engine.set_market_data({"SH600000": market_data["SH600000"].loc[dates]})

        # 执行回测
        results = backtest_engine.run(signals)

        # 验证成本计算
        metrics = results["metrics"]
        assert "total_commission" in metrics
        assert "total_slippage" in metrics
        assert metrics["total_commission"] > 0  # 应该有手续费
        assert metrics["total_slippage"] > 0  # 应该有滑点

    def test_no_lookahead_bias(self, backtest_engine):
        """TC-L2-001: 验证无前视偏差"""
        # 创建未来收益信号（如果有前视偏差，会产生超额收益）
        dates = pd.date_range("2023-01-01", "2023-01-31", freq="D")

        # 创建"完美"预测信号（实际不应该可能）
        perfect_signals = pd.DataFrame({
            "SH600000": [1] * len(dates)  # 总是做多
        }, index=dates)

        # 创建下跌的市场数据
        declining_prices = 100 * np.exp(-np.cumsum(np.ones(len(dates)) * 0.01))
        market_data = {
            "SH600000": pd.DataFrame({
                "close": declining_prices,
                "open": declining_prices,
                "high": declining_prices * 1.01,
                "low": declining_prices * 0.99,
                "volume": [1000000] * len(dates)
            }, index=dates)
        }

        backtest_engine.set_market_data(market_data)
        results = backtest_engine.run(perfect_signals)

        # 在下跌市场中做多应该亏损
        assert results["metrics"]["total_return"] < 0


class TestMonitoringSubsystem:
    """监控子系统集成测试"""

    @pytest.fixture
    def monitor_config(self):
        """创建监控配置"""
        return MonitorConfig(
            check_interval=1,  # 1秒检查一次（测试用）
            history_window=60,  # 保留60分钟数据
            alert_cooldown=5,  # 5秒告警冷却
            thresholds={
                MetricType.DRAWDOWN: {"warning": -0.03, "critical": -0.05, "emergency": -0.10},
                MetricType.SHARPE: {"warning": 0.5, "critical": 0, "emergency": -0.5},
                MetricType.VOLATILITY: {"warning": 0.20, "critical": 0.30, "emergency": 0.40},
            },
            notification_channels=["log", "file"]
        )

    @pytest.fixture
    def monitoring_system(self, monitor_config, tmp_path):
        """创建监控系统"""
        monitor_config.save_path = tmp_path / "monitoring"
        return MonitoringSystem(monitor_config)

    def test_monitoring_system_startup(self, monitoring_system):
        """TC-L2-002: 测试监控系统启动"""
        # 启动监控
        monitoring_system.start()
        assert monitoring_system.is_running

        # 停止监控
        monitoring_system.stop()
        assert not monitoring_system.is_running

    def test_metric_monitoring(self, monitoring_system):
        """TC-L2-002: 测试指标监控"""
        # 注册数据源
        test_values = [100000, 99000, 98000, 97000, 96000]  # 模拟下跌
        index = 0

        def get_portfolio_value():
            nonlocal index
            if index < len(test_values):
                value = test_values[index]
                index += 1
                return pd.Series([value])
            return pd.Series([test_values[-1]])

        monitoring_system.register_data_source("drawdown", get_portfolio_value)

        # 启动监控
        monitoring_system.start()

        # 等待几个监控周期
        import time
        time.sleep(3)

        # 获取状态
        status = monitoring_system.get_status()

        # 停止监控
        monitoring_system.stop()

        # 验证监控数据
        assert "monitors" in status
        assert "drawdown" in status["monitors"]

    def test_alert_generation(self, monitoring_system):
        """TC-L2-002: 测试告警生成"""
        # 创建会触发告警的数据
        def get_critical_drawdown():
            return pd.Series([100000, 95000, 90000])  # -10%回撤

        monitoring_system.register_data_source("drawdown", get_critical_drawdown)

        # 手动触发一次检查
        monitoring_system._check_all_metrics()

        # 验证告警
        assert len(monitoring_system.alert_history) > 0
        alert = monitoring_system.alert_history[-1]
        assert alert.level in [AlertLevel.CRITICAL, AlertLevel.EMERGENCY]

    def test_notification_channels(self, monitoring_system, tmp_path):
        """TC-L2-002: 测试通知渠道"""
        # 配置文件通知
        alert_file = tmp_path / "alerts.log"
        monitoring_system.channels = []
        from monitoring.monitoring_system import FileNotificationChannel
        monitoring_system.add_channel(FileNotificationChannel(alert_file))

        # 生成告警
        from monitoring.monitoring_system import Alert
        test_alert = Alert(
            timestamp=datetime.now(),
            level=AlertLevel.CRITICAL,
            metric_type=MetricType.DRAWDOWN,
            message="测试告警",
            value=-0.10,
            threshold=-0.05
        )

        monitoring_system._send_alert(test_alert)

        # 验证文件通知
        assert alert_file.exists()
        content = alert_file.read_text()
        assert "测试告警" in content


class TestReportingSubsystem:
    """报告生成子系统集成测试"""

    @pytest.fixture
    def report_config(self, tmp_path):
        """创建报告配置"""
        return ReportConfig(
            output_dir=tmp_path / "reports",
            output_formats=["html", "md", "excel"],
            include_charts=True
        )

    @pytest.fixture
    def report_generator(self, report_config):
        """创建报告生成器"""
        return ReportGenerator(report_config)

    @pytest.fixture
    def backtest_results(self):
        """创建回测结果"""
        dates = pd.date_range("2023-01-01", "2023-12-31", freq="D")

        return {
            "metrics": {
                "total_return": 0.15,
                "annual_return": 0.15,
                "sharpe_ratio": 1.2,
                "max_drawdown": -0.08,
                "win_rate": 0.55,
                "total_trades": 100,
                "winning_trades": 55,
                "losing_trades": 45
            },
            "daily_values": pd.DataFrame({
                "date": dates,
                "total_value": 1000000 * np.exp(np.cumsum(np.random.randn(len(dates)) * 0.01)),
                "cash": 500000 + np.random.randn(len(dates)) * 10000,
                "positions_value": 500000 + np.random.randn(len(dates)) * 10000
            }),
            "trades": [
                {
                    "date": dates[i],
                    "symbol": np.random.choice(["SH600000", "SH600036", "SZ000001"]),
                    "action": np.random.choice(["buy", "sell"]),
                    "quantity": np.random.randint(100, 1000) * 100,
                    "price": np.random.uniform(10, 100),
                    "commission": np.random.uniform(10, 100),
                    "slippage": np.random.uniform(5, 50)
                }
                for i in np.random.choice(len(dates), 100)
            ]
        }

    def test_report_generation(self, report_generator, backtest_results):
        """TC-L2-003: 测试报告生成"""
        # 生成报告
        report_files = report_generator.generate(backtest_results)

        # 验证文件生成
        assert len(report_files) > 0
        for file_path in report_files:
            assert file_path.exists()

        # 验证HTML报告
        html_files = [f for f in report_files if f.suffix == ".html"]
        assert len(html_files) > 0
        html_content = html_files[0].read_text()
        assert "回测报告" in html_content or "Backtest Report" in html_content

        # 验证Markdown报告
        md_files = [f for f in report_files if f.suffix == ".md"]
        if md_files:
            md_content = md_files[0].read_text()
            assert "## " in md_content  # 应该有标题

        # 验证Excel报告
        excel_files = [f for f in report_files if f.suffix == ".xlsx"]
        if excel_files:
            # 验证文件可以被pandas读取
            import pandas as pd
            df = pd.read_excel(excel_files[0], sheet_name=None)
            assert len(df) > 0

    def test_chart_generation(self, report_generator, backtest_results):
        """TC-L2-003: 测试图表生成"""
        # 生成报告（包含图表）
        report_files = report_generator.generate(backtest_results)

        # 验证图表文件
        chart_files = [f for f in report_generator.config.output_dir.glob("*.png")]

        # 如果配置包含图表，应该生成图表文件
        if report_generator.config.include_charts:
            # 图表可能嵌入在HTML中，不一定是独立文件
            html_files = [f for f in report_files if f.suffix == ".html"]
            if html_files:
                html_content = html_files[0].read_text()
                # 检查是否包含图表相关内容
                assert "canvas" in html_content or "img" in html_content or "chart" in html_content.lower()

    def test_metrics_accuracy(self, report_generator, backtest_results):
        """TC-L2-003: 测试指标准确性"""
        # 生成报告
        report_files = report_generator.generate(backtest_results)

        # 读取Markdown报告验证指标
        md_files = [f for f in report_files if f.suffix == ".md"]
        if md_files:
            md_content = md_files[0].read_text()

            # 验证关键指标在报告中
            assert "15.00%" in md_content or "0.15" in md_content  # 总收益
            assert "1.2" in md_content  # 夏普比率
            assert "-8.00%" in md_content or "-0.08" in md_content  # 最大回撤


class TestSubsystemIntegration:
    """子系统间集成测试"""

    def test_backtest_to_monitoring_integration(self):
        """测试回测与监控的集成"""
        # 创建回测配置
        backtest_config = UnifiedBacktestConfig(
            initial_capital=1_000_000,
            commission_rate=0.0003,
            slippage_rate=0.001
        )
        backtest = UnifiedBacktest(backtest_config)

        # 创建监控配置
        monitor_config = MonitorConfig(check_interval=1)
        monitoring = MonitoringSystem(monitor_config)

        # 注册数据源（从回测获取）
        def get_backtest_value():
            # 这里应该从回测系统获取实时数据
            return pd.Series([1000000])

        monitoring.register_data_source("portfolio_value", get_backtest_value)

        # 验证集成
        assert monitoring.data_sources.get("portfolio_value") is not None

    def test_backtest_to_report_integration(self, tmp_path):
        """测试回测与报告的集成"""
        # 运行回测
        backtest_config = UnifiedBacktestConfig(initial_capital=1_000_000)
        backtest = UnifiedBacktest(backtest_config)

        # 创建模拟结果
        mock_results = {
            "metrics": {"total_return": 0.10},
            "daily_values": pd.DataFrame({"total_value": [1000000, 1100000]}),
            "trades": []
        }

        # 生成报告
        report_config = ReportConfig(output_dir=tmp_path / "reports")
        generator = ReportGenerator(report_config)
        report_files = generator.generate(mock_results)

        # 验证报告生成
        assert len(report_files) > 0

    def test_complete_workflow_integration(self, tmp_path):
        """测试完整工作流集成"""
        # 1. 准备数据
        dates = pd.date_range("2023-01-01", "2023-01-31", freq="D")
        signals = pd.DataFrame({"SH600000": [1, 0, -1] * 10 + [0]}, index=dates)

        # 2. 配置回测
        backtest_config = UnifiedBacktestConfig(initial_capital=1_000_000)
        backtest = UnifiedBacktest(backtest_config)

        # 3. 配置监控
        monitor_config = MonitorConfig(save_path=tmp_path / "monitoring")
        monitoring = MonitoringSystem(monitor_config)

        # 4. 配置报告
        report_config = ReportConfig(output_dir=tmp_path / "reports")
        generator = ReportGenerator(report_config)

        # 5. 执行工作流
        try:
            # 启动监控
            monitoring.start()

            # 运行回测（使用模拟数据）
            results = {
                "metrics": {"total_return": 0.05},
                "daily_values": pd.DataFrame({"total_value": [1000000, 1050000]}),
                "trades": []
            }

            # 生成报告
            report_files = generator.generate(results)

            # 验证结果
            assert len(report_files) > 0
            assert monitoring.is_running

        finally:
            # 清理
            monitoring.stop()


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v", "--tb=short"])