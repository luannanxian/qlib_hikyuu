# Qlib-Hikyuu 详细设计文档

## 1. 模块设计详述

### 1.1 数据加载模块 (hikyuu_integration.py)

#### 1.1.1 HikyuuDataLoader 类

**设计目的**：提供 Hikyuu 和 Qlib 之间的数据桥接

**类设计**：
```python
@dataclass
class HikyuuDataLoader:
    """Hikyuu 数据加载器"""

    # 字段定义
    fields: Sequence[str]           # 数据字段列表
    freq: str = "day"               # 数据频率
    label_shift: int = 1            # 标签偏移量
    mode: str = "train"             # 运行模式

    # 核心方法
    def load(self, instruments, start_time, end_time) -> pd.DataFrame:
        """加载数据主方法"""

    def _get_hikyuu_stock(self, code: str):
        """获取 Hikyuu 股票对象"""

    def _convert_to_qlib_format(self, kdata) -> pd.DataFrame:
        """转换数据格式"""
```

**关键设计决策**：
1. **模式分离**：train 模式生成标签，predict 模式不生成
2. **缓存机制**：使用 functools.lru_cache 缓存股票对象
3. **数据格式**：MultiIndex DataFrame (datetime, instrument)

#### 1.1.2 HikyuuAlphaHandler 类

**设计目的**：提供 Qlib 兼容的 Alpha 因子处理器

**接口设计**：
```python
class HikyuuAlphaHandler(DataHandlerLP):
    """Alpha 因子处理器"""

    # 工厂方法
    @classmethod
    def create_for_training(cls, **kwargs):
        """创建训练模式实例"""

    @classmethod
    def create_for_prediction(cls, **kwargs):
        """创建预测模式实例"""

    # 配置方法
    def __init__(self, mode="train", **kwargs):
        # 根据模式配置处理器
        if mode == "predict":
            learn_processors = []  # 预测模式不处理标签
        else:
            learn_processors = default_learn_processors
```

**前视偏差防护**：
- 预测模式下 `learn_processors = []`
- 标签生成仅在训练模式
- 严格的时间窗口管理

### 1.2 错误处理模块 (utils/error_handling.py)

#### 1.2.1 错误处理器设计

**核心组件**：
```python
class ErrorHandler:
    """统一错误处理器"""

    def __init__(self):
        self.errors = []
        self.recovery_strategies = {}

    def log_error(self, error: Exception):
        """记录错误"""

    def register_recovery_strategy(self,
                                  error_type: Type[Exception],
                                  strategy: Callable):
        """注册恢复策略"""

    def handle_error(self, error: Exception):
        """处理错误并尝试恢复"""
```

**重试机制**：
```python
@dataclass
class RetryConfig:
    max_attempts: int = 3
    initial_delay: float = 1.0
    exponential_backoff: bool = True
    max_delay: float = 60.0

def with_retry(config: RetryConfig):
    """重试装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(config.max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == config.max_attempts - 1:
                        raise
                    delay = calculate_delay(config, attempt)
                    time.sleep(delay)
```

**自定义异常层次**：
```python
class QlibHikyuuError(Exception):
    """基础异常类"""

class DataLoadError(QlibHikyuuError):
    """数据加载错误"""

class ValidationError(QlibHikyuuError):
    """数据验证错误"""

class BacktestError(QlibHikyuuError):
    """回测错误"""
```

### 1.3 数据管道模块 (utils/data_pipeline.py)

#### 1.3.1 管道架构

**处理器链设计**：
```python
class UnifiedDataPipeline:
    """统一数据处理管道"""

    def __init__(self, config: DataProcessConfig):
        self.processors = []
        self._setup_processors()

    def _setup_processors(self):
        """设置处理器链"""
        # 1. 数据验证
        self.processors.append(DataValidator(...))

        # 2. 异常值处理
        if config.remove_outliers:
            self.processors.append(OutlierRemover(...))

        # 3. 缺失值填充
        self.processors.append(MissingValueImputer(...))

        # 4. 特征工程
        if config.add_technical_indicators:
            self.processors.append(TechnicalIndicatorGenerator(...))

        # 5. 滞后特征
        if config.lag_periods:
            self.processors.append(LagFeatureGenerator(...))
            self.processors.append(MissingValueImputer(...))  # 再次填充

        # 6. 最终验证
        self.processors.append(DataValidator(...))
```

**处理器接口**：
```python
class DataProcessor(ABC):
    """数据处理器基类"""

    @abstractmethod
    def fit(self, data: pd.DataFrame) -> DataProcessor:
        """拟合处理器参数"""

    @abstractmethod
    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """转换数据"""

    def fit_transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """拟合并转换"""
        return self.fit(data).transform(data)
```

#### 1.3.2 特征工程设计

**技术指标生成器**：
```python
class TechnicalIndicatorGenerator(DataProcessor):
    """技术指标生成器"""

    indicators = {
        "MA": moving_average,
        "RSI": relative_strength_index,
        "MACD": macd,
        "BOLL": bollinger_bands,
        "ROC": rate_of_change
    }

    def transform(self, data):
        for indicator_name, calculator in self.indicators.items():
            data[indicator_name] = calculator(data)
        return data
```

