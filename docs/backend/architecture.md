# 后端架构总览

## 1. 分层结构

```text
FastAPI Router (market_reporter/api)
    -> Service/Module 层 (market_reporter/modules, market_reporter/services)
        -> Core 协议与注册器 (market_reporter/core)
            -> Infra 适配层 (market_reporter/infra)
                -> 外部系统 (SQLite / RSS / yfinance / akshare / OpenAI / Codex)
```

## 1.1 模块依赖关系图

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                              API Layer                                       │
│  health | config | dashboard | watchlist | stocks | news | reports | analysis│
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Service/Module Layer                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │Dashboard │  │Watchlist │  │ Reports  │  │ Analysis │  │   News   │       │
│  │ Service  │  │ Service  │  │ Service  │  │ Service  │  │ Listener │       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘       │
│       │             │             │             │             │              │
│       └─────────────┴──────┬──────┴─────────────┴─────────────┘              │
│                            ▼                                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
│  │ Market   │  │  News    │  │ FundFlow │  │ Symbol   │  │  Agent   │       │
│  │  Data    │  │ Service  │  │ Service  │  │ Search   │  │ Service  │       │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘       │
└───────┼─────────────┼─────────────┼─────────────┼─────────────┼─────────────┘
        │             │             │             │             │
        ▼             ▼             ▼             ▼             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Core Layer                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  Contracts   │  │    Types     │  │   Registry   │  │    Errors    │     │
│  │ (Protocols)  │  │   (DTOs)     │  │  (Providers) │  │  (Exceptions)│     │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Infrastructure Layer                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   Database   │  │    HTTP      │  │   Security   │  │   Provider   │     │
│  │  (SQLModel)  │  │   Client     │  │  (AES-GCM)   │  │  Implementations│  │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            External Systems                                  │
│  SQLite | RSS Feeds | yfinance | akshare | Longbridge | OpenAI | Codex     │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 1.2 核心数据流

### 个股分析数据流

```text
用户请求 → API(/api/analysis/stocks/{symbol}/run)
         → AnalysisService.run_stock_analysis()
         → AgentService.run()
            ├→ tools.get_price_history() → MarketDataService
            ├→ tools.get_fundamentals_info() → Longbridge SDK
            ├→ tools.search_news() → NewsService
            ├→ tools.compute_indicators() → ComputeTools
            └→ LLM Provider (OpenAI/Codex/Mock)
         → 持久化到 stock_analysis_runs 表
         → 返回 AnalysisOutput
```

### 新闻监听告警流

```text
定时调度 → NewsListenerScheduler
         → NewsListenerService.run_listener()
            ├→ WatchlistService.list_enabled_items()
            ├→ NewsService.collect() → RSS Provider
            ├→ Matcher.find_symbol_news_matches()
            ├→ MarketDataService.get_curve() + get_quote()
            ├→ 计算窗口涨跌幅
            └→ AnalysisService.analyze_news_alert_batch()
         → 持久化到 news_listener_runs + watchlist_news_alerts
         → 前端轮询 /api/news-alerts
```

### 报告生成数据流

```text
用户请求 → API(/api/reports/run)
         → ReportService.run_report()
            ├→ NewsService.collect()
            ├→ FundFlowService.collect()
            ├→ AgentService.run() (market skill)
            └→ ReportFormatter.format()
         → 写入 output/<run_id>/
            ├→ report.md
            ├→ raw_data.json
            └→ meta.json
```

## 2. 入口与生命周期

- 应用入口：`market_reporter/api/__init__.py` 中 `create_app()`。
- 启动阶段：
  - 加载配置（`ConfigStore.load()`）。
  - 初始化数据库（`init_db`）。
  - 新闻源迁移（YAML -> SQLite，仅首轮表空时）。
  - 启动新闻监听调度器（`NewsListenerScheduler`）。
- 关闭阶段：
  - 停止调度器。
  - 取消 in-memory 个股分析异步任务（`StockAnalysisTaskManager.cancel_all()`）。

## 3. 核心运行机制

- Provider 可插拔：统一由 `ProviderRegistry` 注册与解析。
- 模块服务编排：
  - `NewsService`, `FundFlowService`, `MarketDataService` 提供数据能力。
  - `AnalysisService` 聚合行情/新闻/资金流并调用 LLM Provider。
  - `AgentService/AgentOrchestrator` 负责多工具链推理与报告拼装。
- 数据持久化：通过 `session_scope` + repo 模式访问 SQLModel。

## 4. 关键降级策略

- 行情：provider 失败后回退本地缓存（K 线、曲线），再失败返回 `source=unavailable` 占位。
- 指标：`ta-lib -> pandas-ta -> builtin` 自动回退。
- 新闻：新闻源失败转 warning，不阻断上游流程；可自动禁用故障源。
- 分析：LLM 结构化输出失败时生成可用的 fallback `AnalysisOutput`。
- 监听告警：模型失败时按规则生成降级告警摘要。

## 5. 主要状态存储

- 配置：`config/settings.yaml`（含模块默认配置、provider 列表等）。
- 数据库：`data/market_reporter.db`。
- 报告产物：`output/<run_id>/{report.md,raw_data.json,meta.json}`。
- provider 凭据：DB 中密文 + 本地主密钥（Keychain 或文件回退）。
