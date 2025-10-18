#!/usr/bin/env python3
"""
实时监控仪表板

提供Web界面的实时监控仪表板，展示策略运行状态和指标
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from flask import Flask, jsonify, render_template_string
from flask_cors import CORS

from monitoring_system import MonitoringSystem, MonitorConfig

logger = logging.getLogger(__name__)


# ============================================================================
# HTML模板
# ============================================================================

DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>策略监控仪表板</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
        }

        .header {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            padding: 20px 30px;
            margin-bottom: 20px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.1);
        }

        .header h1 {
            color: #2c3e50;
            font-size: 28px;
            margin-bottom: 10px;
        }

        .status-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .status-indicator {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .status-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            animation: pulse 2s infinite;
        }

        .status-dot.running {
            background: #27ae60;
        }

        .status-dot.stopped {
            background: #e74c3c;
        }

        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }

        .dashboard {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }

        .metric-card {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.1);
            transition: transform 0.3s ease;
        }

        .metric-card:hover {
            transform: translateY(-5px);
        }

        .metric-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }

        .metric-title {
            font-size: 16px;
            color: #7f8c8d;
            font-weight: 600;
        }

        .metric-icon {
            font-size: 24px;
        }

        .metric-value {
            font-size: 36px;
            font-weight: bold;
            margin-bottom: 10px;
        }

        .metric-value.positive {
            color: #27ae60;
        }

        .metric-value.negative {
            color: #e74c3c;
        }

        .metric-value.neutral {
            color: #3498db;
        }

        .metric-change {
            font-size: 14px;
            color: #95a5a6;
        }

        .metric-chart {
            height: 80px;
            margin-top: 15px;
            position: relative;
        }

        .alerts-section {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.1);
        }

        .alerts-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }

        .alerts-title {
            font-size: 18px;
            color: #2c3e50;
            font-weight: 600;
        }

        .alert-item {
            background: #f8f9fa;
            border-left: 4px solid #3498db;
            padding: 12px;
            margin-bottom: 10px;
            border-radius: 5px;
            display: flex;
            align-items: center;
            gap: 15px;
        }

        .alert-item.warning {
            border-left-color: #f39c12;
            background: #fff9e6;
        }

        .alert-item.critical {
            border-left-color: #e74c3c;
            background: #ffe6e6;
        }

        .alert-item.emergency {
            border-left-color: #c0392b;
            background: #ffcccc;
            animation: blink 1s infinite;
        }

        @keyframes blink {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.7; }
        }

        .alert-icon {
            font-size: 20px;
        }

        .alert-content {
            flex: 1;
        }

        .alert-message {
            font-size: 14px;
            color: #2c3e50;
            margin-bottom: 4px;
        }

        .alert-time {
            font-size: 12px;
            color: #7f8c8d;
        }

        .chart-container {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 15px;
            padding: 20px;
            margin-top: 20px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.1);
        }

        .sparkline {
            stroke: #3498db;
            fill: none;
            stroke-width: 2;
        }

        .sparkline-area {
            fill: #3498db;
            opacity: 0.1;
        }

        .no-data {
            text-align: center;
            color: #95a5a6;
            padding: 40px;
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- 头部 -->
        <div class="header">
            <h1>📊 策略监控仪表板</h1>
            <div class="status-bar">
                <div class="status-indicator">
                    <span class="status-dot" id="status-dot"></span>
                    <span id="status-text">连接中...</span>
                </div>
                <div>
                    <span id="update-time">--:--:--</span>
                </div>
            </div>
        </div>

        <!-- 指标仪表板 -->
        <div class="dashboard" id="metrics-dashboard">
            <!-- 动态生成指标卡片 -->
        </div>

        <!-- 告警部分 -->
        <div class="alerts-section">
            <div class="alerts-header">
                <h2 class="alerts-title">🚨 实时告警</h2>
                <span id="alert-count">0 个告警</span>
            </div>
            <div id="alerts-list">
                <div class="no-data">暂无告警</div>
            </div>
        </div>

        <!-- 图表部分 -->
        <div class="chart-container">
            <h2 style="margin-bottom: 20px;">📈 性能趋势</h2>
            <canvas id="trend-chart" width="400" height="200"></canvas>
        </div>
    </div>

    <script>
        // 配置
        const API_BASE = '/api';
        const UPDATE_INTERVAL = 5000;  // 5秒更新一次

        // 状态
        let isRunning = false;
        let metricsData = {};
        let alertsData = [];

        // 指标配置
        const metricConfigs = {
            drawdown: {
                title: '最大回撤',
                icon: '📉',
                format: (v) => (v * 100).toFixed(2) + '%',
                colorClass: (v) => v < -0.05 ? 'negative' : v < -0.02 ? 'neutral' : 'positive'
            },
            sharpe: {
                title: '夏普比率',
                icon: '📊',
                format: (v) => v.toFixed(3),
                colorClass: (v) => v > 1 ? 'positive' : v > 0 ? 'neutral' : 'negative'
            },
            volatility: {
                title: '波动率',
                icon: '📈',
                format: (v) => (v * 100).toFixed(2) + '%',
                colorClass: (v) => v < 0.15 ? 'positive' : v < 0.25 ? 'neutral' : 'negative'
            },
            var: {
                title: 'VaR (95%)',
                icon: '⚠️',
                format: (v) => (v * 100).toFixed(2) + '%',
                colorClass: (v) => v > -0.05 ? 'positive' : v > -0.10 ? 'neutral' : 'negative'
            }
        };

        // 更新状态指示器
        function updateStatus(running) {
            isRunning = running;
            const dot = document.getElementById('status-dot');
            const text = document.getElementById('status-text');

            if (running) {
                dot.className = 'status-dot running';
                text.textContent = '系统运行中';
            } else {
                dot.className = 'status-dot stopped';
                text.textContent = '系统已停止';
            }
        }

        // 更新时间
        function updateTime() {
            const now = new Date();
            document.getElementById('update-time').textContent =
                now.toLocaleTimeString('zh-CN');
        }

        // 创建迷你图表
        function createSparkline(data, width = 100, height = 40) {
            if (!data || data.length < 2) return '';

            const max = Math.max(...data);
            const min = Math.min(...data);
            const range = max - min || 1;

            const points = data.map((v, i) => {
                const x = (i / (data.length - 1)) * width;
                const y = height - ((v - min) / range) * height;
                return `${x},${y}`;
            }).join(' ');

            return `
                <svg width="${width}" height="${height}">
                    <polyline points="${points}" class="sparkline"/>
                </svg>
            `;
        }

        // 渲染指标卡片
        function renderMetrics(metrics) {
            const dashboard = document.getElementById('metrics-dashboard');
            dashboard.innerHTML = '';

            for (const [key, data] of Object.entries(metrics)) {
                const config = metricConfigs[key];
                if (!config || !data.last_value) continue;

                const card = document.createElement('div');
                card.className = 'metric-card';

                const value = data.last_value;
                const stats = data.statistics || {};

                card.innerHTML = `
                    <div class="metric-header">
                        <span class="metric-title">${config.title}</span>
                        <span class="metric-icon">${config.icon}</span>
                    </div>
                    <div class="metric-value ${config.colorClass(value)}">
                        ${config.format(value)}
                    </div>
                    <div class="metric-change">
                        均值: ${config.format(stats.mean || 0)} |
                        标准差: ${config.format(stats.std || 0)}
                    </div>
                    <div class="metric-chart">
                        <!-- 这里可以添加实际的图表 -->
                    </div>
                `;

                dashboard.appendChild(card);
            }
        }

        // 渲染告警
        function renderAlerts(alerts) {
            const alertsList = document.getElementById('alerts-list');
            const alertCount = document.getElementById('alert-count');

            if (!alerts || alerts.length === 0) {
                alertsList.innerHTML = '<div class="no-data">暂无告警</div>';
                alertCount.textContent = '0 个告警';
                return;
            }

            alertCount.textContent = `${alerts.length} 个告警`;
            alertsList.innerHTML = '';

            // 只显示最近10个告警
            alerts.slice(-10).reverse().forEach(alert => {
                const item = document.createElement('div');
                item.className = `alert-item ${alert.level}`;

                const icons = {
                    info: 'ℹ️',
                    warning: '⚠️',
                    critical: '🔴',
                    emergency: '🆘'
                };

                const time = new Date(alert.timestamp);
                const timeStr = time.toLocaleTimeString('zh-CN');

                item.innerHTML = `
                    <span class="alert-icon">${icons[alert.level] || '⚪'}</span>
                    <div class="alert-content">
                        <div class="alert-message">${alert.message}</div>
                        <div class="alert-time">${timeStr} | ${alert.metric}</div>
                    </div>
                `;

                alertsList.appendChild(item);
            });
        }

        // 获取数据
        async function fetchData() {
            try {
                const response = await fetch(`${API_BASE}/status`);
                const data = await response.json();

                updateStatus(data.is_running);
                renderMetrics(data.monitors || {});
                renderAlerts(data.alerts?.recent || []);
                updateTime();
            } catch (error) {
                console.error('获取数据失败:', error);
                updateStatus(false);
            }
        }

        // 定期更新
        function startAutoUpdate() {
            fetchData();
            setInterval(fetchData, UPDATE_INTERVAL);
        }

        // 初始化
        document.addEventListener('DOMContentLoaded', () => {
            startAutoUpdate();
        });
    </script>
</body>
</html>
"""


