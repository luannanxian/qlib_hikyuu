# Qlib-Hikyuu 使用指南

## 快速开始

### 1. 环境安装

#### 1.1 创建虚拟环境

```bash
# 使用 Conda 创建环境
conda create -n qlib_hikyuu python=3.13
conda activate qlib_hikyuu
```

#### 1.2 安装依赖

```bash
# 安装 Hikyuu
pip install hikyuu

# 安装 Qlib
pip install pyqlib

# 安装其他依赖
pip install pandas numpy matplotlib pytest
```

#### 1.3 配置 Hikyuu

创建配置文件 `~/.hikyuu/hikyuu.ini`：

```ini
[database]
type = mysql
host = 127.0.0.1
port = 3306
user = root
password = your_password
database = hikyuu

[data]
path = /Users/your_name/.hikyuu/data

[cache]
enable = true
max_size = 1000000
```

### 2. 基础使用

#### 2.1 数据加载

```python
from hikyuu_integration import HikyuuDataLoader

# 创建数据加载器
loader = HikyuuDataLoader(
    fields=["OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"],
    freq="day",
    mode="train"
)

# 加载数据
data = loader.load(
    instruments=["SH600000", "SZ000001"],
    start_time="2023-01-01",
    end_time="2023-12-31"
)

print(data.head())
```

#### 2.2 创建 Alpha Handler

```python
from hikyuu_integration import HikyuuAlphaHandler

# 训练模式
train_handler = HikyuuAlphaHandler.create_for_training(
    instruments=["SH600000", "SZ000001"],
    start_time="2023-01-01",
    end_time="2023-06-30"
)

# 预测模式（无前视偏差）
predict_handler = HikyuuAlphaHandler.create_for_prediction(
    instruments=["SH600000", "SZ000001"],
    start_time="2023-07-01",
    end_time="2023-12-31"
)
```

### 3. 高级功能

#### 3.1 数据处理管道

```python
from utils.data_pipeline import UnifiedDataPipeline, DataPipelineConfig

# 配置管道
config = DataPipelineConfig(
    # 数据清洗
    remove_outliers=True,
    outlier_method="iqr",
    outlier_threshold=3.0,
    fill_method="forward",

    # 特征工程
    add_technical_indicators=True,
    add_market_features=True,
    lag_periods=[1, 5, 10, 20],
    rolling_windows=[5, 10, 20, 60],

    # 数据验证
    check_monotonic_time=True,
    check_duplicates=True,
    max_nan_ratio=0.1
)

# 创建管道
pipeline = UnifiedDataPipeline(config)

# 处理数据
processed_data = pipeline.fit_transform(raw_data)
```

#### 3.2 错误处理

```python
from utils.error_handling import ErrorHandler, with_retry, RetryConfig

# 配置错误处理器
error_handler = ErrorHandler()

# 注册恢复策略
error_handler.register_recovery_strategy(
    DataLoadError,
    lambda: load_from_cache()
)

# 使用重试装饰器
@with_retry(RetryConfig(max_attempts=3, initial_delay=1.0))
def fetch_realtime_data():
    """获取实时数据，失败自动重试"""
    return data_source.fetch()
```

#### 3.3 回测系统

```python
from backtest import BacktestEngine, BacktestConfig
from strategy import MyStrategy

# 配置回测
config = BacktestConfig(
    start_date="2023-01-01",
    end_date="2023-12-31",
    t_plus_n=1,  # T+1 交易
    commission_rate=0.0003,
    slippage=0.001
)

# 创建回测引擎
engine = BacktestEngine(config)

# 运行回测
strategy = MyStrategy()
results = engine.run(strategy, data)

# 查看结果
print(f"总收益: {results.total_return:.2%}")
print(f"夏普比率: {results.sharpe_ratio:.2f}")
print(f"最大回撤: {results.max_drawdown:.2%}")
```

### 4. 策略开发

#### 4.1 创建自定义策略

