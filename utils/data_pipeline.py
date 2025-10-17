#!/usr/bin/env python3
"""
统一数据处理流水线

提供标准化的数据处理流程，包括：
- 数据清洗
- 特征工程
- 数据验证
- 缓存管理
"""

from __future__ import annotations

import hashlib
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ============================================================================
# 数据处理配置
# ============================================================================

@dataclass
class DataProcessConfig:
    """数据处理配置"""
    # 数据清洗
    remove_outliers: bool = True
    outlier_method: str = "iqr"  # iqr, zscore, isolation_forest
    outlier_threshold: float = 3.0
    fill_method: str = "forward"  # forward, backward, interpolate, mean, median

    # 特征工程
    add_technical_indicators: bool = True
    add_market_features: bool = True
    lag_periods: List[int] = field(default_factory=lambda: [1, 5, 10, 20])
    rolling_windows: List[int] = field(default_factory=lambda: [5, 10, 20, 60])

    # 数据验证
    check_monotonic_time: bool = True
    check_duplicates: bool = True
    max_nan_ratio: float = 0.1

    # 缓存
    use_cache: bool = True
    cache_dir: Path = Path(".data_cache")
    cache_ttl: int = 3600 * 24  # 24小时


# ============================================================================
# 数据处理步骤基类
# ============================================================================

class DataProcessor(ABC):
    """数据处理器基类"""

    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        self.name = name
        self.config = config or {}
        self._fitted = False
        self._fit_params = {}

    @abstractmethod
    def fit(self, data: pd.DataFrame) -> DataProcessor:
        """拟合处理器参数"""
        pass

    @abstractmethod
    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """转换数据"""
        pass

    def fit_transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """拟合并转换"""
        return self.fit(data).transform(data)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}')"


# ============================================================================
# 数据清洗处理器
# ============================================================================

class OutlierRemover(DataProcessor):
    """异常值移除器"""

    def fit(self, data: pd.DataFrame) -> DataProcessor:
        """计算异常值阈值"""
        self._fit_params = {}

        method = self.config.get("method", "iqr")
        threshold = self.config.get("threshold", 3.0)

        numeric_cols = data.select_dtypes(include=[np.number]).columns

        if method == "iqr":
            # IQR方法
            for col in numeric_cols:
                Q1 = data[col].quantile(0.25)
                Q3 = data[col].quantile(0.75)
                IQR = Q3 - Q1
                self._fit_params[col] = {
                    "lower": Q1 - threshold * IQR,
                    "upper": Q3 + threshold * IQR
                }
        elif method == "zscore":
            # Z-score方法
            for col in numeric_cols:
                mean = data[col].mean()
                std = data[col].std()
                self._fit_params[col] = {
                    "mean": mean,
                    "std": std,
                    "threshold": threshold
                }

        self._fitted = True
        return self

    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """移除异常值"""
        if not self._fitted:
            raise ValueError(f"{self.name} 未拟合")

        data = data.copy()
        method = self.config.get("method", "iqr")

        for col, params in self._fit_params.items():
            if col not in data.columns:
                continue

            if method == "iqr":
                mask = (data[col] < params["lower"]) | (data[col] > params["upper"])
                data.loc[mask, col] = np.nan
            elif method == "zscore":
                z_scores = np.abs((data[col] - params["mean"]) / params["std"])
                mask = z_scores > params["threshold"]
                data.loc[mask, col] = np.nan

        logger.info(f"{self.name}: 移除了 {data.isna().sum().sum()} 个异常值")
        return data


class MissingValueImputer(DataProcessor):
    """缺失值填充器"""

    def fit(self, data: pd.DataFrame) -> DataProcessor:
        """计算填充值"""
        self._fit_params = {}

        method = self.config.get("method", "forward")
        numeric_cols = data.select_dtypes(include=[np.number]).columns

        if method in ["mean", "median"]:
            for col in numeric_cols:
                if method == "mean":
                    self._fit_params[col] = data[col].mean()
                else:
                    self._fit_params[col] = data[col].median()

        self._fitted = True
        return self

    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """填充缺失值"""
        data = data.copy()
        method = self.config.get("method", "forward")

        if method == "forward":
            data = data.fillna(method="ffill")
        elif method == "backward":
            data = data.fillna(method="bfill")
        elif method == "interpolate":
            data = data.interpolate(method="linear")
        elif method in ["mean", "median"]:
            for col, value in self._fit_params.items():
                if col in data.columns:
                    data[col] = data[col].fillna(value)

        # 对于仍然存在的 NaN，使用 0 填充
        remaining_nan = data.isna().sum().sum()
        if remaining_nan > 0:
            logger.warning(f"{self.name}: 仍有 {remaining_nan} 个缺失值，使用 0 填充")
            data = data.fillna(0)

        return data


