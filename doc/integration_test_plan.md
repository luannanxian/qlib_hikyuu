# Qlib-Hikyuu 集成测试计划

## 文档信息
- **版本**: 1.0.0
- **创建日期**: 2025-01-18
- **负责人**: QA Team
- **状态**: 待审批

## 1. 测试目标与范围

### 1.1 测试目标
- 验证所有模块间的集成正确性
- 确保数据流在各组件间正确传递
- 验证系统端到端功能的完整性
- 评估系统在集成环境下的性能表现
- 确认错误处理和恢复机制的有效性

### 1.2 测试范围

#### 包含范围
- **核心集成模块**
  - Hikyuu与Qlib的数据集成
  - 回测引擎集成
  - 监控系统集成
  - 报告生成系统集成

- **数据流测试**
  - 数据加载 → 处理 → 特征工程
  - 信号生成 → 回测执行 → 结果输出
  - 实时监控数据流

- **系统接口**
  - REST API接口
  - 文件系统接口
  - 数据库连接（如有）

#### 排除范围
- 单元测试（已在单独测试计划中覆盖）
- UI自动化测试（待Web UI实现后补充）
- 性能压力测试（需专门的性能测试计划）

## 2. 测试策略

### 2.1 测试方法
- **自底向上集成**: 从基础模块开始，逐步集成上层模块
- **增量测试**: 每次集成新模块后立即测试
- **持续集成**: 配合CI/CD流程自动执行测试

### 2.2 测试级别

| 级别 | 描述 | 重点 |
|------|------|------|
| L1 - 模块集成 | 两个直接相关模块的集成 | 接口契约、数据格式 |
| L2 - 子系统集成 | 功能相关的多个模块集成 | 业务流程、数据流 |
| L3 - 系统集成 | 完整系统的端到端集成 | 用户场景、性能 |

### 2.3 测试环境

```yaml
测试环境配置:
  操作系统: Ubuntu 20.04 / macOS 12+
  Python版本: 3.8+
  依赖管理: pip + requirements.txt

  核心依赖:
    - qlib: latest
    - hikyuu: 1.3.0+
    - pandas: 1.3.0+
    - numpy: 1.20.0+

  测试框架:
    - pytest: 7.0+
    - pytest-cov: 3.0+
    - pytest-mock: 3.6+

  数据要求:
    - 测试数据集: A股历史数据（2020-2023）
    - 数据格式: CSV/HDF5
    - 数据量: 最少100支股票，3年数据
```

## 3. 测试用例设计

### 3.1 L1级 - 模块集成测试

#### TC-L1-001: Hikyuu数据加载器集成
```yaml
测试ID: TC-L1-001
测试目标: 验证HikyuuDataLoader与Qlib的集成
前置条件:
  - Hikyuu环境已配置
  - 测试数据已准备
测试步骤:
  1. 创建HikyuuDataLoader实例
  2. 加载指定股票数据
  3. 转换为Qlib格式
  4. 验证数据完整性
预期结果:
  - 数据成功加载
  - 格式转换正确
  - 无数据丢失
```

#### TC-L1-002: 错误处理框架集成
```yaml
测试ID: TC-L1-002
测试目标: 验证错误处理与重试机制
测试步骤:
  1. 模拟数据加载失败
  2. 触发重试机制
  3. 验证错误日志
  4. 检查恢复流程
预期结果:
  - 自动重试3次
  - 错误信息记录完整
  - 系统正确恢复或优雅失败
```

#### TC-L1-003: 数据管道集成
```yaml
测试ID: TC-L1-003
测试目标: 验证数据处理管道
测试步骤:
  1. 输入原始数据
  2. 执行数据清洗
  3. 应用特征工程
  4. 验证输出数据
预期结果:
  - 数据清洗正确
  - 特征计算准确
  - 管道性能符合要求
```

### 3.2 L2级 - 子系统集成测试

#### TC-L2-001: 完整回测流程
```yaml
测试ID: TC-L2-001
测试目标: 验证回测子系统集成
测试范围:
  - 数据加载 → 信号生成 → 回测执行 → 结果输出
测试步骤:
  1. 准备测试策略和信号
  2. 配置回测参数
  3. 执行完整回测
  4. 验证结果指标
验证点:
  - 收益率计算正确
  - 手续费和滑点正确扣除
  - T+1延迟正确执行
  - 无前视偏差
```

#### TC-L2-002: 监控系统集成
```yaml
测试ID: TC-L2-002
测试目标: 验证监控子系统集成
测试步骤:
  1. 启动监控系统
  2. 运行模拟策略
  3. 触发各级别告警
  4. 验证告警通知
验证点:
  - 指标计算实时性
  - 告警阈值准确
  - 通知渠道有效
  - 仪表板数据同步
```

#### TC-L2-003: 报告生成集成
```yaml
测试ID: TC-L2-003
测试目标: 验证报告生成子系统
测试步骤:
  1. 完成回测
  2. 生成各格式报告
  3. 验证报告内容
  4. 检查图表生成
验证点:
  - HTML报告完整性
  - Excel数据准确性
  - 图表正确渲染
  - 文件正确保存
```

