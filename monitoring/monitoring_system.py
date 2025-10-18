#!/usr/bin/env python3
"""
监控告警系统

实时监控策略运行状态和风险指标，提供多渠道告警通知
"""

from __future__ import annotations

import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Union

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ============================================================================
# 监控配置
# ============================================================================

class AlertLevel(Enum):
    """告警级别"""
    INFO = "info"          # 信息提示
    WARNING = "warning"    # 警告
    CRITICAL = "critical"  # 严重
    EMERGENCY = "emergency"  # 紧急


class MetricType(Enum):
    """指标类型"""
    # 性能指标
    RETURN = "return"
    SHARPE = "sharpe"
    VOLATILITY = "volatility"

    # 风险指标
    DRAWDOWN = "drawdown"
    VAR = "var"
    EXPOSURE = "exposure"

    # 执行指标
    SLIPPAGE = "slippage"
    TURNOVER = "turnover"
    COMMISSION = "commission"

    # 系统指标
    MEMORY = "memory"
    CPU = "cpu"
    LATENCY = "latency"


@dataclass
class MonitorConfig:
    """监控配置"""
    # 监控频率
    check_interval: int = 60  # 秒

    # 数据保留
    history_window: int = 1440  # 分钟 (24小时)
    max_data_points: int = 10000

    # 告警配置
    alert_cooldown: int = 300  # 同一告警冷却时间(秒)
    max_alerts_per_hour: int = 10

    # 阈值配置
    thresholds: Dict[MetricType, Dict[str, float]] = field(default_factory=lambda: {
        MetricType.DRAWDOWN: {"warning": -0.05, "critical": -0.10, "emergency": -0.20},
        MetricType.SHARPE: {"warning": 0.5, "critical": 0, "emergency": -1.0},
        MetricType.VOLATILITY: {"warning": 0.20, "critical": 0.30, "emergency": 0.50},
        MetricType.VAR: {"warning": -0.05, "critical": -0.10, "emergency": -0.15},
        MetricType.EXPOSURE: {"warning": 0.80, "critical": 0.95, "emergency": 1.0},
        MetricType.SLIPPAGE: {"warning": 0.002, "critical": 0.005, "emergency": 0.01},
        MetricType.TURNOVER: {"warning": 0.5, "critical": 1.0, "emergency": 2.0},
        MetricType.MEMORY: {"warning": 0.70, "critical": 0.85, "emergency": 0.95},
        MetricType.CPU: {"warning": 0.70, "critical": 0.85, "emergency": 0.95},
        MetricType.LATENCY: {"warning": 1000, "critical": 5000, "emergency": 10000},  # ms
    })

    # 通知渠道
    notification_channels: List[str] = field(default_factory=lambda: ["log", "file"])

    # 持久化
    save_path: Path = Path("monitoring_data")
    save_interval: int = 300  # 秒


# ============================================================================
# 指标监控器
# ============================================================================

class MetricMonitor(ABC):
    """指标监控器基类"""

    def __init__(self, metric_type: MetricType, config: MonitorConfig):
        self.metric_type = metric_type
        self.config = config
        self.history = deque(maxlen=config.max_data_points)
        self.last_value = None
        self.last_update = None

    @abstractmethod
    def calculate(self, data: Any) -> float:
        """计算指标值"""
        pass

    def update(self, data: Any) -> Optional[float]:
        """更新指标"""
        try:
            value = self.calculate(data)
            timestamp = datetime.now()

            self.history.append({
                "timestamp": timestamp,
                "value": value
            })

            self.last_value = value
            self.last_update = timestamp

            return value
        except Exception as e:
            logger.error(f"更新指标 {self.metric_type} 失败: {e}")
            return None

    def check_threshold(self) -> Optional[AlertLevel]:
        """检查阈值"""
        if self.last_value is None:
            return None

        thresholds = self.config.thresholds.get(self.metric_type, {})

        # 对于负向指标（如回撤），值越小越严重
        if self.metric_type in [MetricType.DRAWDOWN, MetricType.VAR]:
            if self.last_value <= thresholds.get("emergency", float("-inf")):
                return AlertLevel.EMERGENCY
            elif self.last_value <= thresholds.get("critical", float("-inf")):
                return AlertLevel.CRITICAL
            elif self.last_value <= thresholds.get("warning", float("-inf")):
                return AlertLevel.WARNING
        # 对于正向指标，值越大越严重（如波动率、延迟）
        else:
            if self.last_value >= thresholds.get("emergency", float("inf")):
                return AlertLevel.EMERGENCY
            elif self.last_value >= thresholds.get("critical", float("inf")):
                return AlertLevel.CRITICAL
            elif self.last_value >= thresholds.get("warning", float("inf")):
                return AlertLevel.WARNING

        return None

    def get_statistics(self) -> Dict[str, float]:
        """获取统计信息"""
        if not self.history:
            return {}

        values = [h["value"] for h in self.history]
        return {
            "current": self.last_value,
            "mean": np.mean(values),
            "std": np.std(values),
            "min": np.min(values),
            "max": np.max(values),
            "count": len(values)
        }


