# analysis_engine 模块

## 1. 模块职责

统一分析引擎入口，负责：

- provider 状态与凭据管理
- OAuth 登录状态管理
- 个股分析执行与落库
- 市场总览/监听告警批量分析

## 2. 核心文件

- `market_reporter/modules/analysis_engine/service.py`
- `market_reporter/modules/analysis_engine/schemas.py`
- `market_reporter/modules/analysis_engine/prompt_builder.py`
- providers:
  - `mock_provider.py`
  - `openai_compatible_provider.py`
  - `codex_app_server_provider.py`

## 3. Provider 管理

- provider 类型：`mock/openai_compatible/codex_app_server`
- 认证模式：`none/api_key/chatgpt_oauth`
- 状态计算维度：
  - enabled
  - models 是否存在
  - base_url 是否必要且已配置
  - secret/account 是否就绪

## 4. 凭据与安全

- API key：加密后存 `analysis_provider_secrets`
- OAuth 账户：加密后存 `analysis_provider_accounts`
- OAuth state：`analysis_provider_auth_states`（防重放、过期）
- 主密钥：`KeychainStore`（Keychain 或文件回退）

## 5. 执行路径

## 5.1 个股分析

`run_stock_analysis()` 流程：

1. 选择 provider + model
2. 解析凭据（api_key/access_token）
3. 构建 `AgentService` 并执行工具链
4. 转换为 `AnalysisInput + AnalysisOutput`
5. 持久化到 `stock_analysis_runs`

## 5.2 市场概览

`analyze_market_overview(news_items, flow_series)`

- 构造 `AnalysisInput(symbol="MARKET")`
- 直接调用 provider 分析

## 5.3 监听批量告警

`analyze_news_alert_batch(candidates)`

- 构造 watchlist listener 专用 payload
- 尝试从 `output.raw.alerts` 提取结构化结果
- 不足条目时自动补齐，保证与候选条数一致

## 6. 提示词构建

`prompt_builder.py` 支持两类 system prompt：

- 个股分析
- 市场总览/监听模式

并包含：

- 技术指标摘要
- 新闻分类摘要
- 资金流摘要
- 基础形态与风险提示

## 7. 历史记录接口

- `list_history/list_recent_history`
- `get_history_item`
- `delete_history_item`

落库字段包含：输入 JSON、输出 JSON、markdown。
