#!/usr/bin/env python3
"""
错误处理和异常管理模块

提供统一的错误处理机制，包括：
- 自定义异常类
- 错误处理装饰器
- 重试机制
- 详细的错误日志
"""

from __future__ import annotations

import functools
import logging
import time
import traceback
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional, Type, TypeVar, Union

import pandas as pd

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ErrorSeverity(Enum):
    """错误严重级别"""
    CRITICAL = "critical"  # 系统无法继续运行
    HIGH = "high"          # 影响核心功能
    MEDIUM = "medium"      # 影响部分功能
    LOW = "low"           # 轻微问题
    INFO = "info"         # 信息提示


class ErrorCategory(Enum):
    """错误分类"""
    DATA = "data"              # 数据相关错误
    CONFIG = "config"          # 配置错误
    NETWORK = "network"        # 网络错误
    CALCULATION = "calc"       # 计算错误
    VALIDATION = "validation"  # 验证错误
    SYSTEM = "system"          # 系统错误
    DEPENDENCY = "dependency"  # 依赖错误


# ============================================================================
# 自定义异常类
# ============================================================================

class QlibHikyuuError(Exception):
    """基础异常类"""

    severity = ErrorSeverity.MEDIUM
    category = ErrorCategory.SYSTEM

    def __init__(
        self,
        message: str,
        severity: Optional[ErrorSeverity] = None,
        category: Optional[ErrorCategory] = None,
        context: Optional[dict] = None
    ):
        super().__init__(message)
        self.message = message
        self.severity = severity or self.__class__.severity
        self.category = category or self.__class__.category
        self.context = context or {}
        self.timestamp = pd.Timestamp.now()

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "severity": self.severity.value,
            "category": self.category.value,
            "context": self.context,
            "timestamp": str(self.timestamp)
        }


class DataLoadError(QlibHikyuuError):
    """数据加载错误"""
    severity = ErrorSeverity.HIGH
    category = ErrorCategory.DATA


class ConfigurationError(QlibHikyuuError):
    """配置错误"""
    severity = ErrorSeverity.CRITICAL
    category = ErrorCategory.CONFIG


class LookaheadBiasError(QlibHikyuuError):
    """前视偏差错误"""
    severity = ErrorSeverity.CRITICAL
    category = ErrorCategory.DATA

    def __init__(self, message: str, **kwargs):
        super().__init__(
            f"前视偏差检测: {message}",
            **kwargs
        )


class BacktestError(QlibHikyuuError):
    """回测错误"""
    severity = ErrorSeverity.HIGH
    category = ErrorCategory.CALCULATION


class ValidationError(QlibHikyuuError):
    """验证错误"""
    severity = ErrorSeverity.MEDIUM
    category = ErrorCategory.VALIDATION


class DependencyError(QlibHikyuuError):
    """依赖错误"""
    severity = ErrorSeverity.CRITICAL
    category = ErrorCategory.DEPENDENCY


# ============================================================================
# 错误处理装饰器
# ============================================================================

@dataclass
class RetryConfig:
    """重试配置"""
    max_attempts: int = 3
    delay: float = 1.0
    backoff: float = 2.0  # 指数退避因子
    max_delay: float = 60.0
    exceptions: tuple = (Exception,)


