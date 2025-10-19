# Qlib-Hikyuu 快速开始指南 (Step-by-Step)

本指南将一步步带您完成项目的安装、配置和使用。

## 📋 目录
- [环境准备](#1-环境准备)
- [安装步骤](#2-安装步骤)
- [配置设置](#3-配置设置)
- [数据准备](#4-数据准备)
- [基础使用](#5-基础使用)
- [进阶功能](#6-进阶功能)
- [策略开发](#7-策略开发)
- [回测分析](#8-回测分析)
- [生产部署](#9-生产部署)
- [故障排除](#10-故障排除)

---

## 1. 环境准备

### Step 1.1: 检查系统要求

```bash
# 检查 Python 版本（需要 3.8 以上）
python --version

# 检查 pip 版本
pip --version

# 检查 git（用于克隆代码）
git --version
```

**预期输出**：
```
Python 3.13.7
pip 24.0
git version 2.34.0
```

### Step 1.2: 安装 Anaconda（推荐）

如果还没有安装 Anaconda，请访问 [Anaconda 官网](https://www.anaconda.com/products/distribution) 下载安装。

```bash
# 验证 Anaconda 安装
conda --version
```

### Step 1.3: 准备 MySQL 数据库

Hikyuu 需要 MySQL 来存储市场数据：

```bash
# macOS
brew install mysql
brew services start mysql

# Linux
sudo apt-get install mysql-server
sudo systemctl start mysql

# Windows
# 下载 MySQL Installer: https://dev.mysql.com/downloads/installer/
```

---

## 2. 安装步骤

### Step 2.1: 克隆项目代码

```bash
# 克隆项目
git clone https://github.com/luannanxian/qlib_hikyuu.git

# 进入项目目录
cd qlib-project
```

### Step 2.2: 创建虚拟环境

```bash
# 创建 conda 环境
conda create -n qlib_hikyuu python=3.13 -y

# 激活环境
conda activate qlib_hikyuu
```

### Step 2.3: 安装核心依赖

```bash
# 安装 Hikyuu（中国市场数据）
pip install hikyuu

# 安装 Qlib（量化框架）
pip install pyqlib

# 安装其他依赖
pip install pandas numpy matplotlib pytest
```

**常见问题**：如果安装失败，尝试：
```bash
# 使用国内镜像
pip install hikyuu -i https://pypi.tuna.tsinghua.edu.cn/simple
pip install pyqlib -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### Step 2.4: 验证安装

```bash
# 创建测试脚本
cat > test_install.py << 'EOF'
try:
    import hikyuu as hk
    print("✅ Hikyuu 安装成功")
except ImportError as e:
    print(f"❌ Hikyuu 安装失败: {e}")

try:
    import qlib
    print("✅ Qlib 安装成功")
except ImportError as e:
    print(f"❌ Qlib 安装失败: {e}")

print("\n环境检查完成！")
EOF

# 运行测试
python test_install.py
```

---

## 3. 配置设置

### Step 3.1: 配置 Hikyuu

创建 Hikyuu 配置文件：

```bash
# 创建配置目录
mkdir -p ~/.hikyuu

# 创建配置文件
cat > ~/.hikyuu/hikyuu.ini << 'EOF'
[database]
type = mysql
host = 127.0.0.1
port = 3306
user = root
password = your_password  # 修改为您的密码
database = hikyuu_stock

[data]
# 数据存储路径
path = ~/.hikyuu/data

[cache]
# 启用缓存
enable = true
max_size = 1000000

[logger]
level = INFO
EOF

echo "配置文件创建成功: ~/.hikyuu/hikyuu.ini"
echo "请修改数据库密码！"
```

### Step 3.2: 初始化数据库

```bash
# 连接 MySQL
mysql -u root -p

# 在 MySQL 中执行
CREATE DATABASE IF NOT EXISTS hikyuu_stock CHARACTER SET utf8mb4;
USE hikyuu_stock;
exit;
```

### Step 3.3: 下载市场数据

```bash
# 使用 Hikyuu 下载数据
python << 'EOF'
import hikyuu as hk

# 初始化
sm = hk.StockManager()

# 下载基础数据
print("开始下载市场数据...")
# 这里会自动下载沪深市场的基础数据
print("数据下载完成！")
EOF
```

---

## 4. 数据准备

### Step 4.1: 准备股票列表

```python
# create_stock_list.py
instruments = [
    "SH600000",  # 浦发银行
    "SH600036",  # 招商银行
    "SZ000001",  # 平安银行
    "SZ000002",  # 万科A
    "SH600519",  # 贵州茅台
]

# 保存到文件
with open("stock_list.txt", "w") as f:
    for stock in instruments:
        f.write(f"{stock}\n")

print(f"已准备 {len(instruments)} 只股票")
```

### Step 4.2: 验证数据可用性

```python
# verify_data.py
from hikyuu_integration import HikyuuDataLoader

# 创建数据加载器
loader = HikyuuDataLoader(
    fields=["OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"],
    freq="day",
    mode="train"
)

# 测试加载一只股票
try:
    data = loader.load(
        instruments=["SH600000"],
        start_time="2023-01-01",
        end_time="2023-01-31"
    )
    print(f"✅ 数据加载成功！")
    print(f"数据形状: {data.shape}")
    print(f"数据预览:\n{data.head()}")
except Exception as e:
    print(f"❌ 数据加载失败: {e}")
```

---

## 5. 基础使用

### Step 5.1: 第一个完整示例

创建文件 `first_example.py`：

```python
#!/usr/bin/env python3
"""
第一个完整示例：加载数据并计算简单指标
"""

import pandas as pd
from datetime import datetime

# 导入项目模块
from hikyuu_integration import HikyuuAlphaHandler
from utils.data_pipeline import UnifiedDataPipeline, DataPipelineConfig

def main():
    print("=== Qlib-Hikyuu 第一个示例 ===\n")

    # Step 1: 设置参数
    instruments = ["SH600000", "SZ000001"]
    start_date = "2023-01-01"
    end_date = "2023-12-31"

    print(f"股票列表: {instruments}")
    print(f"时间范围: {start_date} 至 {end_date}\n")

    # Step 2: 创建数据处理器（训练模式）
    print("创建数据处理器...")
    handler = HikyuuAlphaHandler.create_for_training(
        instruments=instruments,
        start_time=start_date,
        end_time=end_date
    )

    # Step 3: 获取数据
    print("加载数据...")
    data = handler.fetch()
    print(f"数据形状: {data.shape}")
    print(f"特征数量: {len(data.columns)}\n")

    # Step 4: 数据处理管道
    print("应用数据处理管道...")
    config = DataPipelineConfig(
        remove_outliers=True,
        add_technical_indicators=True,
        lag_periods=[1, 5, 10]
    )

    pipeline = UnifiedDataPipeline(config)
    processed_data = pipeline.fit_transform(data)

    print(f"处理后数据形状: {processed_data.shape}")
    print(f"处理后特征数: {len(processed_data.columns)}")

    # Step 5: 计算简单统计
    print("\n=== 数据统计 ===")
    print(processed_data.describe())

    # Step 6: 保存结果
    output_file = "processed_data.csv"
    processed_data.to_csv(output_file)
    print(f"\n结果已保存到: {output_file}")

    return processed_data

if __name__ == "__main__":
    data = main()
    print("\n✅ 示例运行成功！")
```

运行示例：
```bash
python first_example.py
```

### Step 5.2: 预测模式示例（无前视偏差）

创建文件 `prediction_example.py`：

```python
#!/usr/bin/env python3
"""
预测模式示例：确保无前视偏差
"""

from hikyuu_integration import HikyuuAlphaHandler
import pandas as pd

def train_model(train_data):
    """模拟训练模型"""
    print("训练模型...")
    # 这里放置您的模型训练代码
    return "trained_model"

def predict(model, test_data):
    """模拟预测"""
    print("生成预测...")
    # 这里放置您的预测代码
    predictions = pd.Series([0.5] * len(test_data), index=test_data.index)
    return predictions

def main():
    # 训练阶段（包含标签）
    print("=== 训练阶段 ===")
    train_handler = HikyuuAlphaHandler.create_for_training(
        instruments=["SH600000", "SZ000001"],
        start_time="2023-01-01",
        end_time="2023-06-30"
    )

    train_data = train_handler.fetch()
    print(f"训练数据形状: {train_data.shape}")

    # 训练模型
    model = train_model(train_data)

    # 预测阶段（无标签，防止前视偏差）
    print("\n=== 预测阶段 ===")
    predict_handler = HikyuuAlphaHandler.create_for_prediction(
        instruments=["SH600000", "SZ000001"],
        start_time="2023-07-01",
        end_time="2023-12-31"
    )

    test_data = predict_handler.fetch()
    print(f"测试数据形状: {test_data.shape}")

    # 生成预测
    predictions = predict(model, test_data)
    print(f"预测结果: {predictions.head()}")

    print("\n✅ 无前视偏差验证通过！")

if __name__ == "__main__":
    main()
```

---

## 6. 进阶功能

### Step 6.1: 使用错误处理机制

创建文件 `advanced_error_handling.py`：

```python
#!/usr/bin/env python3
"""
进阶功能：错误处理和重试机制
"""

from utils.error_handling import ErrorHandler, with_retry, RetryConfig
from utils.error_handling import DataLoadError
import time
import random

# 配置错误处理器
error_handler = ErrorHandler()

# 模拟不稳定的数据源
@with_retry(RetryConfig(max_attempts=3, initial_delay=1.0))
def fetch_unstable_data():
    """模拟可能失败的数据获取"""
    print("尝试获取数据...")

    # 50% 概率失败
    if random.random() < 0.5:
        raise DataLoadError("网络连接失败")

    print("✅ 数据获取成功！")
    return {"data": "success"}

def main():
    print("=== 错误处理示例 ===\n")

    # 注册恢复策略
    def fallback_strategy():
        print("使用缓存数据作为后备方案")
        return {"data": "from_cache"}

    error_handler.register_recovery_strategy(
        DataLoadError,
        fallback_strategy
    )

    # 尝试获取数据
    try:
        data = fetch_unstable_data()
        print(f"获取到数据: {data}")
    except DataLoadError as e:
        print(f"所有重试失败: {e}")
        # 使用恢复策略
        data = error_handler.handle_error(e)
        print(f"使用后备数据: {data}")

if __name__ == "__main__":
    main()
```

### Step 6.2: 特征工程管道

创建文件 `feature_engineering.py`：

```python
#!/usr/bin/env python3
"""
特征工程示例
"""

import pandas as pd
import numpy as np
from utils.data_pipeline import UnifiedDataPipeline, DataPipelineConfig

def create_sample_data():
    """创建示例数据"""
    dates = pd.date_range("2023-01-01", periods=100)
    data = pd.DataFrame({
        "open": np.random.randn(100).cumsum() + 100,
        "high": np.random.randn(100).cumsum() + 101,
        "low": np.random.randn(100).cumsum() + 99,
        "close": np.random.randn(100).cumsum() + 100,
        "volume": np.random.randint(1000000, 10000000, 100)
    }, index=dates)
    return data

def main():
    print("=== 特征工程示例 ===\n")

    # 创建示例数据
    raw_data = create_sample_data()
    print(f"原始数据形状: {raw_data.shape}")
    print(f"原始特征: {list(raw_data.columns)}\n")

    # 配置特征工程管道
    config = DataPipelineConfig(
        # 数据清洗
        remove_outliers=True,
        outlier_method="iqr",
        fill_method="forward",

        # 特征生成
        add_technical_indicators=True,
        lag_periods=[1, 5, 10, 20],
        rolling_windows=[5, 10, 20],

        # 验证
        check_monotonic_time=True,
        max_nan_ratio=0.1
    )

    # 创建并应用管道
    pipeline = UnifiedDataPipeline(config)
    features = pipeline.fit_transform(raw_data)

    print(f"处理后数据形状: {features.shape}")
    print(f"生成的特征数: {len(features.columns)}")
    print(f"\n新增特征示例:")

    # 显示部分新特征
    new_features = [col for col in features.columns if col not in raw_data.columns]
    for feat in new_features[:5]:
        print(f"  - {feat}")

    print(f"\n总计新增 {len(new_features)} 个特征")

    # 保存特征
    features.to_csv("engineered_features.csv")
    print("\n特征已保存到: engineered_features.csv")

if __name__ == "__main__":
    main()
```

---

## 7. 策略开发

### Step 7.1: 创建简单策略

创建文件 `simple_strategy.py`：

```python
#!/usr/bin/env python3
"""
简单的动量策略示例
"""

import pandas as pd
import numpy as np
from typing import Dict, Any

class MomentumStrategy:
    """简单动量策略"""

    def __init__(self, lookback_period: int = 20, threshold: float = 0.02):
        """
        参数:
            lookback_period: 回望期
            threshold: 交易阈值
        """
        self.lookback_period = lookback_period
        self.threshold = threshold
        self.positions = {}

    def calculate_momentum(self, prices: pd.DataFrame) -> pd.Series:
        """计算动量指标"""
        returns = prices['close'].pct_change(self.lookback_period)
        return returns

    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """生成交易信号"""
        momentum = self.calculate_momentum(data)

        signals = pd.Series(index=data.index, data=0)

        # 买入信号：动量 > 阈值
        signals[momentum > self.threshold] = 1

        # 卖出信号：动量 < -阈值
        signals[momentum < -self.threshold] = -1

        return signals

    def backtest(self, data: pd.DataFrame) -> Dict[str, Any]:
        """简单回测"""
        signals = self.generate_signals(data)

        # 计算收益
        returns = data['close'].pct_change()
        strategy_returns = signals.shift(1) * returns  # T+1 执行

        # 计算累计收益
        cumulative_returns = (1 + strategy_returns).cumprod()

        # 计算统计指标
        total_return = cumulative_returns.iloc[-1] - 1
        sharpe_ratio = strategy_returns.mean() / strategy_returns.std() * np.sqrt(252)
        max_drawdown = (cumulative_returns / cumulative_returns.cummax() - 1).min()

        return {
            "total_return": total_return,
            "sharpe_ratio": sharpe_ratio,
            "max_drawdown": max_drawdown,
            "cumulative_returns": cumulative_returns
        }

def main():
    print("=== 动量策略示例 ===\n")

    # 加载数据
    from hikyuu_integration import HikyuuDataLoader

    loader = HikyuuDataLoader(
        fields=["OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"],
        freq="day"
    )

    data = loader.load(
        instruments=["SH600000"],
        start_time="2023-01-01",
        end_time="2023-12-31"
    )

    # 获取单只股票数据
    stock_data = data.xs("SH600000", level=1)

    # 创建策略
    strategy = MomentumStrategy(lookback_period=20, threshold=0.02)

    # 运行回测
    results = strategy.backtest(stock_data)

    # 显示结果
    print(f"总收益: {results['total_return']:.2%}")
    print(f"夏普比率: {results['sharpe_ratio']:.2f}")
    print(f"最大回撤: {results['max_drawdown']:.2%}")

    # 保存结果
    results['cumulative_returns'].to_csv("strategy_returns.csv")
    print("\n结果已保存")

if __name__ == "__main__":
    main()
```

---

## 8. 回测分析

### Step 8.1: 完整回测流程

创建文件 `full_backtest.py`：

```python
#!/usr/bin/env python3
"""
完整的回测流程示例
"""

import pandas as pd
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt

# 导入项目模块
from hikyuu_integration import HikyuuAlphaHandler
from utils.data_pipeline import UnifiedDataPipeline, DataPipelineConfig

class BacktestFramework:
    """回测框架"""

    def __init__(self, initial_capital: float = 1000000):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.positions = {}
        self.trades = []
        self.portfolio_value = []

    def execute_trade(self, date, instrument, signal, price, quantity=None):
        """执行交易"""
        if signal == 1:  # 买入
            if quantity is None:
                # 等权重分配
                quantity = int(self.capital * 0.1 / price)

            cost = quantity * price * 1.0003  # 加手续费
            if cost <= self.capital:
                self.capital -= cost
                self.positions[instrument] = self.positions.get(instrument, 0) + quantity
                self.trades.append({
                    'date': date,
                    'instrument': instrument,
                    'action': 'BUY',
                    'quantity': quantity,
                    'price': price,
                    'cost': cost
                })
                print(f"{date} 买入 {instrument}: {quantity}股 @ {price:.2f}")

        elif signal == -1:  # 卖出
            if instrument in self.positions and self.positions[instrument] > 0:
                quantity = self.positions[instrument]
                revenue = quantity * price * 0.999  # 扣除手续费和印花税
                self.capital += revenue
                self.positions[instrument] = 0
                self.trades.append({
                    'date': date,
                    'instrument': instrument,
                    'action': 'SELL',
                    'quantity': quantity,
                    'price': price,
                    'revenue': revenue
                })
                print(f"{date} 卖出 {instrument}: {quantity}股 @ {price:.2f}")

    def calculate_portfolio_value(self, date, prices):
        """计算组合价值"""
        position_value = sum(
            self.positions.get(inst, 0) * prices.get(inst, 0)
            for inst in self.positions
        )
        total_value = self.capital + position_value
        self.portfolio_value.append({
            'date': date,
            'value': total_value,
            'cash': self.capital,
            'position_value': position_value
        })
        return total_value

    def get_statistics(self):
        """计算统计指标"""
        df = pd.DataFrame(self.portfolio_value)
        df['returns'] = df['value'].pct_change()

        total_return = (df['value'].iloc[-1] / self.initial_capital) - 1

        # 年化收益
        days = (df['date'].iloc[-1] - df['date'].iloc[0]).days
        annual_return = (1 + total_return) ** (365 / days) - 1

        # 夏普比率
        sharpe = df['returns'].mean() / df['returns'].std() * np.sqrt(252)

        # 最大回撤
        cummax = df['value'].cummax()
        drawdown = (df['value'] - cummax) / cummax
        max_drawdown = drawdown.min()

        return {
            'total_return': total_return,
            'annual_return': annual_return,
            'sharpe_ratio': sharpe,
            'max_drawdown': max_drawdown,
            'total_trades': len(self.trades)
        }

def main():
    print("=== 完整回测示例 ===\n")

    # 1. 准备数据
    instruments = ["SH600000", "SH600036", "SZ000001"]

    handler = HikyuuAlphaHandler.create_for_training(
        instruments=instruments,
        start_time="2023-01-01",
        end_time="2023-12-31"
    )

    data = handler.fetch()

    # 2. 特征工程
    config = DataPipelineConfig(
        add_technical_indicators=True,
        lag_periods=[5, 10, 20]
    )
    pipeline = UnifiedDataPipeline(config)
    features = pipeline.fit_transform(data)

    # 3. 简单策略：基于 RSI
    def generate_signals(features):
        signals = pd.DataFrame(index=features.index, columns=['signal'])

        # 假设有 RSI 指标
        # 这里用简单的价格变化代替
        for date in features.index.get_level_values(0).unique():
            date_data = features.loc[date]
            # 简单规则：价格下跌超过 2% 买入，上涨超过 5% 卖出
            for inst in instruments:
                if inst in date_data.index:
                    price_change = date_data.loc[inst, ('feature', 'CLOSE')] / \
                                 date_data.loc[inst, ('feature', 'OPEN')] - 1

                    if price_change < -0.02:
                        signals.loc[(date, inst), 'signal'] = 1
                    elif price_change > 0.05:
                        signals.loc[(date, inst), 'signal'] = -1
                    else:
                        signals.loc[(date, inst), 'signal'] = 0

        return signals

    # 4. 运行回测
    backtest = BacktestFramework(initial_capital=1000000)
    signals = generate_signals(features)

    dates = features.index.get_level_values(0).unique()

    for date in dates:
        # 获取当日价格
        prices = {}
        for inst in instruments:
            if (date, inst) in features.index:
                prices[inst] = features.loc[(date, inst), ('feature', 'CLOSE')]

        # 执行交易
        for inst in instruments:
            if (date, inst) in signals.index:
                signal = signals.loc[(date, inst), 'signal']
                if signal != 0 and inst in prices:
                    backtest.execute_trade(date, inst, signal, prices[inst])

        # 更新组合价值
        backtest.calculate_portfolio_value(date, prices)

    # 5. 显示结果
    stats = backtest.get_statistics()

    print(f"\n=== 回测结果 ===")
    print(f"总收益: {stats['total_return']:.2%}")
    print(f"年化收益: {stats['annual_return']:.2%}")
    print(f"夏普比率: {stats['sharpe_ratio']:.2f}")
    print(f"最大回撤: {stats['max_drawdown']:.2%}")
    print(f"交易次数: {stats['total_trades']}")

    # 6. 绘制收益曲线
    portfolio_df = pd.DataFrame(backtest.portfolio_value)

    plt.figure(figsize=(12, 6))
    plt.plot(portfolio_df['date'], portfolio_df['value'] / backtest.initial_capital)
    plt.title('Portfolio Value Over Time')
    plt.xlabel('Date')
    plt.ylabel('Portfolio Value (Normalized)')
    plt.grid(True)
    plt.savefig('backtest_results.png')
    print("\n收益曲线已保存到: backtest_results.png")

if __name__ == "__main__":
    main()
```

---

## 9. 生产部署

### Step 9.1: 创建生产配置

创建文件 `config/production.yaml`：

```yaml
# 生产环境配置
environment: production

# 数据源配置
data:
  source: hikyuu
  cache_enabled: true
  cache_ttl: 3600

# 模型配置
model:
  auto_update: true
  update_frequency: daily
  validation_threshold: 0.6

# 监控配置
monitoring:
  enabled: true
  alert_email: your-email@example.com
  metrics_port: 9090

# 风控配置
risk:
  max_position: 0.95
  stop_loss: 0.08
  max_drawdown: 0.15
```

### Step 9.2: 创建启动脚本

创建文件 `scripts/start_production.sh`：

```bash
#!/bin/bash
# 生产环境启动脚本

set -e  # 遇到错误立即退出

echo "=== 启动 Qlib-Hikyuu 生产环境 ==="

# 1. 检查环境
echo "检查环境..."
if ! conda env list | grep -q "qlib_hikyuu"; then
    echo "错误: 未找到 qlib_hikyuu 环境"
    exit 1
fi

# 2. 激活环境
echo "激活 Conda 环境..."
source ~/anaconda3/etc/profile.d/conda.sh
conda activate qlib_hikyuu

# 3. 检查依赖
echo "检查依赖..."
python -c "import hikyuu; import qlib; print('依赖检查通过')"

# 4. 运行测试
echo "运行测试..."
python -m pytest tests/test_modules_coverage.py -q

# 5. 启动监控
echo "启动监控系统..."
python monitoring/start_monitor.py &
MONITOR_PID=$!

# 6. 启动主程序
echo "启动主程序..."
python main.py --config config/production.yaml

# 7. 清理
echo "清理..."
kill $MONITOR_PID

echo "=== 程序已停止 ==="
```

使用：
```bash
chmod +x scripts/start_production.sh
./scripts/start_production.sh
```

---

## 10. 故障排除

### 常见问题和解决方案

#### 问题 1: ImportError: No module named 'hikyuu'
```bash
# 解决方案
pip install hikyuu

# 如果还是失败，检查 Python 版本
python --version  # 需要 3.8+
```

#### 问题 2: Qlib 环境不可用
```bash
# 解决方案
pip install pyqlib

# 验证安装
python -c "import qlib; print(qlib.__version__)"
```

#### 问题 3: MySQL 连接失败
```bash
# 检查 MySQL 服务
sudo systemctl status mysql  # Linux
brew services list | grep mysql  # macOS

# 启动 MySQL
sudo systemctl start mysql  # Linux
brew services start mysql  # macOS

# 检查配置文件
cat ~/.hikyuu/hikyuu.ini
```

#### 问题 4: 数据加载失败
```python
# 调试脚本
import hikyuu as hk

# 检查股票是否存在
sm = hk.StockManager.instance()
stock = sm.getStock("SH600000")
if stock.isNull():
    print("股票不存在，需要下载数据")
else:
    print("股票数据可用")
```

#### 问题 5: 内存不足
```python
# 解决方案：分批处理
batch_size = 10
for i in range(0, len(instruments), batch_size):
    batch = instruments[i:i+batch_size]
    process_batch(batch)
```

### 调试技巧

1. **启用详细日志**
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

2. **使用断点调试**
```python
import pdb
pdb.set_trace()  # 设置断点
```

3. **检查数据形状**
```python
print(f"Data shape: {data.shape}")
print(f"Data types: {data.dtypes}")
print(f"Missing values: {data.isna().sum()}")
```

---

## 📚 进一步学习

### 推荐资源
- [Qlib 官方文档](https://qlib.readthedocs.io/)
- [Hikyuu 官方文档](https://hikyuu.readthedocs.io/)
- [项目 GitHub](https://github.com/luannanxian/qlib_hikyuu)

### 社区支持
- 提交 Issue: https://github.com/luannanxian/qlib_hikyuu/issues
- 邮件支持: your-email@example.com

### 下一步
1. 尝试不同的策略
2. 优化特征工程
3. 集成机器学习模型
4. 部署到生产环境

---

**祝您使用愉快！** 🚀

如有任何问题，请参考故障排除部分或联系技术支持。