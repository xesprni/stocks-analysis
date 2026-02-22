# Market Reporter Pro

面向股票研究与资讯跟踪的本地化系统，提供行情、新闻、监听告警、LLM 分析与报告工作流。

## 当前状态（2026-02-13）

1. Agent 指标计算改为 `ta-lib -> pandas-ta -> builtin` 自动回退，不因环境缺少 TA 库中断。
2. Agent 新闻检索升级为扩展词匹配，且支持无命中时返回近期财经新闻兜底。
3. Stock Terminal 任务状态与结果独立到 `Stock Results` 页面，结果使用 Markdown 报告展示（非 JSON 直出）。
4. Config 页面改为分区保存（基础配置 / 模块默认配置 / Dashboard 配置），不再顶部“一键全局保存”。
5. Dashboard 监控总览拆分为异步并发加载（指标与 watchlist 分离渲染）。

## 核心能力

1. 新闻源管理、新闻聚合、监听告警与告警中心。
2. A/H/US 行情能力：搜索、单股报价、批量报价、K 线、分时曲线。
3. Watchlist 管理（含 alias / display_name / keywords）。
4. 多 Provider / 多 Model 分析引擎（mock / openai_compatible / codex_app_server）。
5. 报告生成与历史回看（市场报告 + 个股分析，均支持异步任务）。

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
    analysis/                # 统一分析模块（含 agent 子包）
      agent/                 # agent 工具链（价格/基本面/财报/新闻/联网检索/指标/宏观）
    reports/                 # 报告生成与任务管理
  infra/
    db/                      # SQLModel + repository
    http/                    # HTTP 适配
    security/                # Keychain + AES-GCM
  services/                  # 配置存储等基础服务
  cli.py                     # Typer CLI

frontend/
  src/pages/                 # Dashboard / Run Reports / Config / NewsFeed / Watchlist / StockTerminal / StockResults / AlertCenter / Reports
  src/components/charts/     # CandlestickChart / TradeCurveChart / Report charts
```

## 快速开始

### 1) 安装依赖

```bash
UV_CACHE_DIR=.uv-cache uv sync
```

### TA-Lib（可选）

1. 项目支持 TA-Lib，但它是可选依赖。
2. 若未安装 TA-Lib（或 `pandas-ta`），指标链路会自动回退到内置算法，不影响主流程。
3. 若希望优先使用 TA-Lib，请先安装系统级 TA-Lib，再安装 Python 包。

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

前端默认地址：`http://127.0.0.1:5173`，开发代理到 `http://127.0.0.1:8000/api`。

### 5) 构建前端并由后端托管（可选）

```bash
cd frontend
npm run build
```

构建产物默认在 `frontend/dist`，后端会自动挂载静态文件。

## Docker Compose 部署

### 0) 前置条件

1. 本机已安装并启动 Docker（Docker Desktop 或 Docker Engine）。
2. 在项目根目录执行命令（即包含 `docker-compose.yml` 的目录）。

### 1) 首次启动（构建镜像并启动服务）

```bash
docker compose up -d --build
```

启动后访问：`http://127.0.0.1:8000`

### 2) 日常启动（不重建镜像）

```bash
docker compose up -d
```

### 3) 查看状态 / 日志

```bash
docker compose ps
docker compose logs -f market-reporter
```

### 4) 停止服务

```bash
docker compose down
```

### 5) 代码更新后重建

```bash
docker compose up -d --build
```

### 6) 持久化目录

`docker-compose.yml` 已挂载以下目录到容器内：

1. `./config -> /app/config`
2. `./data -> /app/data`
3. `./output -> /app/output`

其中 `MARKET_REPORTER_MASTER_KEY_FILE=/app/data/master_key.b64` 用于容器环境下主密钥文件回退（当系统 keyring 不可用时）。

### 7) 容器内 Codex CLI（用于 `codex_app_server`）

镜像已内置 `codex` CLI，并挂载持久化目录 `codex_home:/root/.codex`。

```bash
# 查看版本
docker compose exec market-reporter codex --version

# 首次登录（按终端提示完成）
docker compose exec market-reporter codex login
```

登录成功后，`codex_app_server` provider 可在容器内直接调用。

## 数据库（当前实现）

### 存储位置与配置