### 3.3 L3级 - 系统集成测试

#### TC-L3-001: 端到端策略回测
```yaml
测试ID: TC-L3-001
测试目标: 验证完整的策略回测流程
测试场景:
  用户从数据准备到最终报告的完整流程
测试步骤:
  1. 准备历史数据
  2. 配置策略参数
  3. 生成交易信号
  4. 执行回测
  5. 启动监控
  6. 生成报告
验证点:
  - 每个步骤正确执行
  - 数据在各阶段正确传递
  - 最终结果符合预期
  - 性能指标达标
```

#### TC-L3-002: 异常恢复测试
```yaml
测试ID: TC-L3-002
测试目标: 验证系统异常恢复能力
测试场景:
  1. 数据源中断恢复
  2. 回测中断恢复
  3. 监控系统重启
  4. 并发访问处理
验证点:
  - 系统能够恢复到正常状态
  - 数据一致性保持
  - 不会产生脏数据
```

#### TC-L3-003: 多策略并发测试
```yaml
测试ID: TC-L3-003
测试目标: 验证多策略并发执行
测试步骤:
  1. 准备3个不同策略
  2. 并发执行回测
  3. 监控资源使用
  4. 验证结果隔离
验证点:
  - 策略间数据隔离
  - 资源合理分配
  - 结果独立正确
```

## 4. 测试数据准备

### 4.1 测试数据集

```python
# 测试数据配置
test_data_config = {
    "stocks": [
        "SH600000",  # 浦发银行
        "SH600036",  # 招商银行
        "SZ000001",  # 平安银行
        "SZ000002",  # 万科A
        "SH600519",  # 贵州茅台
    ],
    "date_range": {
        "train": ("2020-01-01", "2022-12-31"),
        "test": ("2023-01-01", "2023-12-31")
    },
    "features": [
        "open", "high", "low", "close", "volume",
        "ma_5", "ma_20", "rsi", "macd"
    ]
}
```

### 4.2 测试信号生成

```python
# 模拟交易信号
def generate_test_signals():
    """生成测试用交易信号"""
    signals = {
        "conservative": lambda x: 0.3,  # 保守策略
        "aggressive": lambda x: 0.8,    # 激进策略
        "balanced": lambda x: 0.5,      # 均衡策略
        "random": lambda x: np.random.choice([-1, 0, 1])  # 随机策略
    }
    return signals
```

## 5. 测试执行计划

### 5.1 执行时间表

| 阶段 | 时间 | 活动 | 负责人 |
|------|------|------|--------|
| 准备阶段 | Day 1-2 | 环境搭建、数据准备 | QA Team |
| L1测试 | Day 3-5 | 模块集成测试 | 开发+QA |
| L2测试 | Day 6-8 | 子系统集成测试 | QA Team |
| L3测试 | Day 9-10 | 系统集成测试 | QA Team |
| 回归测试 | Day 11 | 问题修复后回归 | QA Team |
| 报告编写 | Day 12 | 测试报告 | QA Lead |

### 5.2 测试脚本组织

```bash
tests/
├── integration/
│   ├── L1_module/
│   │   ├── test_hikyuu_integration.py
│   │   ├── test_error_handling.py
│   │   └── test_data_pipeline.py
│   ├── L2_subsystem/
│   │   ├── test_backtest_flow.py
│   │   ├── test_monitoring.py
│   │   └── test_reporting.py
│   └── L3_system/
│       ├── test_e2e_scenarios.py
│       ├── test_recovery.py
│       └── test_concurrent.py
├── fixtures/
│   ├── data_fixtures.py
│   ├── config_fixtures.py
│   └── mock_fixtures.py
└── conftest.py
```

## 6. 测试自动化

### 6.1 CI/CD集成

```yaml
# .github/workflows/integration-tests.yml
name: Integration Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  integration-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Setup Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.8'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-test.txt

      - name: Prepare test data
        run: python scripts/prepare_test_data.py

      - name: Run L1 tests
        run: pytest tests/integration/L1_module/ -v

      - name: Run L2 tests
        run: pytest tests/integration/L2_subsystem/ -v

      - name: Run L3 tests
        run: pytest tests/integration/L3_system/ -v

      - name: Generate coverage report
        run: |
          pytest --cov=. --cov-report=html

      - name: Upload artifacts
        uses: actions/upload-artifact@v2
        with:
          name: test-results
          path: |
            htmlcov/
            test-reports/
```

### 6.2 测试命令

```bash
# 运行所有集成测试
make test-integration

# 运行特定级别测试
pytest tests/integration/L1_module/ -v
pytest tests/integration/L2_subsystem/ -v
pytest tests/integration/L3_system/ -v

# 运行特定测试用例
pytest tests/integration/L2_subsystem/test_backtest_flow.py::test_complete_backtest -v

# 生成测试报告
pytest --html=report.html --self-contained-html

# 运行测试并生成覆盖率
pytest --cov=. --cov-report=html --cov-report=term
```

## 7. 缺陷管理

### 7.1 缺陷分级

