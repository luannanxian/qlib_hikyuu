# Web GUI 架构分析与实施方案

## 1. 当前架构评估

### 1.1 现有架构优势
✅ **模块化设计**：核心功能已经模块化，易于服务化
✅ **数据层分离**：HikyuuDataLoader 可直接作为数据服务
✅ **错误处理完备**：ErrorHandler 可复用于 API 层
✅ **管道模式**：UnifiedDataPipeline 适合异步处理

### 1.2 需要调整的部分
⚠️ **同步执行模式**：需要支持异步和消息队列
⚠️ **紧耦合的回测**：需要解耦为独立服务
⚠️ **内存状态管理**：需要持久化和分布式支持
⚠️ **无 API 层**：需要添加 RESTful/WebSocket 接口

## 2. 是否需要重构？

### 答案：不需要大规模重构，但需要架构扩展

**原因分析**：
1. 当前代码设计良好，遵循 SOLID 原则
2. 核心业务逻辑可以复用
3. 只需添加 API 层和前端，不需要改动核心

## 3. 推荐的 Web 架构方案

### 3.1 三层架构设计

```
┌─────────────────────────────────────────────┐
│           前端层 (Frontend)                 │
│  React/Vue + TypeScript + Ant Design/Vuetify│
├─────────────────────────────────────────────┤
│           API 网关层 (API Gateway)          │
│         FastAPI + WebSocket + Redis         │
├─────────────────────────────────────────────┤
│           业务服务层 (Services)             │
│   现有核心模块 + Celery 异步任务队列        │
├─────────────────────────────────────────────┤
│           数据层 (Data Layer)               │
│    HikyuuDataLoader + MySQL + Redis Cache   │
└─────────────────────────────────────────────┘
```

### 3.2 技术栈选择

#### 后端技术栈
```python
# 推荐方案 A：FastAPI（现代、高性能）
- FastAPI: 现代 Python Web 框架
- Pydantic: 数据验证
- SQLAlchemy: ORM
- Celery: 异步任务队列
- Redis: 缓存和消息队列
- WebSocket: 实时数据推送

# 备选方案 B：Django（成熟、全功能）
- Django + DRF: REST API
- Django Channels: WebSocket
- Celery: 异步任务
- PostgreSQL: 数据库
```

#### 前端技术栈
```javascript
// 推荐方案：React + TypeScript
- React 18: UI 框架
- TypeScript: 类型安全
- Ant Design: 企业级 UI 组件
- Redux Toolkit: 状态管理
- Recharts: 图表库
- Socket.io: 实时通信

// 备选方案：Vue 3
- Vue 3 + Composition API
- Vuetify: Material Design 组件
- Pinia: 状态管理
- ECharts: 图表库
```

## 4. 渐进式实施计划

### Phase 1: API 层构建（无需重构）
```python
# api/main.py - FastAPI 应用
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any
import asyncio

from hikyuu_integration import HikyuuAlphaHandler
from utils.data_pipeline import UnifiedDataPipeline

app = FastAPI(title="Qlib-Hikyuu Web API")

# 添加 CORS 支持
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# RESTful API 端点
@app.post("/api/v1/data/load")
async def load_data(
    instruments: List[str],
    start_date: str,
    end_date: str,
    freq: str = "day"
):
    """加载市场数据"""
    # 直接使用现有的 HikyuuDataLoader
    loader = HikyuuDataLoader(
        fields=["OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"],
        freq=freq
    )
    data = loader.load(instruments, start_date, end_date)
    return {"status": "success", "shape": data.shape}

@app.post("/api/v1/backtest/run")
async def run_backtest(config: Dict[str, Any]):
    """运行回测（异步）"""
    # 提交到 Celery 队列
    task = run_backtest_task.delay(config)
    return {"task_id": task.id, "status": "pending"}

# WebSocket 实时数据
@app.websocket("/ws/realtime/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    try:
        while True:
            # 推送实时数据
            data = await get_realtime_data()
            await websocket.send_json(data)
            await asyncio.sleep(1)
    except Exception as e:
        await websocket.close()
```

