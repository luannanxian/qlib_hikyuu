# --------------------------------------------------------------------------
# Hikyuu ↔ Qlib 数据桥接实现
#
# 这个模块提供两个核心组件：
#   1. HikyuuDataLoader: 直接从 Hikyuu 的行情接口读取数据并组装成
#      Qlib DataHandler 期望的 MultiIndex DataFrame。
#   2. HikyuuAlphaHandler: 基于 DataHandlerLP 的实现，可以直接在 Qlib
#      配置中替换 Alpha158，作为 handler 使用。
#
# 使用方式：
#   - 确保安装了 hikyuu Python 包并正确初始化数据源；
#   - 在 Qlib 脚本中将 handler 改为本模块的 HikyuuAlphaHandler；
#   - 其余训练 / 回测流程保持不变。
# --------------------------------------------------------------------------


from __future__ import annotations

import logging
from dataclasses import dataclass
import os
from typing import Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from qlib.contrib.data.handler import check_transform_proc
from qlib.data.dataset.handler import DataHandlerLP
from qlib.data.dataset.loader import DataLoader
from qlib.log import get_module_logger
from pathlib import Path

_SETUP_LOGGER = logging.getLogger("hikyuu_integration.setup")


def _resolve_hikyuu_home() -> Tuple[str, bool]:
    """
    解析 Hikyuu 的工作目录。
    返回值:
      - 选中的 HKU_HOME 路径
      - 是否需要临时覆盖 HOME 环境变量
    """
    env_home = os.environ.get("HKU_HOME")
    if env_home:
        return env_home, False

    project_root = Path(__file__).resolve().parent
    project_home = project_root / ".hikyuu_home"
    default_home = Path.home() / ".hikyuu"

    if default_home.exists():
        return str(default_home), False

    project_home.mkdir(parents=True, exist_ok=True)
    return str(project_home), True


_ORIG_HOME = os.environ.get("HOME")
_HK_HOME, _OVERRIDE_HOME = _resolve_hikyuu_home()
if _OVERRIDE_HOME:
    os.environ["HOME"] = _HK_HOME
os.environ["HKU_HOME"] = _HK_HOME
_SETUP_LOGGER.info("Hikyuu home resolved to %s (override_home=%s)", _HK_HOME, _OVERRIDE_HOME)
try:
    import hikyuu as hk
except ImportError as exc:  # pragma: no cover - 强调运行时依赖
    raise ImportError(
        "请先安装 hikyuu (pip install hikyuu) 并确保可以导入。"
    ) from exc
finally:
    if _ORIG_HOME is not None:
        os.environ["HOME"] = _ORIG_HOME
    else:
        os.environ.pop("HOME", None)

# 若存在 hikyuu.ini 则显式初始化，确保数据驱动可用
_HK_CONFIG = Path(_HK_HOME) / "hikyuu.ini"
if _HK_CONFIG.exists():
    try:
        _SETUP_LOGGER.info("Initializing Hikyuu with config %s", _HK_CONFIG)
        hk.hikyuu_init(str(_HK_CONFIG))
    except Exception as exc:  # pragma: no cover - 依赖外部库
        _SETUP_LOGGER.warning("调用 hikyuu_init(%s) 失败：%s", _HK_CONFIG, exc)
else:
    _SETUP_LOGGER.warning("未在 %s 找到 hikyuu.ini，Hikyuu 将使用默认配置。", _HK_HOME)

logger = get_module_logger("hikyuu_integration", logging.INFO)


def _to_hikyuu_code(instr: str) -> str:
    """将 Qlib 使用的代码（如 SH600000）转为 Hikyuu 习惯的小写代码（sh600000）。"""
    instr = instr.strip()
    if len(instr) <= 2:
        return instr.lower()
    prefix, code = instr[:2], instr[2:]
    return f"{prefix.lower()}{code}"


def _ensure_datetime(df: pd.DataFrame, column: str = "datetime") -> pd.Series:
    """将 Hikyuu KData 返回的 datetime 列转换成 pandas 时间戳。"""
    dt = df[column]
    if pd.api.types.is_datetime64_any_dtype(dt):
        return dt
    if pd.api.types.is_integer_dtype(dt):
        # Hikyuu 常用 YYYYMMDDhhmmss 整型时间
        dt = pd.to_datetime(dt.astype(str))
    else:
        dt = pd.to_datetime(dt)
    return dt


def _is_valid_stock(stock: "hk.Stock") -> bool:
    """兼容不同版本 Hikyuu 的股票有效性检查。"""
    for attr in ("isNull", "is_null", "is_valid", "isValid"):
        if not hasattr(stock, attr):
            continue
        value = getattr(stock, attr)
        try:
            result = value() if callable(value) else bool(value)
        except Exception:  # pragma: no cover - 依赖外部库实现
            continue
        if attr in {"isNull", "is_null"}:
            return not result
        return bool(result)
    return stock is not None