```python
from strategy import Strategy
import pandas as pd

class MomentumStrategy(Strategy):
    """动量策略示例"""

    def __init__(self, lookback=20):
        self.lookback = lookback

    def generate_signals(self, data, date):
        """生成交易信号"""
        # 计算动量
        returns = data['close'].pct_change(self.lookback)

        # 生成信号
        signals = pd.Series(index=returns.index)
        signals[returns > 0.1] = 1   # 买入信号
        signals[returns < -0.1] = -1  # 卖出信号
        signals.fillna(0, inplace=True)

        return signals

    def calculate_position(self, signals, portfolio):
        """计算持仓"""
        # 等权重分配
        n_long = (signals == 1).sum()
        positions = signals.copy()
        positions[signals == 1] = 1.0 / n_long if n_long > 0 else 0

        return positions
```

#### 4.2 使用 Qlib 模型

```python
from qlib.contrib.model.gbdt import LGBModel

# 创建模型
model = LGBModel()

# 训练模型
model.fit(X_train, y_train)

# 预测
predictions = model.predict(X_test)

# 生成信号
signals = predictions > predictions.quantile(0.8)
```

### 5. 监控与报告

#### 5.1 设置监控

```python
from monitoring import MonitoringSystem, MonitoringConfig

# 配置监控
config = MonitoringConfig(
    enable_system_monitoring=True,
    enable_data_monitoring=True,
    alert_levels=["CRITICAL", "ERROR"],
    metrics_interval=60  # 60秒
)

# 创建监控系统
monitor = MonitoringSystem(config)

# 启动监控
monitor.start()

# 设置告警阈值
monitor.set_threshold("cpu_usage", 80)
monitor.set_threshold("memory_usage", 90)
```

#### 5.2 生成报告

```python
from reports import ReportGenerator, ReportConfig

# 配置报告
config = ReportConfig(
    report_types=["summary", "detailed"],
    output_formats=["html", "pdf"],
    include_charts=True
)

# 创建报告生成器
generator = ReportGenerator(config)

# 生成报告
report = generator.generate(backtest_results)

# 保存报告
report.save("backtest_report.html")
```

### 6. API 参考

#### 6.1 HikyuuDataLoader API

```python
class HikyuuDataLoader:
    """Hikyuu 数据加载器"""

    def __init__(self,
                 fields: Sequence[str],
                 freq: str = "day",
                 label_shift: int = 1,
                 mode: str = "train"):
        """
        参数：
            fields: 数据字段列表
            freq: 数据频率 ("day", "week", "month")
            label_shift: 标签偏移量
            mode: 运行模式 ("train" 或 "predict")
        """

    def load(self,
             instruments: Sequence[str],
             start_time: str,
             end_time: str) -> pd.DataFrame:
        """
        加载数据

        参数：
            instruments: 股票代码列表
            start_time: 开始时间
            end_time: 结束时间

        返回：
            MultiIndex DataFrame (datetime, instrument)
        """
```

#### 6.2 HikyuuAlphaHandler API

```python
class HikyuuAlphaHandler(DataHandlerLP):
    """Alpha 因子处理器"""

    @classmethod
    def create_for_training(cls,
                           instruments: Sequence[str],
                           start_time: str,
                           end_time: str,
                           **kwargs):
        """
        创建训练模式处理器

        参数：
            instruments: 股票代码列表
            start_time: 开始时间
            end_time: 结束时间
            **kwargs: 其他参数
        """

    @classmethod
    def create_for_prediction(cls,
                             instruments: Sequence[str],
                             start_time: str,
                             end_time: str,
                             **kwargs):
        """
        创建预测模式处理器（无前视偏差）
        """
```

#### 6.3 UnifiedDataPipeline API

```python
class UnifiedDataPipeline:
    """统一数据处理管道"""

    def __init__(self, config: DataPipelineConfig):
        """
        参数：
            config: 管道配置
        """

    def fit(self, data: pd.DataFrame) -> UnifiedDataPipeline:
        """
        拟合管道参数

        参数：
            data: 输入数据

        返回：
            self
        """

    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        转换数据

        参数：
            data: 输入数据

        返回：
            处理后的数据
        """

    def fit_transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        拟合并转换数据
        """
```

### 7. 常见问题

#### 7.1 如何避免前视偏差？

使用专门的预测模式处理器：

