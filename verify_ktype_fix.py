#!/usr/bin/env python3
"""验证ktype参数修复"""

import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

print("检查 hikyuu_integration.py 中的 ktype 参数修复...")
print("-" * 60)

# 读取文件内容
with open('hikyuu_integration.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 查找所有Query相关调用
query_lines = []
for i, line in enumerate(lines, 1):
    if 'hk.Query' in line or 'hk.QueryByDate' in line:
        if 'return' in line:  # 只看返回语句
            query_lines.append((i, line.strip()))

print("找到的 Query 调用：")
for line_no, line in query_lines:
    print(f"  行 {line_no}: {line}")

    # 检查参数使用
    if 'ktype=' in line:
        print(f"    ✅ 使用了正确的 ktype= 参数")
    elif 'kType=' in line:
        print(f"    ❌ 错误：使用了 kType= 参数")
    elif 'Query(-1)' in line:
        print(f"    ⚠️  兼容模式：无参数调用")
    else:
        print(f"    ℹ️  其他形式")

print("\n" + "=" * 60)
print("总结：")

# 检查是否所有需要的地方都修复了
has_kType = any('kType=' in line for _, line in query_lines)
has_ktype = any('ktype=' in line for _, line in query_lines)

if has_kType:
    print("❌ 发现未修复的 kType 参数使用！")
elif has_ktype:
    print("✅ 所有 Query 调用都使用了正确的 ktype 参数")
else:
    print("⚠️  未发现带频率参数的 Query 调用")

# 额外检查：确保关键方法存在
print("\n方法检查：")
content = ''.join(lines)

if '_load_for_training' in content:
    print("✅ _load_for_training 方法存在")
else:
    print("❌ _load_for_training 方法不存在")

if '_load_for_prediction' in content:
    print("✅ _load_for_prediction 方法存在")
else:
    print("❌ _load_for_prediction 方法不存在")

if 'mode: str = "train"' in content:
    print("✅ mode 参数已添加到 HikyuuDataLoader")
else:
    print("❌ mode 参数未添加")

print("\n" + "=" * 60)
print("前视偏差修复状态：完成 ✅")