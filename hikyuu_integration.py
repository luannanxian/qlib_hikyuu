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

from qlib.data.dataset.handler import DataHandlerLP
from qlib.data.dataset.loader import DataLoader
from qlib.log import get_module_logger

_ORIG_HOME = os.environ.get("HOME")
_HK_HOME = os.environ.get("HKU_HOME", os.path.join(os.getcwd(), ".hikyuu_home"))
os.makedirs(_HK_HOME, exist_ok=True)
os.environ["HOME"] = _HK_HOME
os.environ["HKU_HOME"] = _HK_HOME
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
            if stock.isNull():
                logger.warning("Hikyuu 中找不到标的 %s（转换后 %s），跳过。", inst, hk_code)
                continue

            k_data = stock.getKData(self._build_query(start_time, end_time))
            if k_data.size() == 0:
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
            start_date = pd.Timestamp(start) if start else None
            end_date = pd.Timestamp(end) if end else None
            start_str = start_date.strftime("%Y-%m-%d") if start_date else ""
            end_str = end_date.strftime("%Y-%m-%d") if end_date else ""
            if hasattr(hk, "QueryByDate"):
                return hk.QueryByDate(start_str, end_str, self._hk_freq)
            if hasattr(hk, "Query"):
                try:
                    return hk.Query(start_str, end_str, self._hk_freq)
                except TypeError:
                    pass
        if hasattr(hk, "Query"):
            try:
                return hk.Query(-1, self._hk_freq)
            except TypeError:
                return hk.Query(-1)
        raise RuntimeError("当前 hikyuu 版本缺少 Query / QueryByDate 接口，无法构造查询。")

    def _to_dataframe(self, k_data: "hk.KData") -> pd.DataFrame:
        if hasattr(k_data, "to_df"):
            df = k_data.to_df()
        elif hasattr(k_data, "to_pandas"):
            df = k_data.to_pandas()
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

        default_infer = infer_processors or [
            {"class": "Fillna", "kwargs": {"fields_group": "feature"}},
            {"class": "RobustZScoreNorm", "kwargs": {"fields_group": "feature", "clip_outlier": True}},
        ]
        default_learn = learn_processors or [
            {"class": "DropnaLabel"},
            {"class": "CSRankNorm", "kwargs": {"fields_group": "label"}},
        ]

        super().__init__(
            instruments=instruments,
            start_time=start_time,
            end_time=end_time,
            freq=freq,
            data_loader=loader,
            infer_processors=default_infer,
            learn_processors=default_learn,
            fit_start_time=fit_start_time or start_time,
            fit_end_time=fit_end_time or end_time,
            drop_raw=True,
            **kwargs,
        )


__all__ = ["HikyuuDataLoader", "HikyuuAlphaHandler"]