```python
# 正确做法
handler = HikyuuAlphaHandler.create_for_prediction(...)

# 错误做法（可能导致前视偏差）
handler = HikyuuAlphaHandler(..., mode="train")  # 在预测时使用训练模式
```

#### 7.2 数据缺失如何处理？

使用数据管道自动处理：

```python
config = DataPipelineConfig(
    fill_method="forward",  # 前向填充
    max_nan_ratio=0.1       # 最大缺失率 10%
)
pipeline = UnifiedDataPipeline(config)
clean_data = pipeline.fit_transform(raw_data)
```

#### 7.3 如何优化回测性能？

```python
# 1. 使用缓存
config.use_cache = True

# 2. 减少数据频率
loader = HikyuuDataLoader(freq="week")  # 使用周数据而非日数据

# 3. 并行处理
from joblib import Parallel, delayed
results = Parallel(n_jobs=-1)(
    delayed(backtest)(strategy, data) for strategy in strategies
)
```

#### 7.4 如何处理大规模数据？

```python
# 1. 分批处理
chunk_size = 100
for chunk in pd.read_csv("large_file.csv", chunksize=chunk_size):
    process(chunk)

# 2. 使用数据类型优化
data = optimize_dtypes(data)  # 自动优化数据类型

# 3. 使用增量更新
pipeline.update(new_data)  # 仅更新新数据
```

### 8. 最佳实践

#### 8.1 项目结构

```
qlib-project/
├── config/              # 配置文件
│   ├── hikyuu.ini
│   └── qlib.yaml
├── data/               # 数据目录
│   ├── raw/
│   └── processed/
├── strategies/         # 策略代码
│   ├── momentum.py
│   └── mean_reversion.py
├── models/            # 模型代码
│   ├── lgb_model.py
│   └── deep_model.py
├── utils/             # 工具函数
│   ├── data_pipeline.py
│   └── error_handling.py
├── tests/             # 测试代码
│   └── test_strategy.py
└── notebooks/         # Jupyter notebooks
    └── research.ipynb
```

#### 8.2 代码规范

1. **使用类型注解**
```python
def load_data(instruments: List[str],
              start_time: str,
              end_time: str) -> pd.DataFrame:
    """加载数据"""
```

2. **添加文档字符串**
```python
def calculate_sharpe_ratio(returns: pd.Series) -> float:
    """
    计算夏普比率

    参数：
        returns: 收益率序列

    返回：
        夏普比率
    """
```

3. **错误处理**
```python
try:
    data = loader.load(instruments, start_time, end_time)
except DataLoadError as e:
    logger.error(f"数据加载失败: {e}")
    data = load_from_cache()
```

#### 8.3 测试建议

1. **单元测试**
```python
def test_no_lookahead_bias():
    """测试无前视偏差"""
    handler = HikyuuAlphaHandler.create_for_prediction(...)
    assert handler.data_loader.mode == "predict"
```

2. **集成测试**
```python
def test_end_to_end():
    """端到端测试"""
    # 加载数据
    data = loader.load(...)

    # 处理数据
    processed = pipeline.transform(data)

    # 运行策略
    results = backtest(strategy, processed)

    # 验证结果
    assert results.total_return > 0
```

### 9. 故障排除

#### 问题：ImportError: No module named 'hikyuu'
**解决方案**：
```bash
pip install hikyuu
```

#### 问题：数据加载失败
**解决方案**：
1. 检查 Hikyuu 配置文件
2. 验证数据库连接
3. 确认数据已下载

#### 问题：内存不足
**解决方案**：
1. 减少加载的股票数量
2. 使用更低的数据频率
3. 启用数据压缩

#### 问题：回测结果异常
**解决方案**：
1. 检查前视偏差
2. 验证手续费设置
3. 确认 T+N 延迟配置

### 10. 更多资源

- **GitHub 仓库**：https://github.com/luannanxian/qlib_hikyuu
- **Qlib 文档**：https://qlib.readthedocs.io/
- **Hikyuu 文档**：https://hikyuu.readthedocs.io/
- **示例代码**：`examples/` 目录
- **技术支持**：提交 Issue 到 GitHub

---

更新日期：2025-10-18
版本：1.0.0