# 后端架构总览

## 1. 分层结构

```text
FastAPI Router (market_reporter/api)
    -> Service/Module 层 (market_reporter/modules, market_reporter/services)
        -> Core 协议与注册器 (market_reporter/core)
            -> Infra 适配层 (market_reporter/infra)
                -> 外部系统 (SQLite / RSS / yfinance / akshare / OpenAI / Codex)
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
