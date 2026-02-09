# Market Reporter Pro

面向股票研究与资讯跟踪的本地化系统，支持：

1. 新闻源管理、新闻聚合与监听告警
2. A/H/US 资金流与个股行情（搜索、报价、K 线、分时曲线）
3. Watchlist 管理（支持关键词）
4. 多 Provider / 多 Model 分析引擎（Mock / OpenAI 兼容 / Codex App）
5. 报告生成（同步/异步）与历史查看

## 架构

```text
market_reporter/
  api/                       # FastAPI 路由层
  core/                      # 协议、类型、注册器、错误定义
  modules/
    news/                    # 新闻采集
    news_listener/           # 新闻监听与告警
    symbol_search/           # 股票搜索
    market_data/             # 行情模块（akshare/yfinance/composite）
    fund_flow/               # 资金流模块
    watchlist/               # watchlist 服务
    analysis_engine/         # 模型分析引擎
    reports/                 # 报告生成与任务管理
  infra/
    db/                      # SQLModel + repository
    http/                    # HTTP 适配
    security/                # Keychain + AES-GCM
  services/                  # 配置存储等基础服务
  cli.py                     # Typer CLI

frontend/
  src/pages/                 # Dashboard / NewsFeed / AlertCenter / Watchlist / StockTerminal / Providers / Reports
  src/components/charts/     # CandlestickChart / TradeCurveChart
```

## 快速开始

### 1) 安装依赖

```bash
UV_CACHE_DIR=.uv-cache uv sync
```

### 2) 初始化配置与数据库

```bash
UV_CACHE_DIR=.uv-cache uv run market-reporter init-config
UV_CACHE_DIR=.uv-cache uv run market-reporter db init
```

默认配置文件：`config/settings.yaml`

### 3) 启动后端

```bash
UV_CACHE_DIR=.uv-cache uv run market-reporter serve --reload
```

### 4) 启动前端

```bash
cd frontend
npm install
npm run dev
```

## CLI 常用命令

```bash
# 报告
UV_CACHE_DIR=.uv-cache uv run market-reporter run

# watchlist
UV_CACHE_DIR=.uv-cache uv run market-reporter watchlist list
UV_CACHE_DIR=.uv-cache uv run market-reporter watchlist add --symbol AAPL --market US
UV_CACHE_DIR=.uv-cache uv run market-reporter watchlist remove --item-id 1

# 分析 provider
UV_CACHE_DIR=.uv-cache uv run market-reporter providers list
UV_CACHE_DIR=.uv-cache uv run market-reporter providers set-default --provider mock --model market-default

# 个股分析
UV_CACHE_DIR=.uv-cache uv run market-reporter analyze stock --symbol AAPL --market US
```

## API 概览

- 健康与配置：
  - `GET /api/health`
  - `GET /api/options/ui`
  - `GET /api/config`
  - `PUT /api/config`
- 报告：
  - `POST /api/reports/run`
  - `POST /api/reports/run/async`
  - `GET /api/reports/tasks`
  - `GET /api/reports/tasks/{task_id}`
  - `GET /api/reports`
  - `GET /api/reports/{run_id}`
  - `GET /api/reports/{run_id}/markdown`
  - `DELETE /api/reports/{run_id}`
- 新闻：
  - `GET /api/news-sources`
  - `POST /api/news-sources`
  - `PATCH /api/news-sources/{source_id}`
  - `DELETE /api/news-sources/{source_id}`
  - `GET /api/news-feed/options`
  - `GET /api/news-feed`
  - `POST /api/news-listener/run`
  - `GET /api/news-listener/runs`
  - `GET /api/news-alerts`
  - `PATCH /api/news-alerts/{alert_id}`
  - `POST /api/news-alerts/mark-all-read`
- 行情与分析：
  - `GET /api/stocks/search`
  - `GET /api/stocks/{symbol}/quote`
  - `GET /api/stocks/{symbol}/kline`
  - `GET /api/stocks/{symbol}/curve`
  - `POST /api/analysis/stocks/{symbol}/run`
  - `POST /api/analysis/stocks/{symbol}/run/async`
  - `GET /api/analysis/stocks/tasks/{task_id}`
  - `GET /api/analysis/stocks/{symbol}/history`
- Watchlist 与 Provider：
  - `GET /api/watchlist`
  - `POST /api/watchlist`
  - `PATCH /api/watchlist/{item_id}`
  - `DELETE /api/watchlist/{item_id}`
  - `GET /api/providers/analysis`
  - `PUT /api/providers/analysis/default`
  - `PUT /api/providers/analysis/{provider_id}/secret`
  - `DELETE /api/providers/analysis/{provider_id}/secret`
  - `POST /api/providers/analysis/{provider_id}/auth/login`
  - `POST /api/providers/analysis/{provider_id}/auth/logout`
  - `GET /api/providers/analysis/{provider_id}/auth/url`
  - `GET /api/providers/analysis/{provider_id}/auth/status`
  - `DELETE /api/providers/analysis/{provider_id}`

## 安全

- Provider API Key 不写入 YAML。
- API Key 加密后保存到 SQLite。
- 主密钥默认保存在 macOS Keychain：
  - service: `market-reporter`
  - account: `master-key`

## 注意

1. 免费行情源可能存在延迟或限频。
2. 在无外网环境下，网络型 provider 会失败并返回告警。
