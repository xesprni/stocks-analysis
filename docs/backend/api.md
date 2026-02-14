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
