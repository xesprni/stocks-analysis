# analysis 模块

## 1. 模块职责

统一分析入口（合并了原 `analysis_engine` 与 `agent` 模块），负责：

- provider 状态与凭据管理
- OAuth 登录状态管理
- 个股分析执行与落库（通过 agent 子包）
- 监听告警批量分析
- 凭据解析公共接口（`resolve_credentials()`）

## 2. 核心文件

- `market_reporter/modules/analysis/service.py`
- `market_reporter/modules/analysis/schemas.py`
- `market_reporter/modules/analysis/prompt_builder.py`
- providers:
  - `mock_provider.py`
  - `openai_compatible_provider.py`
  - `codex_app_server_provider.py`
- agent 子包（见 [agent 子包文档](./agent.md)）

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
- `resolve_credentials()` 公共方法：统一解析 provider 配置、model、api_key、access_token，供 `run_stock_analysis` 与 `reports` 模块复用

## 5. 执行路径

### 5.1 个股分析

`run_stock_analysis()` 流程：

1. 调用 `resolve_credentials()` 选择 provider + model + 凭据
2. 构建 `AgentService` 并执行工具链
3. 转换为 `AnalysisInput + AnalysisOutput`
4. 持久化到 `stock_analysis_runs`

### 5.2 监听批量告警

`analyze_news_alert_batch(candidates)`

- 构造 watchlist listener 专用 payload
- 尝试从 `output.raw.alerts` 提取结构化结果
- 不足条目时自动补齐，保证与候选条数一致

## 6. 提示词构建

`prompt_builder.py` 支持市场总览/监听模式 system prompt，包含：

- 新闻分类摘要
- 资金流摘要

## 7. 历史记录接口

- `list_history/list_recent_history`
- `get_history_item`
- `delete_history_item`

落库字段包含：输入 JSON、输出 JSON、markdown。

## 8. 共享工具

`market_reporter/core/utils.py` 中的 `parse_json()` 函数被本模块及 agent 子包多处复用，用于安全解析 LLM 返回的 JSON 文本。
