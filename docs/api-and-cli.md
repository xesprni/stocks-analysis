# API + CLI + 配置

## API 层（market_reporter/api/）

FastAPI 路由层，所有 protected 路由通过 `Depends(auth_required)` 守卫。

### 代码结构

```
api/
├── __init__.py              # create_app() 工厂函数，CORS，lifecycle events
├── deps.py                  # 依赖注入（get_db, get_config, auth_required 等）
├── auth.py                  # JWT 认证（login/refresh/logout）
├── errors.py                # 统一异常处理
├── health.py                # 健康检查（无需认证）
├── config.py                # 配置读写 (GET/PUT /api/config)
├── dashboard.py             # 仪表盘数据
├── stocks.py                # 行情接口（search, quote, kline, curve）
├── news_feed.py             # 新闻聚合
├── news_sources.py          # 新闻源 CRUD
├── providers.py             # AI Provider 管理（secrets, OAuth, models）
├── reports.py               # 报告生成与管理
├── analysis.py              # 个股分析
├── stock_analysis_tasks.py  # 异步分析任务
├── skills.py                # Skill 目录 CRUD
├── users.py                 # 用户管理（Admin）
└── watchlist.py             # 自选股 CRUD
```

### API 端点一览

#### 认证与用户

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | JWT 登录 |
| POST | `/api/auth/refresh` | 刷新 Token |
| POST | `/api/auth/logout` | 登出 |
| GET | `/api/users` | 用户列表（Admin） |
| POST | `/api/users` | 创建用户（Admin） |
| PATCH | `/api/users/{user_id}` | 更新用户 |
| POST | `/api/users/{user_id}/reset-password` | 重置密码 |

#### 行情

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/stocks/search` | 股票搜索 |
| GET | `/api/stocks/{symbol}/quote` | 单股报价 |
| POST | `/api/stocks/quotes` | 批量报价 |
| GET | `/api/stocks/{symbol}/kline` | K 线数据 |
| GET | `/api/stocks/{symbol}/curve` | 分时数据 |

#### 新闻

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/news-sources` | 新闻源列表 |
| POST | `/api/news-sources` | 添加新闻源 |
| PATCH | `/api/news-sources/{id}` | 更新新闻源 |
| DELETE | `/api/news-sources/{id}` | 删除新闻源 |
| GET | `/api/news-feed` | 新闻列表 |
| GET | `/api/news-feed/options` | 新闻选项 |

#### 报告与分析

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/reports/run` | 同步生成报告 |
| POST | `/api/reports/run/async` | 异步生成报告 |
| GET | `/api/reports/tasks` | 任务列表 |
| GET | `/api/reports/tasks/{task_id}` | 任务状态 |
| GET | `/api/reports` | 报告列表 |
| GET | `/api/reports/{run_id}` | 报告详情 |
| GET | `/api/reports/{run_id}/markdown` | 报告 Markdown |
| DELETE | `/api/reports/{run_id}` | 删除报告 |
| POST | `/api/analysis/stocks/{symbol}/run` | 同步分析 |
| POST | `/api/analysis/stocks/{symbol}/run/async` | 异步分析 |
| GET | `/api/analysis/stocks/runs` | 分析记录列表 |
| GET | `/api/analysis/stocks/runs/{run_id}` | 分析详情 |
| DELETE | `/api/analysis/stocks/runs/{run_id}` | 删除分析 |

#### Provider / Skill / Watchlist / Dashboard / Config

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/providers/analysis` | Provider 列表 |
| PUT | `/api/providers/analysis/{id}/secret` | 保存 API Key |
| DELETE | `/api/providers/analysis/{id}/secret` | 删除 API Key |
| POST | `/api/providers/analysis/{id}/auth/start` | OAuth 开始 |
| GET | `/api/providers/analysis/{id}/auth/callback` | OAuth 回调 |
| GET | `/api/providers/analysis/{id}/models` | 模型列表 |
| GET/PUT | `/api/config` | 全局配置 |
| GET/POST/PATCH/DELETE | `/api/watchlist` | 自选股 CRUD |
| GET | `/api/dashboard/snapshot` | 仪表盘快照 |
| GET/POST/PATCH/DELETE | `/api/skills` | Skill CRUD |
| GET | `/api/health` | 健康检查 |

