# API 层设计与端点清单

## 1. Router 组织

- 统一前缀：`/api`
- Router 文件位于 `market_reporter/api/*.py`
- 依赖注入入口：`market_reporter/api/deps.py`

## 2. 端点分组

### 2.1 健康与配置

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| GET | `/api/options/ui` | UI 可选项（市场、周期、provider 等） |
| GET | `/api/config` | 读取完整配置 |
| PUT | `/api/config` | 更新配置并尝试重启新闻监听调度器 |

### 2.2 Dashboard

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/dashboard/snapshot` | 指数 + watchlist 聚合快照 |
| GET | `/api/dashboard/indices` | 指数快照 |
| GET | `/api/dashboard/watchlist` | watchlist 快照（分页） |
| PUT | `/api/dashboard/auto-refresh` | 更新自动刷新开关 |

### 2.3 Watchlist

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/watchlist` | 列表 |
| POST | `/api/watchlist` | 新增 |
| PATCH | `/api/watchlist/{item_id}` | 更新别名/开关/关键词 |
| DELETE | `/api/watchlist/{item_id}` | 删除 |

### 2.4 行情与搜索

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/stocks/search` | 股票搜索（ALL/CN/HK/US） |
| GET | `/api/stocks/{symbol}/quote` | 单股报价 |
| POST | `/api/stocks/quotes` | 批量报价 |
| GET | `/api/stocks/{symbol}/kline` | K 线 |
| GET | `/api/stocks/{symbol}/curve` | 分时曲线 |

### 2.5 新闻源与新闻流

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/news-sources` | 新闻源列表（DB） |
| POST | `/api/news-sources` | 新增新闻源 |
| PATCH | `/api/news-sources/{source_id}` | 更新新闻源 |
| DELETE | `/api/news-sources/{source_id}` | 删除新闻源 |
| GET | `/api/news-feed/options` | 新闻源选项 |
| GET | `/api/news-feed` | 聚合新闻流（可按 source_id） |

### 2.6 新闻监听与告警

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/news-listener/run` | 手动执行一轮监听 |
| GET | `/api/news-listener/runs` | 监听运行历史 |
| GET | `/api/news-alerts` | 告警列表 |
| PATCH | `/api/news-alerts/{alert_id}` | 更新告警状态 |
| POST | `/api/news-alerts/mark-all-read` | 批量标记已读 |

### 2.7 报告任务（market/stock）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/reports/run` | 同步生成报告 |
| POST | `/api/reports/run/async` | 异步启动报告任务 |
| GET | `/api/reports/tasks` | 任务列表 |
| GET | `/api/reports/tasks/{task_id}` | 任务详情 |
| GET | `/api/reports` | 报告列表 |
| GET | `/api/reports/{run_id}` | 报告详情 |
| GET | `/api/reports/{run_id}/markdown` | 仅 markdown 内容 |
| DELETE | `/api/reports/{run_id}` | 删除报告目录 |

### 2.8 个股分析（Stock Terminal）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/analysis/stocks/{symbol}/run` | 同步运行个股分析 |
| POST | `/api/analysis/stocks/{symbol}/run/async` | 异步运行个股分析 |
| GET | `/api/analysis/stocks/tasks` | 个股分析任务列表 |
| GET | `/api/analysis/stocks/tasks/{task_id}` | 个股分析任务详情 |
| GET | `/api/analysis/stocks/runs` | 历史运行记录 |
| GET | `/api/analysis/stocks/runs/{run_id}` | 单次运行详情 |
| DELETE | `/api/analysis/stocks/runs/{run_id}` | 删除历史运行 |
| GET | `/api/analysis/stocks/{symbol}/history` | 指定 symbol 历史 |