# ============================================================================
# Flask应用
# ============================================================================

class MonitoringDashboardApp:
    """监控仪表板Web应用"""

    def __init__(self, monitoring_system: MonitoringSystem, port: int = 5000):
        self.monitoring_system = monitoring_system
        self.port = port

        # 创建Flask应用
        self.app = Flask(__name__)
        CORS(self.app)  # 允许跨域访问

        # 注册路由
        self._register_routes()

    def _register_routes(self):
        """注册路由"""

        @self.app.route('/')
        def index():
            """首页"""
            return render_template_string(DASHBOARD_TEMPLATE)

        @self.app.route('/api/status')
        def get_status():
            """获取监控状态"""
            status = self.monitoring_system.get_status()
            return jsonify(status)

        @self.app.route('/api/metrics/<metric_type>')
        def get_metric(metric_type):
            """获取特定指标"""
            monitor = self.monitoring_system.monitors.get(metric_type)
            if not monitor:
                return jsonify({"error": "指标不存在"}), 404

            return jsonify({
                "metric_type": metric_type,
                "last_value": monitor.last_value,
                "last_update": monitor.last_update.isoformat() if monitor.last_update else None,
                "statistics": monitor.get_statistics(),
                "history": [
                    {
                        "timestamp": h["timestamp"].isoformat(),
                        "value": h["value"]
                    }
                    for h in list(monitor.history)[-100:]
                ]
            })

        @self.app.route('/api/alerts')
        def get_alerts():
            """获取告警历史"""
            alerts = []
            for alert in self.monitoring_system.alert_history:
                alerts.append({
                    "timestamp": alert.timestamp.isoformat(),
                    "level": alert.level.value,
                    "metric": alert.metric_type.value,
                    "message": alert.message,
                    "value": alert.value,
                    "threshold": alert.threshold
                })
            return jsonify(alerts)

        @self.app.route('/api/start', methods=['POST'])
        def start_monitoring():
            """启动监控"""
            self.monitoring_system.start()
            return jsonify({"status": "started"})

        @self.app.route('/api/stop', methods=['POST'])
        def stop_monitoring():
            """停止监控"""
            self.monitoring_system.stop()
            return jsonify({"status": "stopped"})

    def run(self, debug: bool = False):
        """运行Web应用"""
        logger.info(f"监控仪表板启动在 http://localhost:{self.port}")
        self.app.run(host='0.0.0.0', port=self.port, debug=debug)