### Phase 2: 前端界面开发
```typescript
// frontend/src/components/DataLoader.tsx
import React, { useState } from 'react';
import { Form, Select, DatePicker, Button, Table } from 'antd';
import { api } from '../services/api';

const DataLoader: React.FC = () => {
    const [loading, setLoading] = useState(false);
    const [data, setData] = useState([]);

    const handleLoadData = async (values: any) => {
        setLoading(true);
        try {
            const response = await api.loadData({
                instruments: values.instruments,
                startDate: values.dateRange[0].format('YYYY-MM-DD'),
                endDate: values.dateRange[1].format('YYYY-MM-DD'),
                freq: values.freq
            });
            setData(response.data);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="data-loader">
            <Form onFinish={handleLoadData}>
                <Form.Item name="instruments" label="股票代码">
                    <Select mode="multiple">
                        <Select.Option value="SH600000">浦发银行</Select.Option>
                        <Select.Option value="SZ000001">平安银行</Select.Option>
                    </Select>
                </Form.Item>

                <Form.Item name="dateRange" label="时间范围">
                    <DatePicker.RangePicker />
                </Form.Item>

                <Form.Item>
                    <Button type="primary" htmlType="submit" loading={loading}>
                        加载数据
                    </Button>
                </Form.Item>
            </Form>

            <Table dataSource={data} loading={loading} />
        </div>
    );
};
```

### Phase 3: 服务层改造（最小化修改）
```python
# services/backtest_service.py
from celery import Celery
from typing import Dict, Any
import json

# 创建 Celery 应用
celery_app = Celery('qlib_hikyuu', broker='redis://localhost:6379')

@celery_app.task
def run_backtest_task(config: Dict[str, Any]):
    """异步回测任务"""
    # 使用现有的回测引擎
    from backtest import BacktestEngine, BacktestConfig

    engine = BacktestEngine(BacktestConfig(**config))
    results = engine.run()

    # 保存结果到 Redis
    redis_client.set(f"backtest:{task_id}", json.dumps(results))

    # 发送完成通知
    send_notification(task_id, "completed")

    return results

# services/realtime_service.py
class RealtimeDataService:
    """实时数据服务（使用现有的 HikyuuDataLoader）"""

    def __init__(self):
        self.loader = HikyuuDataLoader(mode="predict")
        self.websocket_manager = WebSocketManager()

    async def stream_data(self, instruments: List[str]):
        """流式推送数据"""
        while True:
            # 获取最新数据
            data = self.loader.load_realtime(instruments)

            # 推送到所有连接的客户端
            await self.websocket_manager.broadcast(data)

            await asyncio.sleep(1)  # 1秒更新
```

## 5. 数据库设计（新增）

```sql
-- 用户管理
CREATE TABLE users (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 策略管理
CREATE TABLE strategies (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    name VARCHAR(100) NOT NULL,
    code TEXT NOT NULL,
    config JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 回测任务
CREATE TABLE backtest_tasks (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    strategy_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL,
    config JSON,
    result JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (strategy_id) REFERENCES strategies(id)
);

-- 实盘交易记录
CREATE TABLE trades (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    strategy_id BIGINT NOT NULL,
    instrument VARCHAR(20) NOT NULL,
    direction VARCHAR(10) NOT NULL,
    quantity INT NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    commission DECIMAL(10, 4),
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (strategy_id) REFERENCES strategies(id)
);
```

## 6. 项目结构（扩展后）

```
qlib-project/
├── backend/                    # 后端 API（新增）
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py            # FastAPI 应用
│   │   ├── routes/            # API 路由
│   │   ├── models/            # Pydantic 模型
│   │   └── middlewares/       # 中间件
│   ├── services/              # 服务层（新增）
│   │   ├── auth_service.py
│   │   ├── backtest_service.py
│   │   └── realtime_service.py
│   └── tasks/                 # Celery 任务（新增）
│       └── backtest_tasks.py
├── frontend/                   # 前端应用（新增）
│   ├── public/
│   ├── src/
│   │   ├── components/        # React 组件
│   │   ├── pages/            # 页面组件
│   │   ├── services/         # API 服务
│   │   ├── store/            # Redux store
│   │   └── App.tsx
│   └── package.json
├── core/                      # 核心业务逻辑（原有代码移至此处）
│   ├── hikyuu_integration.py
│   ├── utils/
│   └── tests/
├── database/                  # 数据库脚本（新增）
│   ├── migrations/
│   └── schema.sql
└── docker/                    # Docker 配置（新增）
    ├── Dockerfile.backend
    ├── Dockerfile.frontend
    └── docker-compose.yml
```