@dataclass
class HikyuuDataLoader(DataLoader):
    """基于 Hikyuu 的数据加载器，满足 Qlib DataHandler 的 load 接口。"""

    fields: Sequence[str] = ("OPEN", "HIGH", "LOW", "CLOSE", "VOLUME", "AMOUNT")
    freq: str = "day"
    label_shift: int = 1

    def __post_init__(self):
        freq_map = {"day": hk.Query.DAY, "week": hk.Query.WEEK, "month": hk.Query.MONTH}
        if self.freq not in freq_map:
            raise ValueError(f"暂不支持 freq='{self.freq}'，可选值: {list(freq_map)}")
        self._hk_freq = freq_map[self.freq]
        self._sm = hk.StockManager.instance()

    # DataLoader 接口 ------------------------------------------------------------------
    def load(
        self,
        instruments: Iterable[str],
        start_time: Optional[str],
        end_time: Optional[str],
    ) -> pd.DataFrame:
        frames: List[pd.DataFrame] = []
        for inst in instruments:
            hk_code = _to_hikyuu_code(inst)
            stock = self._sm[hk_code]
            if not _is_valid_stock(stock):
                logger.warning("Hikyuu 中找不到标的 %s（转换后 %s），跳过。", inst, hk_code)
                continue

            query = self._build_query(start_time, end_time)
            if hasattr(stock, "get_kdata"):
                k_data = stock.get_kdata(query)
            else:
                k_data = stock.getKData(query)
            size = len(k_data) if hasattr(k_data, "__len__") else getattr(k_data, "size", lambda: 0)()
            if size == 0:
                logger.warning("标的 %s 在区间 [%s, %s] 无数据，跳过。", inst, start_time, end_time)
                continue

            df = self._to_dataframe(k_data)
            df["instrument"] = inst

            # 构造标签：Ref($close, -label_shift)/$close - 1
            label = df["close"].shift(-self.label_shift) / df["close"] - 1
            df["label"] = label
            df.dropna(inplace=True)  # 确保未来收益存在

            frames.append(df)

        if not frames:
            raise ValueError("未能从 Hikyuu 中加载到任何数据，请检查代码或时间区间。")

        data = pd.concat(frames, axis=0)
        data.set_index(["datetime", "instrument"], inplace=True)

        # 构造 MultiIndex 列
        feature_columns = []
        for field in self.fields:
            lower = field.lower()
            if lower not in data.columns:
                logger.warning("字段 %s 在数据中不存在，将跳过。", lower)
                continue
            feature_columns.append(("feature", field))
        feature_index = pd.MultiIndex.from_tuples(feature_columns, names=["group", "field"])

        feature_df = data[[f.lower() for f in self.fields if f.lower() in data.columns]]
        feature_df.columns = feature_index

        label_index = pd.MultiIndex.from_tuples([("label", "LABEL0")], names=["group", "field"])
        label_df = data[["label"]]
        label_df.columns = label_index

        return pd.concat([feature_df, label_df], axis=1).sort_index()

    # 辅助 ---------------------------------------------------------------------------
    def _build_query(self, start: Optional[str], end: Optional[str]) -> hk.Query:
        if start or end:
            if hasattr(hk, "QueryByDate"):
                start_date = pd.Timestamp(start) if start else None
                end_date = pd.Timestamp(end) if end else None
                start_str = start_date.strftime("%Y-%m-%d") if start_date else ""
                end_str = end_date.strftime("%Y-%m-%d") if end_date else ""
                return hk.QueryByDate(start_str, end_str, self._hk_freq)
            start_dt = hk.Datetime(start) if start else hk.Datetime.min()
            end_dt = hk.Datetime(end) if end else None
            return hk.Query(start_dt, end_dt, self._hk_freq)
        if hasattr(hk, "Query"):
            try:
                return hk.Query(-1, self._hk_freq)
            except TypeError:
                return hk.Query(-1)
        raise RuntimeError("当前 hikyuu 版本缺少可用的 Query 接口，无法构造查询。")

    def _to_dataframe(self, k_data: "hk.KData") -> pd.DataFrame:
        if hasattr(k_data, "to_pandas"):
            df = k_data.to_pandas()
        elif hasattr(k_data, "to_df"):
            df = k_data.to_df()
        else:
            # 逐条构建 DataFrame
            records = []
            for rec in k_data:
                records.append(
                    {
                        "datetime": rec.datetime.number,
                        "open": rec.openPrice,
                        "high": rec.highPrice,
                        "low": rec.lowPrice,
                        "close": rec.closePrice,
                        "volume": rec.vol,
                        "amount": rec.amount,
                    }
                )
            df = pd.DataFrame(records)

        df = df.rename(
            columns={c: c.lower() for c in df.columns if isinstance(c, str)},
        )
        df["datetime"] = _ensure_datetime(df, column="datetime")
        df.sort_values("datetime", inplace=True)
        return df


class HikyuuAlphaHandler(DataHandlerLP):
    """可直接在 Qlib 的 handler 配置中使用的 Hikyuu Handler。"""

    def __init__(
        self,
        instruments: Sequence[str],
        start_time: str,
        end_time: str,
        fit_start_time: Optional[str] = None,
        fit_end_time: Optional[str] = None,
        freq: str = "day",
        fields: Sequence[str] = ("OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"),
        label_shift: int = 1,
        infer_processors: Optional[Sequence[dict]] = None,
        learn_processors: Optional[Sequence[dict]] = None,
        **kwargs,
    ):
        loader = HikyuuDataLoader(fields=fields, freq=freq, label_shift=label_shift)
        fit_start = fit_start_time or start_time
        fit_end = fit_end_time or end_time

        default_infer = infer_processors or [
            {"class": "Fillna", "kwargs": {"fields_group": "feature"}},
            {"class": "RobustZScoreNorm", "kwargs": {"fields_group": "feature", "clip_outlier": True}},
        ]
        default_learn = learn_processors or [
            {"class": "DropnaLabel"},
            {"class": "CSRankNorm", "kwargs": {"fields_group": "label"}},
        ]
        infer_config = check_transform_proc(default_infer, fit_start, fit_end)
        learn_config = check_transform_proc(default_learn, fit_start, fit_end)

        super().__init__(
            instruments=instruments,
            start_time=start_time,
            end_time=end_time,
            data_loader=loader,
            infer_processors=infer_config,
            learn_processors=learn_config,
            drop_raw=True,
            **kwargs,
        )
        self.fit_start_time = fit_start
        self.fit_end_time = fit_end


__all__ = ["HikyuuDataLoader", "HikyuuAlphaHandler"]
