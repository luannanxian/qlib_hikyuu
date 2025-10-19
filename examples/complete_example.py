#!/usr/bin/env python3
"""
完整的端到端示例：从数据加载到策略回测
"""

import pandas as pd
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
import sys
import os

# 添加项目路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入项目模块
from hikyuu_integration import HikyuuAlphaHandler
from utils.data_pipeline import UnifiedDataPipeline, DataPipelineConfig
from utils.error_handling import ErrorHandler, with_retry, RetryConfig

class SimpleQuantStrategy:
    """简单的量化策略示例"""

    def __init__(self, name="SimpleQuant"):
        self.name = name
        self.signals = []
        self.positions = {}

    def calculate_signals(self, data):
        """
        计算交易信号
        使用简单的均线策略：
        - MA5 上穿 MA20：买入信号
        - MA5 下穿 MA20：卖出信号
        """
        signals = pd.DataFrame(index=data.index)

        # 计算移动平均
        ma5 = data[('feature', 'CLOSE')].rolling(window=5).mean()
        ma20 = data[('feature', 'CLOSE')].rolling(window=20).mean()

        # 生成信号
        signals['ma5'] = ma5
        signals['ma20'] = ma20
        signals['signal'] = 0

        # 金叉买入
        signals.loc[ma5 > ma20, 'signal'] = 1
        # 死叉卖出
        signals.loc[ma5 < ma20, 'signal'] = -1

        # 计算信号变化（避免重复信号）
        signals['positions'] = signals['signal'].diff()

        return signals

    def backtest(self, data, initial_capital=1000000):
        """运行回测"""
        print(f"\n开始回测策略: {self.name}")
        print(f"初始资金: {initial_capital:,.0f}")

        # 计算信号
        signals = self.calculate_signals(data)

        # 初始化
        capital = initial_capital
        shares = 0
        portfolio = []
        trades = []

        # 逐日回测
        for idx, row in signals.iterrows():
            date = idx[0] if isinstance(idx, tuple) else idx
            instrument = idx[1] if isinstance(idx, tuple) else "SH600000"

            if pd.isna(row['positions']) or row['positions'] == 0:
                continue

            price = data.loc[idx, ('feature', 'CLOSE')]

            if row['positions'] > 0:  # 买入信号
                # 使用50%资金买入
                buy_amount = capital * 0.5
                buy_shares = int(buy_amount / price)

                if buy_shares > 0:
                    cost = buy_shares * price * 1.0003  # 加上手续费
                    if cost <= capital:
                        capital -= cost
                        shares += buy_shares
                        trades.append({
                            'date': date,
                            'action': 'BUY',
                            'price': price,
                            'shares': buy_shares,
                            'amount': cost
                        })
                        print(f"{date} 买入 {buy_shares}股 @ {price:.2f}")

            elif row['positions'] < 0 and shares > 0:  # 卖出信号
                revenue = shares * price * 0.999  # 扣除手续费和印花税
                capital += revenue
                trades.append({
                    'date': date,
                    'action': 'SELL',
                    'price': price,
                    'shares': shares,
                    'amount': revenue
                })
                print(f"{date} 卖出 {shares}股 @ {price:.2f}")
                shares = 0

            # 记录每日组合价值
            portfolio_value = capital + shares * price
            portfolio.append({
                'date': date,
                'capital': capital,
                'shares': shares,
                'price': price,
                'value': portfolio_value,
                'return': (portfolio_value / initial_capital - 1) * 100
            })

        # 计算统计指标
        portfolio_df = pd.DataFrame(portfolio)
        if not portfolio_df.empty:
            total_return = (portfolio_df['value'].iloc[-1] / initial_capital - 1) * 100
            max_value = portfolio_df['value'].max()
            max_drawdown = ((max_value - portfolio_df['value'].min()) / max_value) * 100

            print(f"\n=== 回测结果 ===")
            print(f"最终资金: {portfolio_df['value'].iloc[-1]:,.0f}")
            print(f"总收益率: {total_return:.2f}%")
            print(f"最大回撤: {max_drawdown:.2f}%")
            print(f"交易次数: {len(trades)}")

            return {
                'portfolio': portfolio_df,
                'trades': pd.DataFrame(trades),
                'total_return': total_return,
                'max_drawdown': max_drawdown
            }
        else:
            print("没有生成交易信号")
            return None