class DrawdownMonitor(MetricMonitor):
    """回撤监控器"""

    def __init__(self, config: MonitorConfig):
        super().__init__(MetricType.DRAWDOWN, config)
        self.peak_value = None

    def calculate(self, data: pd.Series) -> float:
        """计算当前回撤"""
        if data.empty:
            return 0.0

        current_value = data.iloc[-1]

        # 更新峰值
        if self.peak_value is None or current_value > self.peak_value:
            self.peak_value = current_value

        # 计算回撤
        if self.peak_value > 0:
            drawdown = (current_value - self.peak_value) / self.peak_value
        else:
            drawdown = 0.0

        return drawdown


class SharpeMonitor(MetricMonitor):
    """夏普比率监控器"""

    def __init__(self, config: MonitorConfig, window: int = 252):
        super().__init__(MetricType.SHARPE, config)
        self.window = window  # 计算窗口（天）

    def calculate(self, data: pd.Series) -> float:
        """计算滚动夏普比率"""
        if len(data) < self.window:
            return 0.0

        # 使用最近window天的数据
        recent_returns = data.pct_change().tail(self.window).dropna()

        if recent_returns.empty:
            return 0.0

        # 年化夏普比率
        mean_return = recent_returns.mean()
        std_return = recent_returns.std()

        if std_return > 0:
            sharpe = np.sqrt(252) * mean_return / std_return
        else:
            sharpe = 0.0

        return sharpe


class VolatilityMonitor(MetricMonitor):
    """波动率监控器"""

    def __init__(self, config: MonitorConfig, window: int = 20):
        super().__init__(MetricType.VOLATILITY, config)
        self.window = window

    def calculate(self, data: pd.Series) -> float:
        """计算滚动波动率"""
        if len(data) < self.window:
            return 0.0

        # 使用最近window天的数据
        recent_returns = data.pct_change().tail(self.window).dropna()

        if recent_returns.empty:
            return 0.0

        # 年化波动率
        volatility = recent_returns.std() * np.sqrt(252)

        return volatility


class VaRMonitor(MetricMonitor):
    """VaR监控器"""

    def __init__(self, config: MonitorConfig, confidence: float = 0.95, window: int = 100):
        super().__init__(MetricType.VAR, config)
        self.confidence = confidence
        self.window = window

    def calculate(self, data: pd.Series) -> float:
        """计算VaR"""
        if len(data) < self.window:
            return 0.0

        # 使用最近window天的收益率
        recent_returns = data.pct_change().tail(self.window).dropna()

        if recent_returns.empty:
            return 0.0

        # 计算VaR（负值表示损失）
        var = np.percentile(recent_returns, (1 - self.confidence) * 100)

        return var


# ============================================================================
# 告警通知
# ============================================================================

@dataclass
class Alert:
    """告警信息"""
    timestamp: datetime
    level: AlertLevel
    metric_type: MetricType
    message: str
    value: float
    threshold: float
    context: Optional[Dict[str, Any]] = None


class NotificationChannel(ABC):
    """通知渠道基类"""

    @abstractmethod
    def send(self, alert: Alert) -> bool:
        """发送告警"""
        pass