# ============================================================================
# 特征工程处理器
# ============================================================================

class TechnicalIndicatorGenerator(DataProcessor):
    """技术指标生成器"""

    def fit(self, data: pd.DataFrame) -> DataProcessor:
        """不需要拟合"""
        self._fitted = True
        return self

    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """生成技术指标"""
        data = data.copy()

        # 确保有价格列
        price_cols = ["open", "high", "low", "close", "volume"]
        available_cols = [col for col in price_cols if col in data.columns or ("feature", col.upper()) in data.columns]

        if not available_cols:
            logger.warning(f"{self.name}: 没有找到价格列，跳过技术指标生成")
            return data

        # 处理 MultiIndex columns
        if data.columns.nlevels == 2:
            # 提取价格数据
            price_data = {}
            for col in price_cols:
                if ("feature", col.upper()) in data.columns:
                    price_data[col] = data[("feature", col.upper())]
        else:
            price_data = {col: data[col] for col in available_cols}

        # 计算技术指标
        indicators = {}

        # MA (移动平均)
        for window in self.config.get("ma_windows", [5, 10, 20]):
            if "close" in price_data:
                indicators[f"MA_{window}"] = price_data["close"].rolling(window).mean()

        # RSI (相对强弱指标)
        if "close" in price_data:
            close_diff = price_data["close"].diff()
            gain = close_diff.where(close_diff > 0, 0).rolling(14).mean()
            loss = -close_diff.where(close_diff < 0, 0).rolling(14).mean()
            rs = gain / loss.replace(0, np.nan)
            indicators["RSI"] = 100 - (100 / (1 + rs))

        # MACD
        if "close" in price_data:
            exp1 = price_data["close"].ewm(span=12).mean()
            exp2 = price_data["close"].ewm(span=26).mean()
            indicators["MACD"] = exp1 - exp2
            indicators["MACD_signal"] = indicators["MACD"].ewm(span=9).mean()

        # 成交量指标
        if "volume" in price_data:
            indicators["volume_MA_10"] = price_data["volume"].rolling(10).mean()
            indicators["volume_ratio"] = price_data["volume"] / indicators["volume_MA_10"]

        # 添加到数据中
        if data.columns.nlevels == 2:
            # MultiIndex columns
            for name, values in indicators.items():
                data[("feature", name)] = values
        else:
            for name, values in indicators.items():
                data[name] = values

        logger.info(f"{self.name}: 生成了 {len(indicators)} 个技术指标")
        return data


class LagFeatureGenerator(DataProcessor):
    """滞后特征生成器"""

    def fit(self, data: pd.DataFrame) -> DataProcessor:
        """不需要拟合"""
        self._fitted = True
        return self

    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """生成滞后特征"""
        data = data.copy()
        lag_periods = self.config.get("lag_periods", [1, 5, 10])

        # 获取要生成滞后的列
        if data.columns.nlevels == 2:
            # MultiIndex columns
            feature_cols = [col for col in data.columns if col[0] == "feature"]
            # 只对部分重要特征生成滞后
            important_features = ["CLOSE", "VOLUME", "RSI", "MACD"]
            target_cols = [col for col in feature_cols if any(f in col[1] for f in important_features)]
        else:
            target_cols = data.select_dtypes(include=[np.number]).columns[:5]  # 只选前5列

        new_features = {}
        for col in target_cols:
            for lag in lag_periods:
                if data.columns.nlevels == 2:
                    lag_name = f"{col[1]}_lag_{lag}"
                    new_features[("feature", lag_name)] = data[col].shift(lag)
                else:
                    lag_name = f"{col}_lag_{lag}"
                    new_features[lag_name] = data[col].shift(lag)

        # 添加新特征
        for name, values in new_features.items():
            data[name] = values

        logger.info(f"{self.name}: 生成了 {len(new_features)} 个滞后特征")
        return data


