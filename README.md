# Market Reporter

金融政策新闻聚合 + A股/港股/美股行情资金流分析平台，提供 FastAPI 管理后台和 AI Agent 驱动的研报生成。

## 核心能力

- 新闻源管理与 RSS 新闻聚合
- A/H/US 行情：搜索、报价、K 线、分时曲线
- Watchlist 管理（含 alias / display_name / keywords）
- 多 Provider / 多 Model AI 分析引擎（OpenAI Compatible）
- Agent 驱动的报告生成（市场 / 个股 / 持仓），支持异步任务
- Skill 文档懒加载：从 `skills/*/SKILL.md` 动态加载
- 可选 Telegram 报告完成推送

## 快速开始

### 安装依赖

```bash
uv sync
```

### TA-Lib（可选）

技术指标链路优先级：`ta-lib → pandas-ta → builtin`。未安装 TA 库时自动回退到内置算法，不影响主流程。

### 初始化

```bash
uv run market-reporter init-config
uv run market-reporter db init
```

### 启动后端

```bash
uv run market-reporter serve --reload
```

默认监听 `0.0.0.0:8000`。

### 启动前端

```bash
cd frontend
npm install
npm run dev
```

前端默认地址 `http://127.0.0.1:5173`，开发代理到 `http://127.0.0.1:8000/api`。

### 构建前端（可选）

```bash
cd frontend && npm run build
```

构建产物位于 `frontend/dist`，后端自动挂载静态文件。

## 架构

```
market_reporter/
├── api/                  # FastAPI 路由层（JWT 认证）
├── core/                 # 协议接口、类型定义、Provider 注册器
├── modules/
│   ├── analysis/         # AI 分析引擎
│   │   └── agent/        # Agent 系统（orchestrator → runtime → tools）
│   ├── reports/          # 报告生成与任务管理
│   ├── market_data/      # 行情（Longbridge / Yahoo Finance / AKShare）
│   ├── news/             # RSS 新闻采集
│   ├── fund_flow/        # 资金流（东方财富 / FRED）
│   ├── symbol_search/    # 股票搜索
│   ├── dashboard/        # 仪表盘
│   └── watchlist/        # 自选股管理
├── infra/
│   ├── db/               # SQLModel + repository
│   ├── http/             # HTTP 客户端
│   └── security/         # AES-GCM 加密 + 系统密钥链
├── services/             # 配置存储、Telegram 通知等
├── cli.py                # Typer CLI
frontend/                 # React SPA (Vite + TailwindCSS)
skills/                   # Agent skill 定义（SKILL.md）
tests/                    # pytest 测试
```

### Agent 系统

报告生成通过 Agent 系统执行：

1. **ReportService** 接收请求，解析 skill，构建上下文
2. **ReportSkill** 调用 `AgentService.run()`
3. **AgentService** 组装 ToolRegistry + AgentOrchestrator
4. **AgentOrchestrator** 执行循环：构建 prompt → LLM function calling → 执行工具 → 重复直到产出最终报告
5. **AgentGuardrails** 校验结果，计算 confidence
6. **AgentReportFormatter** 格式化最终报告

### Provider 体系

5 类 Provider 通过 Protocol 接口定义：

- **NewsProvider** → RSS
- **FundFlowProvider** → 东方财富, FRED
- **MarketDataProvider** → Longbridge, Yahoo Finance, AKShare
- **AnalysisProvider** → OpenAI Compatible
- **SymbolSearchProvider** → Longbridge, AKShare, YFinance, Finnhub

## 前端页面

| 页面 | 说明 |
|------|------|
| Dashboard | 监控总览，指数和 watchlist 异步加载 |
| Run Reports | 运行市场 / 个股报告 |
| Reports | 报告任务状态、历史与详情 |
| News Feed | 新闻聚合浏览 |
| Watchlist | 自选股管理 |
| Stock Terminal | 盘中图表（报价 / K 线 / 分时） |
| Config | 配置管理、新闻源、Provider |
| Providers | AI Provider 管理 |
| Skills | Skill 目录浏览 |
| Users | 用户管理（Admin） |

## Docker 部署

### 启动

```bash
docker compose up -d --build
```

访问 `http://127.0.0.1:8000`。

### 日常操作

```bash
docker compose ps                    # 查看状态
docker compose logs -f market-reporter  # 查看日志
docker compose down                  # 停止
docker compose up -d --build         # 更新重建
```

### 持久化

Docker Compose 挂载：`config/`、`data/`、`output/`。

密钥获取顺序：环境变量 `MARKET_REPORTER_MASTER_KEY` → `MARKET_REPORTER_MASTER_KEY_FILE` → 系统密钥链。

### 运维脚本

```bash
./bin/deploy.sh    # 部署
./bin/restart.sh   # 重启
./bin/stop.sh      # 停止
./bin/update.sh    # 更新重建
./bin/status.sh    # 状态
./bin/logs.sh 300  # 日志
```

非 Docker 本地脚本：`deploy-local.sh`、`restart-local.sh`、`stop-local.sh`、`update-local.sh`、`status-local.sh`、`logs-local.sh`。

## CLI 命令

```bash
uv run market-reporter serve --reload                  # 启动服务
uv run market-reporter run --mode market               # 市场报告
uv run market-reporter run --mode stock --symbol AAPL --market US  # 个股报告
uv run market-reporter analyze stock --symbol 00700 --market HK    # 个股分析
uv run market-reporter watchlist list/add/remove       # 自选股管理
uv run market-reporter providers list/check            # Provider 管理
uv run market-reporter user create/list/reset-password # 用户管理
uv run market-reporter db init                         # 初始化数据库
uv run market-reporter auth enable/disable             # 认证开关
```

## 测试

```bash
uv run pytest                              # 全部测试
uv run pytest tests/test_agent_orchestrator_*  # Agent 相关
uv run pytest tests/test_report_service.py     # 报告服务
```

## 数据库

- 默认 SQLite，文件 `data/market_reporter.db`
- `SQLModel.metadata.create_all(...)` 建表，后端启动时自动检查
- Provider API Key 通过 AES-GCM 加密存储

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `MARKET_REPORTER_CONFIG_FILE` | `config/settings.yaml` | 配置文件路径 |
| `MARKET_REPORTER_FRONTEND_DIST` | `frontend/dist` | 前端构建产物路径 |
| `MARKET_REPORTER_API_HOST` | `0.0.0.0` | API 绑定地址 |
| `MARKET_REPORTER_API_PORT` | `8000` | API 端口 |
| `MARKET_REPORTER_AUTH_ENABLED` | `true` | JWT 认证开关 |
| `MARKET_REPORTER_JWT_SECRET_KEY` | - | JWT 签名密钥 |
| `MARKET_REPORTER_DEFAULT_ADMIN_PASSWORD` | 自动生成 | 初始 admin 密码 |

## 安全

- JWT 认证，bcrypt 密码哈希
- Provider API Key 不写入 YAML，加密存储在 SQLite
- 用户数据隔离（reports, watchlist, analysis runs 按 user_id 隔离）
- Admin 用户首次启动时自动创建