class LogNotificationChannel(NotificationChannel):
    """日志通知渠道"""

    def send(self, alert: Alert) -> bool:
        """通过日志发送告警"""
        log_level = {
            AlertLevel.INFO: logging.INFO,
            AlertLevel.WARNING: logging.WARNING,
            AlertLevel.CRITICAL: logging.ERROR,
            AlertLevel.EMERGENCY: logging.CRITICAL
        }[alert.level]

        logger.log(
            log_level,
            f"[{alert.level.value.upper()}] {alert.metric_type.value}: "
            f"{alert.message} (值: {alert.value:.4f}, 阈值: {alert.threshold:.4f})"
        )

        return True


class FileNotificationChannel(NotificationChannel):
    """文件通知渠道"""

    def __init__(self, file_path: Path = Path("alerts.log")):
        self.file_path = file_path
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def send(self, alert: Alert) -> bool:
        """将告警写入文件"""
        try:
            with open(self.file_path, "a", encoding="utf-8") as f:
                alert_dict = {
                    "timestamp": alert.timestamp.isoformat(),
                    "level": alert.level.value,
                    "metric": alert.metric_type.value,
                    "message": alert.message,
                    "value": alert.value,
                    "threshold": alert.threshold,
                    "context": alert.context
                }
                f.write(json.dumps(alert_dict, ensure_ascii=False) + "\n")
            return True
        except Exception as e:
            logger.error(f"写入告警文件失败: {e}")
            return False


class EmailNotificationChannel(NotificationChannel):
    """邮件通知渠道（示例）"""

    def __init__(self, smtp_config: Dict[str, Any]):
        self.smtp_config = smtp_config

    def send(self, alert: Alert) -> bool:
        """通过邮件发送告警"""
        # 这里只是示例，实际需要配置SMTP
        logger.info(f"邮件告警（未实现）: {alert.message}")
        return True