# ============================================================================
# 数据验证处理器
# ============================================================================

class DataValidator(DataProcessor):
    """数据验证器"""

    def fit(self, data: pd.DataFrame) -> DataProcessor:
        """不需要拟合"""
        self._fitted = True
        return self

    def transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """验证数据"""
        issues = []

        # 检查时间序列单调性
        if self.config.get("check_monotonic_time", True):
            if data.index.nlevels >= 1:
                time_index = data.index.get_level_values(0) if data.index.nlevels > 1 else data.index
                if not time_index.is_monotonic_increasing:
                    issues.append("时间索引非单调递增")
                    # 自动修复
                    data = data.sort_index()

        # 检查重复
        if self.config.get("check_duplicates", True):
            duplicates = data.index.duplicated()
            if duplicates.any():
                n_dup = duplicates.sum()
                issues.append(f"发现 {n_dup} 个重复索引")
                # 自动去重
                data = data[~duplicates]

        # 检查缺失值比例
        max_nan_ratio = self.config.get("max_nan_ratio", 0.1)
        nan_ratio = data.isna().sum().sum() / data.size
        if nan_ratio > max_nan_ratio:
            issues.append(f"缺失值比例 {nan_ratio:.1%} 超过阈值 {max_nan_ratio:.1%}")

        # 记录问题
        if issues:
            logger.warning(f"{self.name} 发现问题: {', '.join(issues)}")
        else:
            logger.info(f"{self.name}: 数据验证通过")

        return data


# ============================================================================
# 统一数据处理流水线
# ============================================================================

class UnifiedDataPipeline:
    """统一的数据处理流水线"""

    def __init__(self, config: Optional[DataProcessConfig] = None):
        self.config = config or DataProcessConfig()
        self.processors: List[DataProcessor] = []
        self._setup_processors()
        self._cache = {}

    def _setup_processors(self):
        """设置处理器"""
        # 数据验证（第一步）
        self.processors.append(
            DataValidator("初始验证", {
                "check_monotonic_time": self.config.check_monotonic_time,
                "check_duplicates": self.config.check_duplicates,
            })
        )

        # 异常值处理
        if self.config.remove_outliers:
            self.processors.append(
                OutlierRemover("异常值移除", {
                    "method": self.config.outlier_method,
                    "threshold": self.config.outlier_threshold,
                })
            )

        # 缺失值填充
        self.processors.append(
            MissingValueImputer("缺失值填充", {
                "method": self.config.fill_method,
            })
        )

        # 技术指标
        if self.config.add_technical_indicators:
            self.processors.append(
                TechnicalIndicatorGenerator("技术指标", {
                    "ma_windows": self.config.rolling_windows,
                })
            )

        # 滞后特征
        if self.config.lag_periods:
            self.processors.append(
                LagFeatureGenerator("滞后特征", {
                    "lag_periods": self.config.lag_periods,
                })
            )

        # 最终验证
        self.processors.append(
            DataValidator("最终验证", {
                "max_nan_ratio": self.config.max_nan_ratio,
            })
        )

    def fit(self, data: pd.DataFrame) -> UnifiedDataPipeline:
        """拟合所有处理器"""
        logger.info("开始拟合数据处理流水线...")

        current_data = data.copy()
        for processor in self.processors:
            logger.debug(f"拟合 {processor.name}")
            processor.fit(current_data)
            # 某些处理器可能会改变数据，用于下一个处理器的拟合
            current_data = processor.transform(current_data)

        logger.info("数据处理流水线拟合完成")
        return self

    def transform(self, data: pd.DataFrame, use_cache: bool = True) -> pd.DataFrame:
        """应用所有处理器"""
        # 生成缓存键
        cache_key = self._generate_cache_key(data)

        # 尝试从缓存获取
        if use_cache and self.config.use_cache and cache_key in self._cache:
            logger.info("从缓存返回处理后的数据")
            return self._cache[cache_key]

        logger.info("开始数据处理流水线...")

        current_data = data.copy()
        for processor in self.processors:
            logger.debug(f"应用 {processor.name}")
            current_data = processor.transform(current_data)

        # 缓存结果
        if use_cache and self.config.use_cache:
            self._cache[cache_key] = current_data
            # 保存到磁盘缓存
            self._save_cache(cache_key, current_data)

        logger.info(f"数据处理完成: {data.shape} -> {current_data.shape}")
        return current_data

    def fit_transform(self, data: pd.DataFrame) -> pd.DataFrame:
        """拟合并转换"""
        return self.fit(data).transform(data)

    def _generate_cache_key(self, data: pd.DataFrame) -> str:
        """生成缓存键"""
        # 基于数据形状和索引生成键
        key_parts = [
            str(data.shape),
            str(data.index.names),
            str(data.columns.tolist()[:5]),  # 只用前5列
        ]
        key_str = "_".join(key_parts)
        return hashlib.md5(key_str.encode()).hexdigest()

    def _save_cache(self, key: str, data: pd.DataFrame):
        """保存缓存到磁盘"""
        if not self.config.cache_dir.exists():
            self.config.cache_dir.mkdir(parents=True)

        cache_file = self.config.cache_dir / f"{key}.pkl"
        try:
            data.to_pickle(cache_file)
            logger.debug(f"缓存已保存: {cache_file}")
        except Exception as e:
            logger.warning(f"保存缓存失败: {e}")

    def add_processor(self, processor: DataProcessor, position: Optional[int] = None):
        """添加自定义处理器"""
        if position is None:
            self.processors.append(processor)
        else:
            self.processors.insert(position, processor)
        logger.info(f"添加处理器: {processor.name}")

    def remove_processor(self, name: str):
        """移除处理器"""
        self.processors = [p for p in self.processors if p.name != name]
        logger.info(f"移除处理器: {name}")

    def get_processor_names(self) -> List[str]:
        """获取所有处理器名称"""
        return [p.name for p in self.processors]


