# 集成测试执行指南

## 文档信息
- **版本**: 1.0.0
- **创建日期**: 2025-01-18
- **维护团队**: QA Team

## 1. 环境准备

### 1.1 安装依赖

```bash
# 安装基础依赖
pip install -r requirements.txt

# 安装测试依赖
pip install pytest pytest-cov pytest-html pytest-mock
```

### 1.2 配置环境变量

```bash
# 设置环境变量
export PYTHONPATH=$PYTHONPATH:$(pwd)
export TEST_ENV=integration
export LOG_LEVEL=DEBUG

# 配置Hikyuu（如果需要）
export HKU_HOME=/path/to/hikyuu
```

### 1.3 准备测试数据

```bash
# 生成测试数据
python tests/prepare_test_data.py

# 验证测试数据
python tests/prepare_test_data.py --validate
```

## 2. 执行测试

### 2.1 运行所有集成测试

```bash
# 基础执行
pytest tests/integration/ -v

# 带覆盖率报告
pytest tests/integration/ --cov=. --cov-report=html

# 生成HTML报告
pytest tests/integration/ --html=reports/integration_test_report.html --self-contained-html
```

### 2.2 分级执行

#### L1级 - 模块集成测试
```bash
# 运行L1级测试
pytest tests/integration/test_L1_module_integration.py -v

# 单独测试模块
pytest tests/integration/test_L1_module_integration.py::TestHikyuuIntegration -v
pytest tests/integration/test_L1_module_integration.py::TestErrorHandling -v
pytest tests/integration/test_L1_module_integration.py::TestDataPipeline -v
```

#### L2级 - 子系统集成测试
```bash
# 运行L2级测试
pytest tests/integration/test_L2_subsystem_integration.py -v

# 单独测试子系统
pytest tests/integration/test_L2_subsystem_integration.py::TestBacktestSubsystem -v
pytest tests/integration/test_L2_subsystem_integration.py::TestMonitoringSubsystem -v
pytest tests/integration/test_L2_subsystem_integration.py::TestReportingSubsystem -v
```

#### L3级 - 系统集成测试
```bash
# 运行L3级测试（需要先实现）
pytest tests/integration/test_L3_system_integration.py -v
```

### 2.3 特定测试用例执行

```bash
# 执行特定测试用例
pytest tests/integration/test_L1_module_integration.py::TestHikyuuIntegration::test_data_loading_with_mode -v

# 使用关键字筛选
pytest tests/integration/ -k "lookahead" -v
pytest tests/integration/ -k "monitoring" -v
```

### 2.4 并行执行

```bash
# 安装pytest-xdist
pip install pytest-xdist

# 并行执行（使用4个进程）
pytest tests/integration/ -n 4
```

## 3. 测试标记

### 3.1 定义标记

```python
# 在pytest.ini中定义
[pytest]
markers =
    slow: 标记为慢速测试
    critical: 关键路径测试
    smoke: 冒烟测试
    regression: 回归测试
```

### 3.2 使用标记

```bash
# 只运行快速测试
pytest tests/integration/ -m "not slow"

# 只运行关键测试
pytest tests/integration/ -m critical

# 运行冒烟测试
pytest tests/integration/ -m smoke
```

## 4. 测试配置

### 4.1 pytest配置文件

创建 `pytest.ini`:

```ini
[pytest]
minversion = 6.0
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    -v
    --tb=short
    --strict-markers
    --disable-warnings

markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
    critical: marks tests as critical path
    smoke: marks tests as smoke tests
    integration: marks tests as integration tests
```

### 4.2 测试夹具配置

创建 `tests/conftest.py`:

```python
import pytest
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

@pytest.fixture(scope="session")
def test_data_dir():
    """测试数据目录"""
    return Path(__file__).parent / "data"

@pytest.fixture(scope="session")
def temp_dir(tmp_path_factory):
    """临时目录"""
    return tmp_path_factory.mktemp("integration_test")
```

## 5. 持续集成

### 5.1 GitHub Actions配置

创建 `.github/workflows/integration-tests.yml`:

```yaml
name: Integration Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 2 * * *'  # 每天凌晨2点运行

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.8, 3.9]

    steps:
    - uses: actions/checkout@v2

    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v2
      with:
        python-version: ${{ matrix.python-version }}

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install pytest pytest-cov

    - name: Prepare test data
      run: python tests/prepare_test_data.py

    - name: Run L1 tests
      run: pytest tests/integration/test_L1_module_integration.py -v

    - name: Run L2 tests
      run: pytest tests/integration/test_L2_subsystem_integration.py -v

    - name: Generate coverage report
      run: pytest tests/integration/ --cov=. --cov-report=xml

    - name: Upload coverage to Codecov
      uses: codecov/codecov-action@v1
      with:
        file: ./coverage.xml
        flags: integration

    - name: Archive test results
      if: always()
      uses: actions/upload-artifact@v2
      with:
        name: test-results
        path: |
          htmlcov/
          reports/
```

## 6. 故障排除

### 6.1 常见问题

#### 导入错误
```bash
# 问题：ModuleNotFoundError
# 解决：设置PYTHONPATH
export PYTHONPATH=$PYTHONPATH:$(pwd)
```

#### 数据文件缺失
```bash
# 问题：FileNotFoundError: tests/data/market_data.pkl
# 解决：生成测试数据
python tests/prepare_test_data.py
```

#### 权限问题
```bash
# 问题：PermissionError
# 解决：检查文件权限
chmod 755 tests/integration/
chmod 644 tests/data/*
```

### 6.2 调试技巧

```bash
# 启用详细输出
pytest tests/integration/ -vv

# 显示print输出
pytest tests/integration/ -s

# 在失败时进入调试器
pytest tests/integration/ --pdb

# 只运行上次失败的测试
pytest tests/integration/ --lf

# 生成详细的失败报告
pytest tests/integration/ --tb=long
```

## 7. 测试报告

### 7.1 生成报告

```bash
# HTML报告
pytest tests/integration/ --html=reports/test_report.html --self-contained-html

# JUnit XML报告（用于CI）
pytest tests/integration/ --junitxml=reports/junit.xml

# 覆盖率报告
pytest tests/integration/ --cov=. --cov-report=html --cov-report=term

# Allure报告（需要安装allure-pytest）
pip install allure-pytest
pytest tests/integration/ --alluredir=reports/allure_results
allure serve reports/allure_results
```

### 7.2 报告解读

#### 覆盖率报告
- **语句覆盖率**: 执行的代码行数/总代码行数
- **分支覆盖率**: 执行的分支数/总分支数
- **函数覆盖率**: 调用的函数数/总函数数

目标值：
- 单元测试覆盖率 > 80%
- 集成测试覆盖率 > 70%
- 关键模块覆盖率 > 90%

#### 性能指标
- **测试执行时间**: 总时间应 < 10分钟
- **单个测试时间**: 大部分测试应 < 1秒
- **慢速测试**: 标记并优化 > 5秒的测试

## 8. 最佳实践

### 8.1 测试编写

1. **独立性**: 每个测试应该独立运行
2. **可重复性**: 测试结果应该一致
3. **清晰性**: 测试名称描述测试内容
4. **完整性**: 包含准备、执行、验证、清理

### 8.2 数据管理

1. **隔离测试数据**: 使用独立的测试数据库/文件
2. **数据清理**: 每个测试后清理数据
3. **数据生成**: 使用工厂模式生成测试数据
4. **数据验证**: 验证测试数据的正确性

### 8.3 Mock使用

```python
# 示例：Mock外部服务
from unittest.mock import Mock, patch

@patch('requests.get')
def test_external_api(mock_get):
    mock_get.return_value.json.return_value = {"status": "ok"}
    # 测试代码
```

## 9. 监控和维护

### 9.1 测试健康度监控

- **通过率趋势**: 监控测试通过率变化
- **执行时间**: 跟踪测试执行时间趋势
- **不稳定测试**: 识别和修复flaky tests
- **覆盖率变化**: 确保覆盖率不下降

### 9.2 定期维护

- **每周**: 审查失败的测试
- **每月**: 更新测试数据
- **每季度**: 优化慢速测试
- **每年**: 全面审查测试策略

## 10. 检查清单

### 执行前检查
- [ ] 环境变量已设置
- [ ] 依赖已安装
- [ ] 测试数据已准备
- [ ] 配置文件已更新

### 执行后检查
- [ ] 所有L1测试通过
- [ ] 所有L2测试通过
- [ ] 覆盖率达到目标
- [ ] 报告已生成
- [ ] 结果已记录

### 发布前检查
- [ ] 无P0/P1级缺陷
- [ ] 关键路径测试通过
- [ ] 性能指标达标
- [ ] 文档已更新

---
*本指南将根据实际执行情况持续更新*