class WebhookNotificationChannel(NotificationChannel):
    """Webhook通知渠道（示例）"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, alert: Alert) -> bool:
        """通过Webhook发送告警"""
        # 这里只是示例，实际需要发送HTTP请求
        logger.info(f"Webhook告警（未实现）: {alert.message}")
        return True


# ============================================================================
# 监控系统
# ============================================================================

class MonitoringSystem:
    """监控系统"""

    def __init__(self, config: Optional[MonitorConfig] = None):
        self.config = config or MonitorConfig()

        # 监控器
        self.monitors: Dict[MetricType, MetricMonitor] = {}
        self._init_monitors()

        # 通知渠道
        self.channels: List[NotificationChannel] = []
        self._init_channels()

        # 告警管理
        self.alert_history: deque = deque(maxlen=1000)
        self.alert_cooldowns: Dict[str, datetime] = {}
        self.alert_counts: Dict[str, int] = {}

        # 监控线程
        self.monitoring_thread = None
        self.is_running = False

        # 数据源
        self.data_sources: Dict[str, Callable] = {}

    def _init_monitors(self):
        """初始化监控器"""
        self.monitors[MetricType.DRAWDOWN] = DrawdownMonitor(self.config)
        self.monitors[MetricType.SHARPE] = SharpeMonitor(self.config)
        self.monitors[MetricType.VOLATILITY] = VolatilityMonitor(self.config)
        self.monitors[MetricType.VAR] = VaRMonitor(self.config)

    def _init_channels(self):
        """初始化通知渠道"""
        for channel_name in self.config.notification_channels:
            if channel_name == "log":
                self.channels.append(LogNotificationChannel())
            elif channel_name == "file":
                self.channels.append(FileNotificationChannel())
            elif channel_name == "email":
                # 需要配置
                pass
            elif channel_name == "webhook":
                # 需要配置
                pass

    def register_data_source(self, name: str, source: Callable):
        """注册数据源"""
        self.data_sources[name] = source

    def add_monitor(self, monitor: MetricMonitor):
        """添加监控器"""
        self.monitors[monitor.metric_type] = monitor

    def add_channel(self, channel: NotificationChannel):
        """添加通知渠道"""
        self.channels.append(channel)

    def start(self):
        """启动监控"""
        if self.is_running:
            logger.warning("监控系统已经在运行")
            return

        self.is_running = True
        self.monitoring_thread = threading.Thread(target=self._monitoring_loop)
        self.monitoring_thread.daemon = True
        self.monitoring_thread.start()

        logger.info("监控系统已启动")

    def stop(self):
        """停止监控"""
        self.is_running = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)

        logger.info("监控系统已停止")

    def _monitoring_loop(self):
        """监控循环"""
        while self.is_running:
            try:
                self._check_all_metrics()
                time.sleep(self.config.check_interval)
            except Exception as e:
                logger.error(f"监控循环错误: {e}")

    def _check_all_metrics(self):
        """检查所有指标"""
        for metric_type, monitor in self.monitors.items():
            # 获取数据
            data_source = self.data_sources.get(metric_type.value)
            if not data_source:
                continue

            try:
                data = data_source()

                # 更新指标
                value = monitor.update(data)
                if value is None:
                    continue

                # 检查阈值
                alert_level = monitor.check_threshold()
                if alert_level:
                    self._handle_alert(monitor, alert_level)

            except Exception as e:
                logger.error(f"检查指标 {metric_type} 失败: {e}")

    def _handle_alert(self, monitor: MetricMonitor, level: AlertLevel):
        """处理告警"""
        # 生成告警键
        alert_key = f"{monitor.metric_type.value}_{level.value}"

        # 检查冷却时间
        last_alert_time = self.alert_cooldowns.get(alert_key)
        if last_alert_time:
            if datetime.now() - last_alert_time < timedelta(seconds=self.config.alert_cooldown):
                return

        # 检查告警频率
        current_hour = datetime.now().strftime("%Y%m%d%H")
        hour_key = f"{current_hour}_{alert_key}"
        if self.alert_counts.get(hour_key, 0) >= self.config.max_alerts_per_hour:
            return

        # 创建告警
        thresholds = self.config.thresholds.get(monitor.metric_type, {})
        alert = Alert(
            timestamp=datetime.now(),
            level=level,
            metric_type=monitor.metric_type,
            message=f"{monitor.metric_type.value} 触发 {level.value} 级别告警",
            value=monitor.last_value,
            threshold=thresholds.get(level.value.lower(), 0),
            context=monitor.get_statistics()
        )

        # 发送告警
        self._send_alert(alert)

        # 更新冷却和计数
        self.alert_cooldowns[alert_key] = datetime.now()
        self.alert_counts[hour_key] = self.alert_counts.get(hour_key, 0) + 1

        # 保存告警历史
        self.alert_history.append(alert)

    def _send_alert(self, alert: Alert):
        """发送告警"""
        for channel in self.channels:
            try:
                channel.send(alert)
            except Exception as e:
                logger.error(f"发送告警失败 ({channel.__class__.__name__}): {e}")

    def get_status(self) -> Dict[str, Any]:
        """获取监控状态"""
        status = {
            "is_running": self.is_running,
            "monitors": {},
            "alerts": {
                "total": len(self.alert_history),
                "recent": []
            }
        }

        # 监控器状态
        for metric_type, monitor in self.monitors.items():
            status["monitors"][metric_type.value] = {
                "last_value": monitor.last_value,
                "last_update": monitor.last_update.isoformat() if monitor.last_update else None,
                "statistics": monitor.get_statistics()
            }

        # 最近告警
        for alert in list(self.alert_history)[-10:]:
            status["alerts"]["recent"].append({
                "timestamp": alert.timestamp.isoformat(),
                "level": alert.level.value,
                "metric": alert.metric_type.value,
                "message": alert.message,
                "value": alert.value
            })

        return status

    def save_state(self):
        """保存监控状态"""
        state_file = self.config.save_path / "monitoring_state.json"
        state_file.parent.mkdir(parents=True, exist_ok=True)

        state = {
            "timestamp": datetime.now().isoformat(),
            "status": self.get_status(),
            "config": {
                "check_interval": self.config.check_interval,
                "history_window": self.config.history_window,
                "thresholds": {
                    k.value: v for k, v in self.config.thresholds.items()
                }
            }
        }

        with open(state_file, "w") as f:
            json.dump(state, f, indent=2, default=str)

        logger.info(f"监控状态已保存到 {state_file}")


# ============================================================================
# 监控仪表板
# ============================================================================

class MonitoringDashboard:
    """监控仪表板（文本版）"""

    def __init__(self, monitoring_system: MonitoringSystem):
        self.monitoring_system = monitoring_system

    def display(self):
        """显示仪表板"""
        status = self.monitoring_system.get_status()

        print("\n" + "=" * 60)
        print("策略监控仪表板")
        print("=" * 60)

        # 系统状态
        print(f"\n📊 系统状态: {'运行中' if status['is_running'] else '已停止'}")
        print(f"⏰ 更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # 指标状态
        print("\n📈 指标监控:")
        print("-" * 40)

        for metric_name, metric_data in status["monitors"].items():
            value = metric_data.get("last_value")
            if value is not None:
                # 根据指标类型格式化显示
                if metric_name in ["drawdown", "var"]:
                    display_value = f"{value*100:.2f}%"
                    emoji = "🔴" if value < -0.05 else "🟡" if value < -0.02 else "🟢"
                elif metric_name in ["sharpe"]:
                    display_value = f"{value:.3f}"
                    emoji = "🟢" if value > 1 else "🟡" if value > 0 else "🔴"
                elif metric_name in ["volatility"]:
                    display_value = f"{value*100:.2f}%"
                    emoji = "🔴" if value > 0.25 else "🟡" if value > 0.15 else "🟢"
                else:
                    display_value = f"{value:.4f}"
                    emoji = "⚪"

                print(f"{emoji} {metric_name:12s}: {display_value:>10s}")

        # 最近告警
        print("\n🚨 最近告警:")
        print("-" * 40)

        recent_alerts = status["alerts"]["recent"]
        if recent_alerts:
            for alert in recent_alerts[-5:]:
                timestamp = datetime.fromisoformat(alert["timestamp"])
                level_emoji = {
                    "info": "ℹ️",
                    "warning": "⚠️",
                    "critical": "🔴",
                    "emergency": "🆘"
                }[alert["level"]]

                print(f"{level_emoji} [{timestamp.strftime('%H:%M:%S')}] "
                      f"{alert['metric']}: {alert['message']}")
        else:
            print("暂无告警")

        print("\n" + "=" * 60)


# ============================================================================
# 使用示例
# ============================================================================

if __name__ == "__main__":
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # 创建监控系统
    config = MonitorConfig(
        check_interval=5,  # 5秒检查一次（演示用）
        notification_channels=["log", "file"]
    )

    monitoring = MonitoringSystem(config)

    # 注册数据源（模拟）
    np.random.seed(42)
    base_value = 1000000
    values = []

    def get_portfolio_value():
        """模拟获取组合净值"""
        # 模拟随机游走
        if values:
            last_value = values[-1]
        else:
            last_value = base_value

        # 随机变化
        change = np.random.randn() * 0.01
        new_value = last_value * (1 + change)
        values.append(new_value)

        # 偶尔产生大的波动（测试告警）
        if np.random.random() < 0.1:
            new_value *= 0.95  # 5%的下跌

        return pd.Series(values[-100:])  # 返回最近100个值

    # 注册数据源
    monitoring.register_data_source("drawdown", get_portfolio_value)
    monitoring.register_data_source("sharpe", get_portfolio_value)
    monitoring.register_data_source("volatility", get_portfolio_value)
    monitoring.register_data_source("var", get_portfolio_value)

    # 创建仪表板
    dashboard = MonitoringDashboard(monitoring)

    # 启动监控
    monitoring.start()

    # 运行一段时间
    try:
        for i in range(20):
            time.sleep(3)
            dashboard.display()

            # 定期保存状态
            if i % 5 == 0:
                monitoring.save_state()

    except KeyboardInterrupt:
        print("\n正在停止监控...")
    finally:
        monitoring.stop()
        monitoring.save_state()
        print("监控已停止")