# ============================================================================
# 便捷函数
# ============================================================================

def create_default_pipeline() -> UnifiedDataPipeline:
    """创建默认的数据处理流水线"""
    config = DataProcessConfig(
        remove_outliers=True,
        outlier_method="iqr",
        fill_method="forward",
        add_technical_indicators=True,
        lag_periods=[1, 5, 10],
        use_cache=True
    )
    return UnifiedDataPipeline(config)


def create_minimal_pipeline() -> UnifiedDataPipeline:
    """创建最小的数据处理流水线（只做必要的清洗）"""
    config = DataProcessConfig(
        remove_outliers=False,
        add_technical_indicators=False,
        lag_periods=[],
        use_cache=False
    )
    return UnifiedDataPipeline(config)


# ============================================================================
# 使用示例
# ============================================================================

if __name__ == "__main__":
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # 创建示例数据
    dates = pd.date_range("2023-01-01", periods=100)
    instruments = ["SH600000", "SH600001"]

    data = []
    for date in dates:
        for inst in instruments:
            data.append({
                "datetime": date,
                "instrument": inst,
                "open": np.random.uniform(10, 11),
                "high": np.random.uniform(11, 12),
                "low": np.random.uniform(9, 10),
                "close": np.random.uniform(10, 11),
                "volume": np.random.uniform(1e6, 2e6)
            })

    df = pd.DataFrame(data)
    df = df.set_index(["datetime", "instrument"])

    # 添加一些异常值和缺失值
    df.iloc[10:15, 0] = np.nan  # 缺失值
    df.iloc[20, 1] = 100  # 异常值

    print("原始数据:")
    print(df.head())
    print(f"形状: {df.shape}")
    print(f"缺失值: {df.isna().sum().sum()}")

    # 创建并应用流水线
    pipeline = create_default_pipeline()

    # 拟合和转换
    processed_df = pipeline.fit_transform(df)

    print("\n处理后数据:")
    print(processed_df.head())
    print(f"形状: {processed_df.shape}")
    print(f"缺失值: {processed_df.isna().sum().sum()}")
    print(f"新增列数: {len(processed_df.columns) - len(df.columns)}")

    # 显示处理器
    print("\n使用的处理器:")
    for name in pipeline.get_processor_names():
        print(f"  - {name}")