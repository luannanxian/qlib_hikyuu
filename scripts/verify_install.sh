#!/usr/bin/env bash
set -euo pipefail

# 项目根目录（根据需要调整）
ROOT="/Users/zhenkunliu/project/qlib"
VENV="$ROOT/python3.13"
PYTHON="$VENV/bin/python"
WHEEL="$ROOT/dist/pyqlib-0.9.8.dev7+g7d66e4b78.d20251015-cp313-cp313-macosx_12_0_arm64.whl"

echo "使用 Python: $PYTHON"
"$PYTHON" --version

echo "安装 wheel：$WHEEL"
"$PYTHON" -m pip install --force-reinstall "$WHEEL"

echo "运行功能自检..."
"$PYTHON" - <<'PY'
import qlib
import qlib._compat as compat

qlib.init(provider_uri="~/.qlib/qlib_data/cn_data", backend="Local")
print("qlib 版本：", qlib.__version__)
print("兼容信息：", compat.__dict__.get("PYTHON_VERSION"))

# 关闭初始化
from qlib.utils import init_instance_by_config
init_instance_by_config({"module_path": "qlib.workflow.ColabRecorder", "class": "RecorderColab"})  # 轻量调用确保组件可用
print("基础功能验证通过。")
PY

echo "验证完成。"