**滞后特征生成器**：
```python
class LagFeatureGenerator(DataProcessor):
    """滞后特征生成器"""

    def transform(self, data):
        lag_periods = [1, 5, 10, 20]
        for col in important_columns:
            for lag in lag_periods:
                data[f"{col}_lag_{lag}"] = data[col].shift(lag)
        return data
```

### 1.4 回测引擎模块

#### 1.4.1 回测配置

```python
@dataclass
class BacktestConfig:
    """回测配置"""

    # 时间设置
    start_date: str
    end_date: str

    # 执行设置
    t_plus_n: int = 1              # T+N 延迟
    execution_price: str = "close"  # 执行价格

    # 费用设置
    commission_rate: float = 0.0003 # 手续费率
    slippage: float = 0.001         # 滑点
    stamp_tax: float = 0.001        # 印花税

    # 风控设置
    max_position: float = 0.95      # 最大仓位
    stop_loss: float = 0.08         # 止损线
```

#### 1.4.2 回测引擎

```python
class BacktestEngine:
    """回测引擎"""

    def __init__(self, config: BacktestConfig):
        self.config = config
        self.portfolio = Portfolio()
        self.trades = []

    def run(self, strategy, data):
        """运行回测"""
        for date in trading_dates:
            # 获取信号
            signals = strategy.generate_signals(data, date)

            # T+N 延迟执行
            if self.pending_orders:
                self.execute_pending_orders(date)

            # 生成新订单
            orders = self.generate_orders(signals)
            self.pending_orders.append((date, orders))

            # 更新组合
            self.portfolio.update(date, data)
```

### 1.5 监控系统模块

#### 1.5.1 监控配置

```python
@dataclass
class MonitoringConfig:
    """监控配置"""

    # 监控级别
    enable_system_monitoring: bool = True
    enable_data_monitoring: bool = True
    enable_model_monitoring: bool = True

    # 告警设置
    alert_levels: List[str] = ["CRITICAL", "ERROR", "WARNING"]
    alert_channels: List[str] = ["log", "email", "webhook"]

    # 指标设置
    metrics_interval: int = 60  # 秒
    metrics_retention: int = 7  # 天
```

#### 1.5.2 监控系统

```python
class MonitoringSystem:
    """监控系统"""

    def __init__(self, config: MonitoringConfig):
        self.config = config
        self.metrics_collector = MetricsCollector()
        self.alert_manager = AlertManager()

    def start(self):
        """启动监控"""
        # 启动指标收集
        self.metrics_collector.start()

        # 启动告警管理
        self.alert_manager.start()

    def check_system_health(self):
        """检查系统健康状态"""
        metrics = {
            "cpu_usage": psutil.cpu_percent(),
            "memory_usage": psutil.virtual_memory().percent,
            "disk_usage": psutil.disk_usage('/').percent
        }

        for metric, value in metrics.items():
            if value > self.thresholds[metric]:
                self.alert_manager.send_alert(
                    level="WARNING",
                    message=f"{metric} exceeded threshold: {value}%"
                )
```

### 1.6 报告生成模块

#### 1.6.1 报告配置

```python
@dataclass
class ReportConfig:
    """报告配置"""

    # 报告类型
    report_types: List[str] = ["summary", "detailed", "risk"]

    # 输出格式
    output_formats: List[str] = ["html", "pdf", "markdown"]

    # 图表设置
    include_charts: bool = True
    chart_types: List[str] = ["pnl", "drawdown", "returns"]
```

#### 1.6.2 报告生成器

```python
class ReportGenerator:
    """报告生成器"""

    def __init__(self, config: ReportConfig):
        self.config = config
        self.chart_generator = ChartGenerator()

    def generate(self, backtest_results):
        """生成报告"""
        report = {
            "summary": self._generate_summary(backtest_results),
            "metrics": self._calculate_metrics(backtest_results),
            "charts": self._generate_charts(backtest_results)
        }

        return self._format_report(report)

    def _calculate_metrics(self, results):
        """计算指标"""
        return {
            "total_return": calculate_total_return(results),
            "sharpe_ratio": calculate_sharpe_ratio(results),
            "max_drawdown": calculate_max_drawdown(results),
            "win_rate": calculate_win_rate(results)
        }
```

## 2. 接口设计

### 2.1 数据接口

```python
# 数据加载接口
def load_data(instruments: List[str],
              start_time: str,
              end_time: str,
              freq: str = "day") -> pd.DataFrame:
    """加载市场数据"""

# 特征工程接口
def create_features(data: pd.DataFrame,
                   config: FeatureConfig) -> pd.DataFrame:
    """创建特征"""

# 标签生成接口
def create_labels(data: pd.DataFrame,
                 method: str = "return") -> pd.DataFrame:
    """生成标签"""
```

### 2.2 模型接口

```python
# 模型训练接口
def train_model(X_train: pd.DataFrame,
                y_train: pd.Series,
                model_config: ModelConfig) -> Model:
    """训练模型"""

# 模型预测接口
def predict(model: Model,
           X_test: pd.DataFrame) -> pd.Series:
    """模型预测"""
```

