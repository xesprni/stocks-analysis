# 后端技术文档

本目录用于沉淀 `market_reporter` 后端的模块化技术文档，按“基础层 + 业务模块”组织。

## 文档索引

- [后端架构总览](./backend/architecture.md)
- [API 层设计与端点清单](./backend/api.md)
- [Core 与配置系统](./backend/core_and_config.md)
- [基础设施层（DB/HTTP/安全）](./backend/infra.md)

### 业务模块（`market_reporter/modules`）

- [watchlist 模块](./backend/modules/watchlist.md)
- [news 模块](./backend/modules/news.md)
- [news_listener 模块](./backend/modules/news_listener.md)
- [market_data 模块](./backend/modules/market_data.md)
- [symbol_search 模块](./backend/modules/symbol_search.md)
- [fund_flow 模块](./backend/modules/fund_flow.md)
- [analysis 模块](./backend/modules/analysis.md)（含 agent 子包）
- [agent 子包](./backend/modules/agent.md)
- [reports 模块](./backend/modules/reports.md)
- [dashboard 模块](./backend/modules/dashboard.md)

## 使用指南

1. **阅读顺序建议**：从架构总览开始，理解系统分层，然后按基础层→业务模块顺序阅读
2. **配置参考**：所有模块的默认配置可在 `config/settings.yaml` 中查看
3. **API 调试**：使用 `/api/options/ui` 端点获取可选参数列表
4. **调试模式**：启用 `mock` provider 可在无外部依赖情况下测试功能

## 约定

- 术语中的“模块”默认指 `market_reporter/modules/*` 下子模块。
- API 路由统一挂载在 `/api/*`。
- 当前后端默认数据库为 SQLite（`data/market_reporter.db`）。