### 应用工厂（create_app）

```python
def create_app() -> FastAPI:
    # CORS 配置
    # Lifecycle events（启动时 init_db + seed_news_sources + init_default_admin）
    # 挂载所有 router
    # 静态文件（frontend/dist）
    # 异常处理器
```

### 认证流程

1. `POST /api/auth/login` → 校验 bcrypt → 返回 JWT access + refresh token
2. 每个请求通过 `Depends(auth_required)` 从 `Authorization: Bearer <token>` 提取并验证 JWT
3. `auth_required` 注入当前 `user_id` 到路由函数
4. Admin-only 路由额外检查 `user.is_admin`

## CLI（market_reporter/cli.py）

基于 `Typer` 的命令行工具。

### 命令结构

```
market-reporter
├── serve              # 启动 API 服务 (--reload, --host, --port)
├── run                # 生成报告 (--mode, --symbol, --market, --skill-id)
├── init-config        # 初始化配置文件
├── db
│   └── init           # 初始化数据库
├── analyze
│   └── stock          # 个股分析 (--symbol, --market)
├── watchlist
│   ├── list           # 列出自选股
│   ├── add            # 添加 (--symbol, --market, --alias)
│   └── remove         # 移除 (--item-id)
├── providers
│   ├── list           # 列出 provider
│   └── check          # 检查连通性 (--provider, --model)
├── user
│   ├── create         # 创建用户
│   ├── list           # 用户列表
│   └── reset-password # 重置密码
└── auth
    ├── enable         # 开启 JWT 认证
    └── disable        # 关闭 JWT 认证
```

## 配置系统

### 三层配置

| 层级 | 文件/位置 | 说明 |
|------|-----------|------|
| 环境变量 | `MARKET_REPORTER_*` | 最高优先级，`AppSettings`（`settings.py`） |
| YAML 文件 | `config/settings.yaml` | 业务配置，`AppConfig`（`config.py`） |
| 用户覆盖 | `user_configs` 表 | 用户级配置，`UserConfigStore` |

### AppSettings（settings.py）

```python
class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MARKET_REPORTER_")
    config_file: str = "config/settings.yaml"
    frontend_dist: str = "frontend/dist"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    auth_enabled: bool = True
    jwt_secret_key: str = "change-me"
    default_admin_password: Optional[str] = None
```

使用 `pydantic-settings`，环境变量前缀 `MARKET_REPORTER_`，支持 `.env` 文件。

### AppConfig（config.py）

```python
class AppConfig(BaseModel):
    modules: ModulesConfig        # 各模块默认 provider
    analysis: AnalysisConfig      # AI 分析 provider 列表 + 默认值
    agent: AgentConfig            # max_steps, max_tool_calls, consistency_tolerance
    dashboard: DashboardConfig    # 指数配置
    longbridge: LongbridgeConfig  # Longbridge 凭证
    telegram: TelegramConfig      # Telegram 通知
    database: DatabaseConfig      # SQLite URL
    news_limit: int = 50
    flow_periods: int = 5
    timezone: str = "Asia/Shanghai"
    request_timeout_seconds: int = 30
    output_root: str = "output"
    user_agent: str = "..."
```

`ConfigStore` 负责 YAML 读写；`UserConfigStore` 负责用户级覆盖（存储在 `user_configs` 表的 `config_json` 字段中）。

### 共享 Schemas（schemas.py）

```python
class RunRequest(BaseModel)          # 报告运行请求
class RunResult(BaseModel)           # 报告运行结果
class ReportRunSummary(BaseModel)    # 报告摘要
class ReportRunDetail(BaseModel)     # 报告详情（含 markdown + raw_data）
class ReportRunTaskView(BaseModel)   # 异步任务状态视图
class ReportTaskStatus(str, Enum)    # PENDING / RUNNING / SUCCEEDED / FAILED
```