1. 默认数据库：`SQLite`
2. 默认文件：`data/market_reporter.db`
3. 配置项：`config/settings.yaml -> database.url`

示例：

```yaml
database:
  url: sqlite:///data/market_reporter.db
```

### 初始化与建表策略

1. `UV_CACHE_DIR=.uv-cache uv run market-reporter db init` 初始化数据库。
2. 后端启动时也会执行建表检查。
3. 当前不使用 Alembic，采用 `SQLModel.metadata.create_all(...)`。
4. SQLite 启动时会补齐 `watchlist_items.display_name` 与 `watchlist_items.keywords_json` 兼容字段。

### 首次启动数据

1. 若旧 YAML 中存在 `news_sources`，会迁移到数据库。
2. 若不存在，则写入系统默认新闻源。

### 常见操作

```bash
# 查看表
sqlite3 data/market_reporter.db ".tables"

# 备份数据库
cp data/market_reporter.db data/market_reporter_$(date +%Y%m%d_%H%M%S).db

# 重建数据库（会丢失数据）
rm -f data/market_reporter.db
UV_CACHE_DIR=.uv-cache uv run market-reporter db init
```

## 前端页面（当前）

1. `Dashboard`：监控总览，指数和 watchlist 异步并发加载。
2. `Run Reports`：运行市场/个股报告任务。
3. `Config`：基础配置、模块默认配置、Dashboard 配置、新闻源与 Provider 管理。
4. `News Feed`：新闻聚合浏览。
5. `Watchlist`：股票列表维护与检索。
6. `Stock Terminal`：盘中图表 + 异步发起个股分析。
7. `Stock Results`：查看个股分析任务状态与 Markdown 报告。
8. `Alert Center`：监听运行记录、告警处理。
9. `Reports`：市场报告任务状态、历史与详情。

## Agent 行为说明（当前）

### Skills 抽象

1. Agent 与 Report 执行链已支持 skill 注册与分发，不再在主流程中硬编码 mode 分支。
2. 兼容旧调用：未传 `skill_id` 时仍按 `mode` 自动映射。
3. 可选显式字段：
   - `RunRequest.skill_id`（报告 skill）
   - `StockAnalysisRunRequest.skill_id` / `AgentRunRequest.skill_id`（agent skill）

### 技术指标后端自动回退

1. 后端优先级固定：`ta-lib -> pandas-ta -> builtin`。
2. `IndicatorsResult.source` 可能为：
   - `ta-lib/computed`
   - `pandas-ta/computed`
   - `builtin/computed`
3. 无论 TA 三方库是否安装，都会保留内置算法兜底，产出结构化指标字段。

### 新闻检索策略

1. Stock 模式会组合检索词：`query + ticker + 去后缀 ticker + 公司别名(shortName/longName/displayName)`。
2. ticker 采用单词边界匹配，名称采用大小写不敏感包含匹配。
3. 匹配文本范围：`title + source + category + content`。
4. 若严格匹配为空，会返回日期范围内最新财经新闻（最多 limit），并追加 warning：
   - `no_news_matched`
   - `news_fallback_recent_headlines`

## API 概览（当前实现）

### 健康 / 配置 / Dashboard

1. `GET /api/health`
2. `GET /api/options/ui`
3. `GET /api/config`
4. `PUT /api/config`
5. `GET /api/dashboard/snapshot`
6. `GET /api/dashboard/indices`
7. `GET /api/dashboard/watchlist`
8. `PUT /api/dashboard/auto-refresh`

### 报告（market / stock report）

1. `POST /api/reports/run`
2. `POST /api/reports/run/async`
3. `GET /api/reports/tasks`
4. `GET /api/reports/tasks/{task_id}`
5. `GET /api/reports`
6. `GET /api/reports/{run_id}`
7. `GET /api/reports/{run_id}/markdown`
8. `DELETE /api/reports/{run_id}`

### 个股分析（Stock Terminal / Stock Results）

1. `POST /api/analysis/stocks/{symbol}/run`
2. `POST /api/analysis/stocks/{symbol}/run/async`
3. `GET /api/analysis/stocks/tasks`
4. `GET /api/analysis/stocks/tasks/{task_id}`
5. `GET /api/analysis/stocks/runs`
6. `GET /api/analysis/stocks/runs/{run_id}`
7. `GET /api/analysis/stocks/{symbol}/history`
8. `DELETE /api/analysis/stocks/runs/{run_id}`