# ============================================================================
# CLI仪表板
# ============================================================================

def create_cli_dashboard(monitoring_system: MonitoringSystem):
    """创建命令行仪表板"""
    import curses
    import time

    def draw_dashboard(stdscr, status):
        """绘制仪表板"""
        stdscr.clear()
        height, width = stdscr.getmaxyx()

        # 标题
        title = "策略监控仪表板"
        stdscr.addstr(0, (width - len(title)) // 2, title, curses.A_BOLD)

        # 状态
        status_text = f"状态: {'运行中' if status['is_running'] else '已停止'}"
        stdscr.addstr(2, 2, status_text)

        # 更新时间
        time_text = f"更新: {datetime.now().strftime('%H:%M:%S')}"
        stdscr.addstr(2, width - len(time_text) - 2, time_text)

        # 分隔线
        stdscr.addstr(3, 0, "-" * width)

        # 指标部分
        row = 5
        stdscr.addstr(row, 2, "指标监控:", curses.A_BOLD)
        row += 2

        for metric_name, metric_data in status["monitors"].items():
            value = metric_data.get("last_value")
            if value is not None:
                # 格式化值
                if metric_name in ["drawdown", "var", "volatility"]:
                    display_value = f"{value*100:>8.2f}%"
                else:
                    display_value = f"{value:>8.3f}"

                # 显示
                line = f"  {metric_name:12s}: {display_value}"
                stdscr.addstr(row, 2, line)
                row += 1

        # 分隔线
        row += 1
        stdscr.addstr(row, 0, "-" * width)

        # 告警部分
        row += 2
        stdscr.addstr(row, 2, "最近告警:", curses.A_BOLD)
        row += 2

        alerts = status["alerts"]["recent"]
        if alerts:
            for alert in alerts[-5:]:
                alert_time = datetime.fromisoformat(alert["timestamp"])
                alert_line = f"  [{alert_time.strftime('%H:%M:%S')}] {alert['level']:8s} {alert['metric']:12s}"
                stdscr.addstr(row, 2, alert_line[:width-4])
                row += 1
        else:
            stdscr.addstr(row, 2, "  暂无告警")

        stdscr.refresh()

    def main(stdscr):
        """主函数"""
        curses.curs_set(0)  # 隐藏光标
        stdscr.nodelay(1)   # 非阻塞输入
        stdscr.timeout(1000)  # 1秒超时

        while True:
            try:
                status = monitoring_system.get_status()
                draw_dashboard(stdscr, status)

                # 检查键盘输入
                key = stdscr.getch()
                if key == ord('q'):
                    break
                elif key == ord('s'):
                    monitoring_system.start()
                elif key == ord('t'):
                    monitoring_system.stop()

            except KeyboardInterrupt:
                break

    # 运行curses应用
    curses.wrapper(main)


# ============================================================================
# 使用示例
# ============================================================================

if __name__ == "__main__":
    import sys

    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # 创建监控系统
    config = MonitorConfig(
        check_interval=5,
        notification_channels=["log", "file"]
    )

    monitoring = MonitoringSystem(config)

    # 模拟数据源（实际应该连接到真实的策略）
    import numpy as np

    values = [1000000]

    def get_mock_data():
        """模拟数据"""
        change = np.random.randn() * 0.01
        values.append(values[-1] * (1 + change))
        return pd.Series(values[-100:])

    # 注册数据源
    for metric_type in ["drawdown", "sharpe", "volatility", "var"]:
        monitoring.register_data_source(metric_type, get_mock_data)

    # 启动监控
    monitoring.start()

    # 选择界面类型
    if len(sys.argv) > 1 and sys.argv[1] == "cli":
        # CLI界面
        create_cli_dashboard(monitoring)
    else:
        # Web界面
        app = MonitoringDashboardApp(monitoring, port=5000)
        app.run(debug=True)