### 2.9 分析 Provider 管理

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/providers/analysis` | Provider 状态列表 |
| PUT | `/api/providers/analysis/default` | 设置默认 provider/model |
| PUT | `/api/providers/analysis/{provider_id}/secret` | 保存 API Key |
| DELETE | `/api/providers/analysis/{provider_id}/secret` | 删除 API Key |
| POST | `/api/providers/analysis/{provider_id}/auth/start` | 发起 OAuth 登录 |
| GET | `/api/providers/analysis/{provider_id}/auth/status` | 查询登录状态 |
| GET | `/api/providers/analysis/{provider_id}/auth/callback` | OAuth 回调 |
| POST | `/api/providers/analysis/{provider_id}/auth/logout` | 退出登录 |
| GET | `/api/providers/analysis/{provider_id}/models` | 查询模型列表 |
| DELETE | `/api/providers/analysis/{provider_id}` | 删除 provider 配置 |

## 3. API 设计要点

- API 层保持轻逻辑：参数校验 + 组装 service + 异常转换。
- 强依赖统一从 `ConfigStore` 读取最新配置，避免使用过期状态。
- 长任务采用内存任务管理：
  - 报告任务：`ReportService._tasks`
  - 个股分析任务：`StockAnalysisTaskManager._tasks`
- 部分端点在请求时显式 `init_db`，确保数据库 schema 已就绪。

## 4. 响应格式与示例

### 4.1 统一响应结构

所有 API 返回 JSON 格式，成功响应直接返回数据对象或数组：

```json
{
  "id": 1,
  "symbol": "AAPL",
  "market": "US",
  "display_name": "Apple Inc.",
  "enabled": true
}
```

列表接口返回数组：

```json
[
  {"id": 1, "symbol": "AAPL", "market": "US", ...},
  {"id": 2, "symbol": "0700", "market": "HK", ...}
]
```

### 4.2 分页响应

分页接口（如 watchlist 快照）返回结构：

```json
{
  "items": [...],
  "total": 100,
  "page": 1,
  "page_size": 20
}
```

### 4.3 典型响应示例

#### 报价响应 (`GET /api/stocks/{symbol}/quote`)

```json
{
  "symbol": "AAPL",
  "market": "US",
  "price": 178.52,
  "change": 2.35,
  "change_percent": 1.33,
  "volume": 52340000,
  "source": "yfinance",
  "timestamp": "2024-01-15T21:00:00Z"
}
```

#### K线响应 (`GET /api/stocks/{symbol}/kline`)

```json
{
  "symbol": "AAPL",
  "market": "US",
  "interval": "1d",
  "bars": [
    {
      "time": "2024-01-15",
      "open": 176.17,
      "high": 179.23,
      "low": 175.82,
      "close": 178.52,
      "volume": 52340000
    }
  ],
  "source": "yfinance"
}
```

#### 新闻流响应 (`GET /api/news-feed`)

```json
[
  {
    "id": "abc123",
    "title": "Apple announces new product",
    "link": "https://example.com/news/1",
    "source_name": "Reuters",
    "published": "2024-01-15T10:30:00Z",
    "summary": "Apple Inc. announced..."
  }
]
```

#### 告警响应 (`GET /api/news-alerts`)

```json
[
  {
    "id": 1,
    "symbol": "AAPL",
    "market": "US",
    "display_name": "Apple Inc.",
    "severity": "high",
    "matched_keywords": ["Apple", "iPhone"],
    "price_change_percent": 3.5,
    "news_title": "Apple announces record sales",
    "analysis_summary": "正面利好，建议关注...",
    "status": "UNREAD",
    "created_at": "2024-01-15T10:30:00Z"
  }
]
```

#### 报告任务响应 (`GET /api/reports/tasks/{task_id}`)

```json
{
  "task_id": "task_abc123",
  "status": "SUCCEEDED",
  "run_id": "20240115_103000",
  "created_at": "2024-01-15T10:30:00Z",
  "finished_at": "2024-01-15T10:35:00Z",
  "error": null
}
```

## 5. 错误码与异常处理

### 5.1 HTTP 状态码

| 状态码 | 含义 | 场景 |
|--------|------|------|
| 200 | 成功 | 请求正常处理 |
| 400 | 请求错误 | 参数校验失败、JSON 解析错误 |
| 404 | 未找到 | 资源不存在（如 symbol、report） |
| 409 | 冲突 | 资源已存在（如重复添加 watchlist） |
| 500 | 服务器错误 | 内部异常、provider 执行失败 |

### 5.2 错误响应格式

```json
{
  "detail": "错误描述信息"
}
```

### 5.3 常见错误示例

#### 参数校验失败 (400)

```json
{
  "detail": "Invalid market: must be one of ['CN', 'HK', 'US']"
}
```

#### 资源不存在 (404)

```json
{
  "detail": "Report not found: run_id=20240101_000000"
}
```

#### 资源冲突 (409)

```json
{
  "detail": "Watchlist item already exists: symbol=AAPL, market=US"
}
```

#### Provider 执行失败 (500)

```json
{
  "detail": "Provider execution failed: yfinance timeout"
}
```

### 5.4 业务异常类型

| 异常类型 | HTTP 映射 | 说明 |
|----------|-----------|------|
| `ValidationError` | 400 | 参数校验失败 |
| `ProviderNotFoundError` | 400 | 指定的 provider 不存在 |
| `ProviderExecutionError` | 500 | provider 执行异常 |
| `SecretStorageError` | 500 | 密钥存储操作失败 |
