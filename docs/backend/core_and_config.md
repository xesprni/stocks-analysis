# Core 与配置系统

## 1. Core 层

## 1.1 协议契约（`market_reporter/core/contracts.py`）

定义统一 Provider 协议，约束模块实现：

- `NewsProvider.collect(limit)`
- `FundFlowProvider.collect(periods)`
- `MarketDataProvider.get_quote/get_kline/get_curve`
- `AnalysisProvider.analyze(payload, model, api_key)`
- `SymbolSearchProvider.search(query, market, limit)`

## 1.2 类型系统（`market_reporter/core/types.py`）

核心跨模块 DTO：

- 行情：`Quote`、`KLineBar`、`CurvePoint`
- 新闻：`NewsItem`
- 资金流：`FlowPoint`
- 分析输入输出：`AnalysisInput`、`AnalysisOutput`

这些类型在模块间传递，保证数据结构一致。

## 1.3 Provider 注册器（`market_reporter/core/registry.py`）

- `register(module, provider_id, factory)`：注册工厂。
- `resolve(module, provider_id, **kwargs)`：按模块 + id 创建 provider。
- `list_ids(module)`：列举可用 provider。

异常：provider 不存在时抛 `ProviderNotFoundError`。

## 1.4 错误体系（`market_reporter/core/errors.py`）

应用级错误基类 `MarketReporterError`，派生：

- `ProviderNotFoundError`
- `ProviderExecutionError`
- `SecretStorageError`
- `ValidationError`

## 2. 配置模型（`market_reporter/config.py`）

`AppConfig` 包含：

- 基础：`output_root`、`timezone`、`news_limit`、`flow_periods`
- 模块配置：`modules.news/fund_flow/market_data/news_listener/symbol_search`
- 分析配置：`analysis.providers/default_provider/default_model`
- 业务配置：`watchlist`、`news_listener`、`symbol_search`、`dashboard`、`agent`
- 数据库配置：`database.url`

## 2.1 默认值

- 默认分析 provider：`mock`、`openai_compatible`、`codex_app_server`
- 默认新闻源与 FRED 序列内置在 `default_news_sources/default_fred_series`

## 2.2 配置规范化

`AppConfig.normalized()` + `ConfigStore` 负责路径与字段补齐。

## 3. 配置存储（`market_reporter/services/config_store.py`）

- `load()`：读取 YAML；若不存在则写入默认配置。
- `save(config)`：标准化后写回 YAML。
- `patch(patch_data)`：浅层合并后校验并保存。

关键保障：

- 自动规范 provider 列表（去重、补 auth_mode、确保至少一个 enabled）。
- 自动修复 analysis/agent/dashboard 缺失关键字段。
- 自动创建 data 目录（SQLite 场景）。

## 4. 运行时设置（`market_reporter/settings.py`）

环境变量前缀：`MARKET_REPORTER_`。

主要字段：

- `config_file`
- `frontend_dist`
- `api_host/api_port`
- `keychain_service_name/keychain_account_name`

## 5. 配置文件示例

### 5.1 完整配置示例 (`config/settings.yaml`)

