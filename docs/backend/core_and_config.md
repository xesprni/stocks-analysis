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
