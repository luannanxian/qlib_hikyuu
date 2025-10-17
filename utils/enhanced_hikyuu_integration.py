#!/usr/bin/env python3
"""
增强版 Hikyuu 集成补丁
- 集成了错误处理机制
- 添加了数据验证
- 实现了重试机制
"""

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from utils.error_handling import (
    with_error_handling,
    with_retry,
    validate_dataframe,
    DataLoadError,
    ConfigurationError,
    ValidationError,
    RetryConfig,
    ErrorRecovery,
    logger
)
import pandas as pd
from typing import Optional, List, Dict, Any


class EnhancedHikyuuDataLoader:
    """增强版的 Hikyuu 数据加载器"""

    def __init__(self, base_loader):
        """
        包装原始的 HikyuuDataLoader，添加错误处理

        Args:
            base_loader: 原始的 HikyuuDataLoader 实例
        """
        self.base_loader = base_loader
        self.error_recovery = ErrorRecovery()
        self._error_count = 0
        self._max_errors = 10

    @with_error_handling(
        default_return=pd.DataFrame(),
        raise_on_error=False,
        category=ErrorCategory.DATA
    )
    @validate_dataframe(
        check_empty=False,  # 允许空数据，但会记录警告
        check_columns=None,  # 动态检查
        check_index="MultiIndex"
    )
    def load(
        self,
        instruments: List[str],
        start_time: Optional[str],
        end_time: Optional[str],
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        加载数据，带错误处理和缓存

        Args:
            instruments: 股票代码列表
            start_time: 开始时间
            end_time: 结束时间
            use_cache: 是否使用缓存

        Returns:
            加载的数据 DataFrame
        """
        # 生成缓存键
        cache_key = f"data_{'-'.join(instruments)}_{start_time}_{end_time}"

        # 尝试从缓存加载
        if use_cache:
            cached_data = self.error_recovery.load_checkpoint(cache_key)
            if cached_data is not None:
                logger.info(f"从缓存加载数据: {cache_key}")
                return cached_data

        # 验证输入参数
        self._validate_inputs(instruments, start_time, end_time)

        # 加载数据，带重试
        data = self._load_with_retry(instruments, start_time, end_time)

        # 验证输出数据
        data = self._validate_output(data)

        # 保存到缓存
        if use_cache and not data.empty:
            self.error_recovery.save_checkpoint(cache_key, data)

        return data

    def _validate_inputs(
        self,
        instruments: List[str],
        start_time: Optional[str],
        end_time: Optional[str]
    ):
        """验证输入参数"""
        if not instruments:
            raise ValidationError("股票列表不能为空")

        if start_time and end_time:
            try:
                start_dt = pd.Timestamp(start_time)
                end_dt = pd.Timestamp(end_time)
                if start_dt >= end_dt:
                    raise ValidationError(
                        f"开始时间 {start_time} 必须早于结束时间 {end_time}"
                    )
            except Exception as e:
                raise ValidationError(f"时间格式错误: {e}")

        # 验证股票代码格式
        for inst in instruments:
            if not self._is_valid_instrument(inst):
                raise ValidationError(f"无效的股票代码: {inst}")

    def _is_valid_instrument(self, instrument: str) -> bool:
        """验证股票代码格式"""
        # 简单验证：应该是 2个字母 + 6个数字
        if len(instrument) != 8:
            return False
        prefix = instrument[:2].upper()
        code = instrument[2:]
        return prefix in ["SH", "SZ", "BJ"] and code.isdigit()

    @with_retry(
        config=RetryConfig(
            max_attempts=3,
            delay=2.0,
            exceptions=(DataLoadError, ConnectionError)
        )
    )
    def _load_with_retry(
        self,
        instruments: List[str],
        start_time: Optional[str],
        end_time: Optional[str]
    ) -> pd.DataFrame:
        """带重试的数据加载"""
        try:
            # 调用原始加载器
            data = self.base_loader.load(instruments, start_time, end_time)

            if data is None:
                raise DataLoadError("数据加载返回 None")

            return data

        except Exception as e:
            self._error_count += 1
            if self._error_count >= self._max_errors:
                raise DataLoadError(
                    f"错误次数过多 ({self._error_count})，停止加载",
                    context={"last_error": str(e)}
                )
            raise DataLoadError(f"数据加载失败: {e}")

    def _validate_output(self, data: pd.DataFrame) -> pd.DataFrame:
        """验证输出数据"""
        if data.empty:
            logger.warning("加载的数据为空")
            return data

        # 检查必要的列
        if self.base_loader.mode == "train":
            required_columns = ["open", "high", "low", "close", "volume", "label"]
        else:
            required_columns = ["open", "high", "low", "close", "volume"]

        # 检查MultiIndex的列
        if data.index.nlevels == 2:
            # MultiIndex 格式
            if data.columns.nlevels == 2:
                # 检查 feature 组
                feature_cols = [col[1].lower() for col in data.columns if col[0] == "feature"]
                for req_col in required_columns[:-1]:  # 不检查 label
                    if req_col not in feature_cols:
                        logger.warning(f"缺少特征列: {req_col}")

                # 训练模式检查 label
                if self.base_loader.mode == "train":
                    label_cols = [col for col in data.columns if col[0] == "label"]
                    if not label_cols:
                        raise ValidationError("训练模式缺少标签列")

        # 检查数据质量
        self._check_data_quality(data)

        return data

    def _check_data_quality(self, data: pd.DataFrame):
        """检查数据质量"""
        # 检查 NaN 值
        nan_ratio = data.isna().sum().sum() / data.size
        if nan_ratio > 0.1:  # 超过10% NaN
            logger.warning(f"数据包含 {nan_ratio:.1%} 的缺失值")

        # 检查异常值（价格为负等）
        if data.columns.nlevels == 2:
            price_cols = [col for col in data.columns if col[0] == "feature" and col[1].lower() in ["open", "high", "low", "close"]]
            for col in price_cols:
                if (data[col] < 0).any():
                    raise ValidationError(f"发现负价格: {col}")

        # 检查时间序列连续性
        if data.index.nlevels == 2:
            dates = data.index.get_level_values(0).unique()
            if len(dates) > 1:
                date_diff = pd.Series(dates).diff()
                # 检查是否有大于30天的间隔（可能是数据缺失）
                large_gaps = date_diff[date_diff > pd.Timedelta(days=30)]
                if not large_gaps.empty:
                    logger.warning(f"数据存在大于30天的间隔: {large_gaps}")


def enhance_data_handler(handler_class):
    """
    装饰器：增强 DataHandler 类

    Args:
        handler_class: 原始的 Handler 类

    Returns:
        增强后的 Handler 类
    """
    class EnhancedHandler(handler_class):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # 包装数据加载器
            if hasattr(self, "data_loader"):
                self.data_loader = EnhancedHikyuuDataLoader(self.data_loader)
            logger.info(f"已增强 {handler_class.__name__} 的错误处理能力")

        @with_error_handling(raise_on_error=True)
        def setup_data(self, *args, **kwargs):
            """带错误处理的数据设置"""
            return super().setup_data(*args, **kwargs)

        @with_error_handling(raise_on_error=False)
        def fetch_data(self, *args, **kwargs):
            """带错误处理的数据获取"""
            return super().fetch_data(*args, **kwargs)

    EnhancedHandler.__name__ = f"Enhanced{handler_class.__name__}"
    return EnhancedHandler


# ============================================================================
# 错误处理集成示例
# ============================================================================

def apply_error_handling_patch():
    """应用错误处理补丁到现有模块"""
    try:
        from hikyuu_integration import HikyuuDataLoader, HikyuuAlphaHandler

        # 创建增强版本
        EnhancedHikyuuAlphaHandler = enhance_data_handler(HikyuuAlphaHandler)

        # 替换原始类（可选）
        # sys.modules["hikyuu_integration"].HikyuuAlphaHandler = EnhancedHikyuuAlphaHandler

        logger.info("错误处理补丁已应用")
        return EnhancedHikyuuAlphaHandler

    except ImportError as e:
        logger.error(f"无法导入 hikyuu_integration: {e}")
        return None


if __name__ == "__main__":
    # 设置日志
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # 测试增强功能
    print("测试错误处理增强...")

    # 应用补丁
    EnhancedHandler = apply_error_handling_patch()

    if EnhancedHandler:
        print("创建增强版 Handler...")
        try:
            # 这里会因为缺少真实数据而失败，但错误会被优雅处理
            handler = EnhancedHandler(
                instruments=["SH600000"],
                start_time="2023-01-01",
                end_time="2023-12-31"
            )
            print("Handler 创建成功（带错误处理）")
        except Exception as e:
            print(f"Handler 创建失败（预期的）: {e}")
    else:
        print("无法应用错误处理补丁")