### 2.3 策略接口

```python
class Strategy(ABC):
    """策略基类"""

    @abstractmethod
    def generate_signals(self,
                        data: pd.DataFrame,
                        date: pd.Timestamp) -> pd.Series:
        """生成交易信号"""

    @abstractmethod
    def calculate_position(self,
                          signals: pd.Series,
                          portfolio: Portfolio) -> pd.Series:
        """计算持仓"""
```

## 3. 数据结构设计

### 3.1 核心数据结构

```python
# 市场数据结构
MarketData = pd.DataFrame  # MultiIndex: (datetime, instrument)

# 交易信号结构
Signal = pd.Series  # Index: instrument, Values: [-1, 0, 1]

# 持仓结构
Position = Dict[str, float]  # {instrument: weight}

# 订单结构
@dataclass
class Order:
    instrument: str
    direction: str  # "buy" or "sell"
    quantity: int
    price: float
    timestamp: pd.Timestamp
```

### 3.2 配置结构

```python
# 全局配置
@dataclass
class GlobalConfig:
    data_config: DataConfig
    model_config: ModelConfig
    backtest_config: BacktestConfig
    monitor_config: MonitoringConfig
    report_config: ReportConfig
```

## 4. 算法设计

### 4.1 前视偏差检测算法

```python
def detect_lookahead_bias(data: pd.DataFrame,
                         features: pd.DataFrame,
                         labels: pd.Series) -> bool:
    """
    检测前视偏差

    算法：
    1. 对每个时间点 t
    2. 检查特征是否使用了 t+1 之后的数据
    3. 检查标签是否正确对齐
    """
    for t in data.index.get_level_values(0).unique():
        # 获取 t 时刻的特征
        features_t = features.loc[t]

        # 检查特征时间戳
        if any(feature_contains_future_data(features_t, t)):
            return True

        # 检查标签对齐
        if labels.loc[t] uses data after t:
            return True

    return False
```

### 4.2 异常值检测算法

```python
def detect_outliers(data: pd.Series,
                   method: str = "iqr") -> pd.Series:
    """
    异常值检测

    支持方法：
    - IQR: 四分位距方法
    - Z-Score: 标准差方法
    - Isolation Forest: 孤立森林
    """
    if method == "iqr":
        Q1 = data.quantile(0.25)
        Q3 = data.quantile(0.75)
        IQR = Q3 - Q1
        lower = Q1 - 1.5 * IQR
        upper = Q3 + 1.5 * IQR
        return (data < lower) | (data > upper)

    elif method == "zscore":
        z_scores = np.abs((data - data.mean()) / data.std())
        return z_scores > 3
```

## 5. 性能考虑

### 5.1 内存优化

```python
# 数据类型优化
def optimize_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """优化数据类型以减少内存使用"""
    for col in df.columns:
        col_type = df[col].dtype

        if col_type != 'object':
            c_min = df[col].min()
            c_max = df[col].max()

            if str(col_type)[:3] == 'int':
                if c_min > np.iinfo(np.int8).min and \
                   c_max < np.iinfo(np.int8).max:
                    df[col] = df[col].astype(np.int8)
                # ... 其他整数类型

            else:  # float
                if c_min > np.finfo(np.float16).min and \
                   c_max < np.finfo(np.float16).max:
                    df[col] = df[col].astype(np.float16)
                # ... 其他浮点类型

    return df
```

### 5.2 计算优化

```python
# 向量化操作
def calculate_returns_vectorized(prices: pd.DataFrame) -> pd.DataFrame:
    """向量化计算收益率"""
    return prices.pct_change()

# 并行处理
from joblib import Parallel, delayed

def parallel_feature_calculation(data: pd.DataFrame,
                                feature_funcs: List[Callable]) -> pd.DataFrame:
    """并行计算特征"""
    results = Parallel(n_jobs=-1)(
        delayed(func)(data) for func in feature_funcs
    )
    return pd.concat(results, axis=1)
```

## 6. 安全性考虑

### 6.1 数据验证

```python
def validate_data(data: pd.DataFrame) -> bool:
    """
    数据验证

    检查项：
    1. 数据完整性
    2. 数据一致性
    3. 数据时效性
    """
    # 完整性检查
    if data.isna().sum().sum() > len(data) * 0.1:
        raise ValidationError("Too many missing values")

    # 一致性检查
    if not data.index.is_monotonic_increasing:
        raise ValidationError("Time index not monotonic")

    # 时效性检查
    latest_date = data.index.get_level_values(0).max()
    if latest_date < pd.Timestamp.now() - pd.Timedelta(days=2):
        raise ValidationError("Data is stale")

    return True
```

### 6.2 权限控制

```python
class PermissionManager:
    """权限管理器"""

    def __init__(self):
        self.permissions = {
            "read_data": ["user", "admin"],
            "write_data": ["admin"],
            "execute_trade": ["trader", "admin"],
            "modify_config": ["admin"]
        }

    def check_permission(self, user_role: str, action: str) -> bool:
        """检查权限"""
        return user_role in self.permissions.get(action, [])
```

---

更新日期：2025-10-18
版本：1.0.0