### 行情与搜索

1. `GET /api/stocks/search`
2. `GET /api/stocks/{symbol}/quote`
3. `POST /api/stocks/quotes`
4. `GET /api/stocks/{symbol}/kline`
5. `GET /api/stocks/{symbol}/curve`

### 新闻与监听

1. `GET /api/news-sources`
2. `POST /api/news-sources`
3. `PATCH /api/news-sources/{source_id}`
4. `DELETE /api/news-sources/{source_id}`
5. `GET /api/news-feed/options`
6. `GET /api/news-feed`
7. `POST /api/news-listener/run`
8. `GET /api/news-listener/runs`
9. `GET /api/news-alerts`
10. `PATCH /api/news-alerts/{alert_id}`
11. `POST /api/news-alerts/mark-all-read`

### Watchlist

1. `GET /api/watchlist`
2. `POST /api/watchlist`
3. `PATCH /api/watchlist/{item_id}`
4. `DELETE /api/watchlist/{item_id}`

### Analysis Provider

1. `GET /api/providers/analysis`
2. `PUT /api/providers/analysis/default`
3. `PUT /api/providers/analysis/{provider_id}/secret`
4. `DELETE /api/providers/analysis/{provider_id}/secret`
5. `POST /api/providers/analysis/{provider_id}/auth/start`
6. `GET /api/providers/analysis/{provider_id}/auth/status`
7. `GET /api/providers/analysis/{provider_id}/auth/callback`
8. `POST /api/providers/analysis/{provider_id}/auth/logout`
9. `GET /api/providers/analysis/{provider_id}/models`
10. `DELETE /api/providers/analysis/{provider_id}`

## CLI 常用命令

```bash
# 报告
UV_CACHE_DIR=.uv-cache uv run market-reporter run

# watchlist
UV_CACHE_DIR=.uv-cache uv run market-reporter watchlist list
UV_CACHE_DIR=.uv-cache uv run market-reporter watchlist add --symbol AAPL --market US
UV_CACHE_DIR=.uv-cache uv run market-reporter watchlist remove --item-id 1

# provider
UV_CACHE_DIR=.uv-cache uv run market-reporter providers list
UV_CACHE_DIR=.uv-cache uv run market-reporter providers set-default --provider mock --model market-default

# 个股分析
UV_CACHE_DIR=.uv-cache uv run market-reporter analyze stock --symbol AAPL --market US
```

## 测试建议

```bash
# 最近改动的关键回归
UV_CACHE_DIR=.uv-cache uv run pytest -q \
  tests/test_compute_tools_backend_selection.py \
  tests/test_news_tools_search_matching.py \
  tests/test_agent_orchestrator_* \
  tests/test_stock_analysis_results_api.py \
  tests/test_dashboard_api_snapshot.py

# 更完整回归（与 agent/news/compute 相关）
UV_CACHE_DIR=.uv-cache uv run pytest -q tests/test_compute_tools_* tests/test_agent_orchestrator_* tests/test_news_*
```

## 安全

1. Provider API Key 不写入 YAML。
2. API Key 加密后保存到 SQLite。
3. 主密钥默认保存在 macOS Keychain：
   - service: `market-reporter`
   - account: `master-key`

## 注意

1. 免费行情源可能存在延迟或限频。
2. 在无外网环境下，网络型 provider 会失败并返回告警。
3. `market` 参数校验为 `CN|HK|US`：
   - `GET /api/analysis/stocks/runs` 若不筛选市场，请省略 `market` 参数，不要传空字符串。
   - `GET /api/analysis/stocks/{symbol}/history` 的 `market` 为必填且必须是上述三值之一。

## VSCode / 本地开发

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# 1) 同步依赖
uv sync

# 2) 启动服务
uv run market-reporter serve --reload

# 3) 添加依赖
uv add fastapi httpx

# 4) 移除依赖
uv remove package-name

# 5) 安装开发依赖
uv sync --dev

# 6) 运行脚本
uv run python script.py

# 7) 执行测试
uv run pytest
```
