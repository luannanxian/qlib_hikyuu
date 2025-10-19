#!/usr/bin/env python3
"""
快速开始示例 - 5分钟上手 Qlib-Hikyuu
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hikyuu_integration import HikyuuAlphaHandler
from utils.data_pipeline import UnifiedDataPipeline, DataPipelineConfig

def main():
    print("=== Qlib-Hikyuu 快速开始 ===\n")

    # 1. 加载数据（训练模式）
    print("Step 1: 加载数据...")
    handler = HikyuuAlphaHandler.create_for_training(
        instruments=["SH600000"],  # 浦发银行
        start_time="2023-01-01",
        end_time="2023-12-31"
    )

    data = handler.fetch()
    print(f"✅ 数据加载成功！形状: {data.shape}\n")

    # 2. 数据处理
    print("Step 2: 数据处理...")
    config = DataPipelineConfig(
        remove_outliers=True,
        add_technical_indicators=True
    )

    pipeline = UnifiedDataPipeline(config)
    processed_data = pipeline.fit_transform(data)
    print(f"✅ 处理完成！特征数: {len(processed_data.columns)}\n")

    # 3. 显示数据样本
    print("Step 3: 数据预览")
    print(processed_data.head())

    # 4. 简单统计
    print("\nStep 4: 数据统计")
    print(processed_data.describe())

    print("\n✅ 快速开始完成！")
    print("\n下一步:")
    print("- 查看 examples/complete_example.py 了解完整流程")
    print("- 阅读 doc/user_guide.md 了解更多功能")

if __name__ == "__main__":
    main()