| 级别 | 描述 | 示例 | SLA |
|------|------|------|-----|
| P0 - 阻塞 | 系统无法使用 | 数据加载失败、系统崩溃 | 4小时 |
| P1 - 严重 | 功能异常 | 计算错误、数据丢失 | 1天 |
| P2 - 一般 | 功能受限 | 性能问题、UI问题 | 3天 |
| P3 - 次要 | 体验问题 | 提示不明确、文档错误 | 1周 |

### 7.2 缺陷跟踪

```markdown
缺陷报告模板:
- **缺陷ID**: BUG-YYYYMMDD-XXX
- **发现日期**: YYYY-MM-DD
- **测试用例**: TC-XX-XXX
- **严重级别**: P0/P1/P2/P3
- **模块**: 具体模块名称
- **描述**: 详细问题描述
- **复现步骤**:
  1. 步骤1
  2. 步骤2
- **预期结果**:
- **实际结果**:
- **截图/日志**:
- **环境信息**:
- **修复状态**: 新建/进行中/已修复/已验证/关闭
```

## 8. 测试指标

### 8.1 质量指标

| 指标 | 目标值 | 计算方法 |
|------|--------|----------|
| 测试覆盖率 | ≥80% | 执行的测试用例/总测试用例 |
| 代码覆盖率 | ≥70% | 测试覆盖的代码行/总代码行 |
| 缺陷密度 | <5个/KLOC | 缺陷数/代码千行数 |
| 缺陷修复率 | ≥95% | 已修复缺陷/总缺陷数 |
| 测试通过率 | ≥90% | 通过的测试/总测试数 |

### 8.2 进度指标

| 指标 | 计算方法 | 报告频率 |
|------|----------|----------|
| 测试执行进度 | 已执行测试/计划测试 | 每日 |
| 缺陷趋势 | 新增vs修复缺陷数 | 每日 |
| 阻塞问题 | P0/P1未解决数 | 实时 |

## 9. 风险与缓解

### 9.1 识别的风险

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| 测试数据不足 | 中 | 高 | 提前准备多样化测试数据 |
| 环境不稳定 | 低 | 中 | 使用容器化部署 |
| 依赖版本冲突 | 中 | 中 | 严格版本管理 |
| 测试时间不足 | 中 | 高 | 优先级排序，自动化 |

### 9.2 回滚计划

```bash
# 快速回滚脚本
#!/bin/bash
# rollback.sh

echo "开始回滚到上一个稳定版本..."
git checkout last-stable-tag
pip install -r requirements-stable.txt
python scripts/verify_installation.py
echo "回滚完成"
```

## 10. 验收标准

### 10.1 测试完成标准
- [ ] 所有L1级测试用例执行完成
- [ ] 所有L2级测试用例执行完成
- [ ] 所有L3级测试用例执行完成
- [ ] 测试覆盖率达到80%以上
- [ ] 代码覆盖率达到70%以上
- [ ] P0/P1缺陷全部修复
- [ ] P2缺陷修复率>90%

### 10.2 发布准入标准
- [ ] 所有集成测试通过
- [ ] 无P0/P1级别缺陷
- [ ] 性能指标达标
- [ ] 文档更新完成
- [ ] 回归测试通过

## 11. 测试报告模板

```markdown
# 集成测试报告

## 执行摘要
- 测试周期: YYYY-MM-DD 至 YYYY-MM-DD
- 测试范围: [描述]
- 测试结果: 通过/不通过

## 测试执行统计
- 计划执行: X个
- 实际执行: X个
- 通过: X个
- 失败: X个
- 阻塞: X个

## 缺陷统计
- P0: X个（已修复X个）
- P1: X个（已修复X个）
- P2: X个（已修复X个）
- P3: X个（已修复X个）

## 测试覆盖率
- 功能覆盖: X%
- 代码覆盖: X%

## 主要问题与风险
[列出主要问题]

## 结论与建议
[测试结论和改进建议]

## 附录
- 详细测试用例执行记录
- 缺陷列表
- 测试日志
```

## 12. 持续改进

### 12.1 经验总结
- 每个测试周期结束后进行回顾
- 记录最佳实践和教训
- 更新测试策略和流程

### 12.2 测试优化
- 定期评审测试用例有效性
- 优化测试执行时间
- 提高自动化覆盖率

## 附录A: 测试工具清单

| 工具 | 用途 | 版本 |
|------|------|------|
| pytest | 测试框架 | 7.0+ |
| pytest-cov | 覆盖率 | 3.0+ |
| pytest-mock | Mock支持 | 3.6+ |
| pytest-html | HTML报告 | 3.1+ |
| tox | 多环境测试 | 3.24+ |
| hypothesis | 属性测试 | 6.0+ |

## 附录B: 联系信息

| 角色 | 负责人 | 联系方式 |
|------|--------|----------|
| 测试负责人 | QA Lead | qa-lead@example.com |
| 开发负责人 | Dev Lead | dev-lead@example.com |
| 产品负责人 | Product Owner | po@example.com |

---
*本文档将随项目进展持续更新*