## 7. 部署架构

```yaml
# docker-compose.yml
version: '3.8'

services:
  # 前端
  frontend:
    build:
      context: ./frontend
      dockerfile: ../docker/Dockerfile.frontend
    ports:
      - "3000:3000"
    environment:
      - REACT_APP_API_URL=http://localhost:8000

  # 后端 API
  backend:
    build:
      context: .
      dockerfile: ./docker/Dockerfile.backend
    ports:
      - "8000:8000"
    depends_on:
      - redis
      - mysql
    environment:
      - DATABASE_URL=mysql://root:password@mysql:3306/qlib_hikyuu
      - REDIS_URL=redis://redis:6379

  # Celery Worker
  celery:
    build:
      context: .
      dockerfile: ./docker/Dockerfile.backend
    command: celery -A backend.tasks worker -l info
    depends_on:
      - redis
      - mysql

  # Redis
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  # MySQL
  mysql:
    image: mysql:8
    ports:
      - "3306:3306"
    environment:
      - MYSQL_ROOT_PASSWORD=password
      - MYSQL_DATABASE=qlib_hikyuu
    volumes:
      - mysql_data:/var/lib/mysql

  # Nginx（生产环境）
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl

volumes:
  mysql_data:
```

## 8. 实施步骤

### Step 1: 创建 API 层（1-2 周）
```bash
# 安装 FastAPI
pip install fastapi uvicorn redis celery

# 创建基础 API
mkdir -p backend/api
touch backend/api/main.py

# 启动开发服务器
uvicorn backend.api.main:app --reload
```

### Step 2: 构建前端（2-3 周）
```bash
# 创建 React 应用
npx create-react-app frontend --template typescript
cd frontend
npm install antd axios @reduxjs/toolkit recharts

# 启动开发服务器
npm start
```

### Step 3: 集成测试（1 周）
```bash
# 运行集成测试
pytest tests/integration/test_web_api.py

# 性能测试
locust -f tests/performance/locustfile.py
```

### Step 4: 部署（3-5 天）
```bash
# 构建 Docker 镜像
docker-compose build

# 启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f
```

## 9. 性能优化建议

### 9.1 后端优化
- **使用连接池**：数据库和 Redis 连接池
- **异步处理**：长时间任务使用 Celery
- **缓存策略**：Redis 缓存热点数据
- **分页加载**：大数据集分页返回

### 9.2 前端优化
- **虚拟滚动**：大列表使用虚拟滚动
- **懒加载**：路由和组件懒加载
- **数据缓存**：使用 Redux 缓存数据
- **WebWorker**：计算密集型任务

## 10. 安全考虑

### 10.1 认证授权
```python
# 使用 JWT 认证
from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    # 验证 JWT token
    user = verify_token(token)
    if not user:
        raise HTTPException(status_code=401)
    return user
```

### 10.2 数据安全
- **HTTPS**：生产环境强制 HTTPS
- **CORS**：严格配置跨域策略
- **Rate Limiting**：API 限流
- **SQL 注入防护**：使用 ORM

## 11. 总结

### 不需要重构的理由
1. ✅ 现有代码模块化良好
2. ✅ 业务逻辑可以直接复用
3. ✅ 只需添加 Web 层，不改核心

### 需要新增的部分
1. 📦 API 层（FastAPI）
2. 🎨 前端应用（React）
3. 📊 数据库设计
4. 🔄 异步任务队列
5. 🚀 部署配置

### 实施建议
- **渐进式开发**：先 API，后前端
- **保持兼容**：CLI 和 Web 并存
- **测试驱动**：确保质量
- **文档先行**：API 文档自动生成

---
更新时间：2025-10-18