def with_error_handling(
    default_return: Any = None,
    raise_on_error: bool = True,
    log_level: int = logging.ERROR,
    category: ErrorCategory = ErrorCategory.SYSTEM
):
    """
    错误处理装饰器

    Args:
        default_return: 发生错误时的默认返回值
        raise_on_error: 是否重新抛出异常
        log_level: 日志级别
        category: 错误分类
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            try:
                return func(*args, **kwargs)
            except QlibHikyuuError as e:
                # 已经是我们的自定义异常，记录并处理
                logger.log(
                    log_level,
                    f"{func.__name__} 执行失败: {e.message}",
                    extra={"error_details": e.to_dict()}
                )
                if raise_on_error:
                    raise
                return default_return
            except Exception as e:
                # 包装成自定义异常
                error = QlibHikyuuError(
                    message=f"{func.__name__} 执行失败: {str(e)}",
                    category=category,
                    context={
                        "function": func.__name__,
                        "args": str(args)[:200],
                        "kwargs": str(kwargs)[:200],
                        "traceback": traceback.format_exc()
                    }
                )
                logger.log(
                    log_level,
                    error.message,
                    extra={"error_details": error.to_dict()}
                )
                if raise_on_error:
                    raise error from e
                return default_return
        return wrapper
    return decorator


def with_retry(
    config: Optional[RetryConfig] = None,
    on_retry: Optional[Callable[[Exception, int], None]] = None
):
    """
    重试装饰器

    Args:
        config: 重试配置
        on_retry: 重试时的回调函数
    """
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            delay = config.delay

            for attempt in range(1, config.max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except config.exceptions as e:
                    last_exception = e

                    if attempt == config.max_attempts:
                        break

                    if on_retry:
                        on_retry(e, attempt)
                    else:
                        logger.warning(
                            f"{func.__name__} 失败 (尝试 {attempt}/{config.max_attempts}): {e}"
                        )

                    time.sleep(min(delay, config.max_delay))
                    delay *= config.backoff

            # 所有重试都失败
            raise QlibHikyuuError(
                f"{func.__name__} 在 {config.max_attempts} 次尝试后失败",
                severity=ErrorSeverity.HIGH,
                context={
                    "last_error": str(last_exception),
                    "attempts": config.max_attempts
                }
            ) from last_exception

        return wrapper
    return decorator


# ============================================================================
# 数据验证装饰器
# ============================================================================

def validate_dataframe(
    check_empty: bool = True,
    check_columns: Optional[list] = None,
    check_index: Optional[str] = None,
    check_dtypes: Optional[dict] = None
):
    """
    DataFrame 验证装饰器

    Args:
        check_empty: 是否检查空数据
        check_columns: 必需的列
        check_index: 索引类型检查
        check_dtypes: 列类型检查
    """
    def decorator(func: Callable[..., pd.DataFrame]) -> Callable[..., pd.DataFrame]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> pd.DataFrame:
            result = func(*args, **kwargs)

            if not isinstance(result, pd.DataFrame):
                raise ValidationError(
                    f"{func.__name__} 应返回 DataFrame，实际返回 {type(result)}"
                )

            if check_empty and result.empty:
                raise ValidationError(f"{func.__name__} 返回了空 DataFrame")

            if check_columns:
                missing = set(check_columns) - set(result.columns)
                if missing:
                    raise ValidationError(
                        f"{func.__name__} 缺少必需的列: {missing}"
                    )

            if check_index:
                if check_index == "MultiIndex" and result.index.nlevels < 2:
                    raise ValidationError(
                        f"{func.__name__} 需要 MultiIndex，实际为 {type(result.index)}"
                    )

            if check_dtypes:
                for col, expected_dtype in check_dtypes.items():
                    if col in result.columns:
                        actual_dtype = result[col].dtype
                        if not pd.api.types.is_dtype_equal(actual_dtype, expected_dtype):
                            logger.warning(
                                f"列 {col} 类型不匹配: 期望 {expected_dtype}, 实际 {actual_dtype}"
                            )

            return result
        return wrapper
    return decorator


# ============================================================================
# 错误恢复机制
# ============================================================================

class ErrorRecovery:
    """错误恢复管理器"""

    def __init__(self, checkpoint_dir: Optional[Path] = None):
        self.checkpoint_dir = checkpoint_dir or Path(".checkpoints")
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.errors = []

    def save_checkpoint(self, name: str, data: Any):
        """保存检查点"""
        checkpoint_file = self.checkpoint_dir / f"{name}.pkl"
        try:
            pd.to_pickle(data, checkpoint_file)
            logger.debug(f"检查点已保存: {name}")
        except Exception as e:
            logger.error(f"保存检查点失败: {e}")

    def load_checkpoint(self, name: str) -> Optional[Any]:
        """加载检查点"""
        checkpoint_file = self.checkpoint_dir / f"{name}.pkl"
        if checkpoint_file.exists():
            try:
                data = pd.read_pickle(checkpoint_file)
                logger.info(f"从检查点恢复: {name}")
                return data
            except Exception as e:
                logger.error(f"加载检查点失败: {e}")
        return None

    def record_error(self, error: QlibHikyuuError):
        """记录错误"""
        self.errors.append(error.to_dict())

        # 保存错误日志
        error_log = self.checkpoint_dir / "error_log.json"
        import json
        with open(error_log, "w") as f:
            json.dump(self.errors, f, indent=2, default=str)

    def can_recover(self, checkpoint_name: str) -> bool:
        """检查是否可以从检查点恢复"""
        checkpoint_file = self.checkpoint_dir / f"{checkpoint_name}.pkl"
        return checkpoint_file.exists()


# ============================================================================
# 错误监控和告警
# ============================================================================

class ErrorMonitor:
    """错误监控器"""

    def __init__(self, alert_threshold: int = 5):
        self.alert_threshold = alert_threshold
        self.error_counts = {}
        self.alerts_sent = set()

    def track_error(self, error: QlibHikyuuError):
        """跟踪错误"""
        key = f"{error.category.value}:{error.__class__.__name__}"
        self.error_counts[key] = self.error_counts.get(key, 0) + 1

        # 检查是否需要告警
        if self.error_counts[key] >= self.alert_threshold:
            if key not in self.alerts_sent:
                self.send_alert(error, self.error_counts[key])
                self.alerts_sent.add(key)

    def send_alert(self, error: QlibHikyuuError, count: int):
        """发送告警（这里只是记录，实际可以接入告警系统）"""
        logger.critical(
            f"错误告警: {error.__class__.__name__} 已发生 {count} 次\n"
            f"严重级别: {error.severity.value}\n"
            f"类别: {error.category.value}\n"
            f"消息: {error.message}"
        )

    def get_error_summary(self) -> dict:
        """获取错误摘要"""
        return {
            "total_errors": sum(self.error_counts.values()),
            "error_types": len(self.error_counts),
            "details": self.error_counts,
            "alerts_sent": len(self.alerts_sent)
        }


# ============================================================================
# 全局错误处理器
# ============================================================================

_error_monitor = ErrorMonitor()
_error_recovery = ErrorRecovery()


def handle_error(error: Union[Exception, QlibHikyuuError]) -> QlibHikyuuError:
    """全局错误处理函数"""
    if not isinstance(error, QlibHikyuuError):
        error = QlibHikyuuError(
            message=str(error),
            context={"original_type": type(error).__name__}
        )

    # 记录和监控
    _error_recovery.record_error(error)
    _error_monitor.track_error(error)

    return error


def get_error_summary() -> dict:
    """获取错误统计摘要"""
    return _error_monitor.get_error_summary()


# ============================================================================
# 使用示例
# ============================================================================

if __name__ == "__main__":
    # 设置日志
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # 测试错误处理装饰器
    @with_error_handling(default_return=pd.DataFrame(), raise_on_error=False)
    def test_function():
        raise ValueError("测试错误")

    result = test_function()
    print(f"结果: {result}")

    # 测试重试机制
    attempt_count = 0

    @with_retry(RetryConfig(max_attempts=3, delay=0.5))
    def test_retry():
        global attempt_count
        attempt_count += 1
        print(f"尝试 {attempt_count}")
        if attempt_count < 3:
            raise ValueError("暂时失败")
        return "成功"

    try:
        result = test_retry()
        print(f"重试结果: {result}")
    except QlibHikyuuError as e:
        print(f"重试失败: {e.message}")

    # 测试验证装饰器
    @validate_dataframe(check_columns=["A", "B"])
    def get_data() -> pd.DataFrame:
        return pd.DataFrame({"A": [1, 2], "B": [3, 4]})

    df = get_data()
    print(f"验证通过: {df}")

    # 获取错误摘要
    print(f"\n错误摘要: {get_error_summary()}")