def plot_results(results):
    """绘制回测结果"""
    if results is None:
        return

    portfolio = results['portfolio']

    fig, axes = plt.subplots(2, 1, figsize=(12, 8))

    # 组合价值曲线
    axes[0].plot(portfolio['date'], portfolio['value'], label='Portfolio Value')
    axes[0].set_title('Portfolio Value Over Time')
    axes[0].set_ylabel('Value')
    axes[0].grid(True)
    axes[0].legend()

    # 收益率曲线
    axes[1].plot(portfolio['date'], portfolio['return'], label='Return %', color='green')
    axes[1].axhline(y=0, color='r', linestyle='--', alpha=0.3)
    axes[1].set_title('Portfolio Return %')
    axes[1].set_xlabel('Date')
    axes[1].set_ylabel('Return %')
    axes[1].grid(True)
    axes[1].legend()

    plt.tight_layout()
    plt.savefig('backtest_results.png', dpi=100)
    print("\n图表已保存到: backtest_results.png")

def main():
    """主函数"""
    print("=" * 60)
    print("Qlib-Hikyuu 完整示例：端到端量化交易流程")
    print("=" * 60)

    # Step 1: 设置参数
    instruments = ["SH600000", "SZ000001"]  # 股票列表
    train_start = "2023-01-01"
    train_end = "2023-06-30"
    test_start = "2023-07-01"
    test_end = "2023-12-31"

    print(f"\n配置:")
    print(f"股票: {instruments}")
    print(f"训练期: {train_start} 至 {train_end}")
    print(f"测试期: {test_start} 至 {test_end}")

    try:
        # Step 2: 训练阶段 - 加载数据
        print("\n=== 训练阶段 ===")
        train_handler = HikyuuAlphaHandler.create_for_training(
            instruments=instruments,
            start_time=train_start,
            end_time=train_end
        )

        print("加载训练数据...")
        train_data = train_handler.fetch()
        print(f"训练数据形状: {train_data.shape}")

        # Step 3: 特征工程
        print("\n应用特征工程...")
        config = DataPipelineConfig(
            remove_outliers=True,
            outlier_method="iqr",
            add_technical_indicators=True,
            lag_periods=[1, 5, 10],
            rolling_windows=[5, 10, 20]
        )

        pipeline = UnifiedDataPipeline(config)
        train_features = pipeline.fit_transform(train_data)
        print(f"特征数量: {len(train_features.columns)}")

        # Step 4: 策略开发（使用训练数据）
        print("\n开发策略...")
        strategy = SimpleQuantStrategy(name="MA_Crossover")

        # 使用第一只股票进行策略开发
        stock_data = train_features.xs(instruments[0], level=1)
        train_results = strategy.backtest(stock_data, initial_capital=1000000)

        # Step 5: 测试阶段 - 验证策略（无前视偏差）
        print("\n=== 测试阶段（无前视偏差）===")
        test_handler = HikyuuAlphaHandler.create_for_prediction(
            instruments=instruments,
            start_time=test_start,
            end_time=test_end
        )

        print("加载测试数据...")
        test_data = test_handler.fetch()
        print(f"测试数据形状: {test_data.shape}")

        # 应用相同的特征工程
        test_features = pipeline.transform(test_data)  # 注意：只用transform，不重新fit

        # 在测试集上运行策略
        print("\n在测试集上验证策略...")
        test_stock_data = test_features.xs(instruments[0], level=1)
        test_results = strategy.backtest(test_stock_data, initial_capital=1000000)

        # Step 6: 绘制结果
        if test_results:
            plot_results(test_results)

        # Step 7: 保存结果
        if test_results:
            print("\n保存结果...")
            test_results['portfolio'].to_csv('portfolio_results.csv', index=False)
            test_results['trades'].to_csv('trades_history.csv', index=False)
            print("结果已保存到 CSV 文件")

        print("\n" + "=" * 60)
        print("✅ 示例运行成功！")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        print("请检查:")
        print("1. Hikyuu 和 Qlib 是否已正确安装")
        print("2. 数据库连接是否正常")
        print("3. 股票数据是否已下载")

        # 错误处理
        error_handler = ErrorHandler()
        error_handler.log_error(e)
        raise

if __name__ == "__main__":
    main()