```yaml
# 基础配置
output_root: output
timezone: Asia/Shanghai
news_limit: 50
flow_periods: 30

# 数据库配置
database:
  url: sqlite:///data/market_reporter.db

# 模块配置
modules:
  # 新闻模块
  news:
    providers:
      - id: rss
        enabled: true
  
  # 资金流模块
  fund_flow:
    providers:
      - id: eastmoney
        enabled: true
      - id: fred
        enabled: true
  
  # 行情数据模块
  market_data:
    default_provider: composite
    providers:
      - id: yfinance
        enabled: true
      - id: akshare
        enabled: true
      - id: composite
        enabled: true
  
  # 新闻监听模块
  news_listener:
    enabled: true
    interval_minutes: 30
    move_window_minutes: 60
    move_threshold_percent: 2.0
    max_news_per_cycle: 100
    analysis_provider: openai_compatible
    analysis_model: gpt-4
  
  # 股票搜索模块
  symbol_search:
    default_provider: composite
    providers:
      - id: yfinance
        enabled: true
      - id: akshare
        enabled: true
      - id: finnhub
        enabled: false
      - id: longbridge
        enabled: false

# 分析配置
analysis:
  default_provider: openai_compatible
  default_model: gpt-4
  providers:
    - id: mock
      enabled: true
      auth_mode: none
    - id: openai_compatible
      enabled: true
      auth_mode: api_key
      base_url: https://api.openai.com/v1
      models:
        - gpt-4
        - gpt-3.5-turbo
    - id: codex_app_server
      enabled: false
      auth_mode: chatgpt_oauth
      base_url: http://localhost:8080

# Watchlist 配置
watchlist:
  default_market_scope:
    - CN
    - HK
    - US

# Dashboard 配置
dashboard:
  auto_refresh_enabled: true
  auto_refresh_seconds: 60
  indices:
    - symbol: "000001"
      market: CN
      display_name: "上证指数"
    - symbol: "399001"
      market: CN
      display_name: "深证成指"
    - symbol: "^DJI"
      market: US
      display_name: "道琼斯"
    - symbol: "^GSPC"
      market: US
      display_name: "标普500"

# Agent 配置
agent:
  default_skill: stock_analysis
  runtime: openai_tools
  max_tool_iterations: 10
  guardrails:
    pe_consistency_check: true
    evidence_required: true
```

### 5.2 最小配置示例

```yaml
output_root: output
timezone: Asia/Shanghai

database:
  url: sqlite:///data/market_reporter.db

analysis:
  default_provider: mock
  providers:
    - id: mock
      enabled: true
      auth_mode: none
```

## 6. 环境变量说明

### 6.1 支持的环境变量

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `MARKET_REPORTER_CONFIG_FILE` | `config/settings.yaml` | 配置文件路径 |
| `MARKET_REPORTER_FRONTEND_DIST` | `frontend/dist` | 前端静态文件目录 |
| `MARKET_REPORTER_API_HOST` | `0.0.0.0` | API 监听地址 |
| `MARKET_REPORTER_API_PORT` | `8000` | API 监听端口 |
| `MARKET_REPORTER_KEYCHAIN_SERVICE_NAME` | `market_reporter` | Keychain 服务名 |
| `MARKET_REPORTER_KEYCHAIN_ACCOUNT_NAME` | `master_key` | Keychain 账户名 |
| `MARKET_REPORTER_MASTER_KEY_FILE` | - | 主密钥文件路径（优先级高于 Keychain） |

### 6.2 使用示例

```bash
# 指定配置文件
export MARKET_REPORTER_CONFIG_FILE=/path/to/config.yaml

# 指定 API 端口
export MARKET_REPORTER_API_PORT=3000

# 使用文件存储主密钥（跳过 Keychain）
export MARKET_REPORTER_MASTER_KEY_FILE=/secure/path/master.key

# 启动服务
python -m market_reporter
```

### 6.3 Docker 环境变量示例

```yaml
# docker-compose.yml
services:
  market_reporter:
    image: market_reporter:latest
    environment:
      - MARKET_REPORTER_API_HOST=0.0.0.0
      - MARKET_REPORTER_API_PORT=8000
      - MARKET_REPORTER_CONFIG_FILE=/app/config/settings.yaml
    volumes:
      - ./config:/app/config
      - ./data:/app/data
      - ./output:/app/output
```

## 7. 配置热更新

### 7.1 运行时更新

通过 API 更新配置：

```bash
# 更新配置
curl -X PUT http://localhost:8000/api/config \
  -H "Content-Type: application/json" \
  -d '{"news_listener": {"interval_minutes": 60}}'
```

### 7.2 配置更新影响范围

| 配置项 | 更新后行为 |
|--------|-----------|
| `news_listener.interval_minutes` | 重启调度器 |
| `news_listener.enabled` | 启动/停止调度器 |
| `analysis.default_provider` | 下次分析生效 |
| `dashboard.auto_refresh_enabled` | 立即生效 |
| `dashboard.indices` | 下次快照生效 |
