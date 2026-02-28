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

`StockAnalysisRunRequest` 新增可选字段 `skill_id`，可显式指定 agent skill（兼容默认 `stock` 映射）。

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

## 9. 配置示例

### 9.1 完整配置（`config/settings.yaml`）

```yaml
analysis:
  default_provider: openai_compatible
  default_model: gpt-4
  providers:
    # Mock provider（测试用）
    - id: mock
      enabled: true
      auth_mode: none
    
    # OpenAI Compatible provider
    - id: openai_compatible
      enabled: true
      auth_mode: api_key
      base_url: https://api.openai.com/v1
      models:
        - gpt-4
        - gpt-4-turbo
        - gpt-3.5-turbo
    
    # Codex App Server provider（OAuth）
    - id: codex_app_server
      enabled: false
      auth_mode: chatgpt_oauth
      base_url: http://localhost:8080
      models:
        - codex-default
```

### 9.2 Provider 配置说明

| Provider | 认证模式 | 说明 | 适用场景 |
|----------|----------|------|----------|
| `mock` | `none` | 返回模拟数据 | 测试、开发 |
| `openai_compatible` | `api_key` | OpenAI API 兼容服务 | 生产环境 |
| `codex_app_server` | `chatgpt_oauth` | ChatGPT OAuth 登录 | 企业内网 |

### 9.3 认证模式说明

| 认证模式 | 凭据类型 | 存储方式 |
|----------|----------|----------|
| `none` | 无需凭据 | - |
| `api_key` | API Key | 加密存储在 `analysis_provider_secrets` |
| `chatgpt_oauth` | Access Token + Refresh Token | 加密存储在 `analysis_provider_accounts` |

## 10. OAuth 流程说明

### 10.1 OAuth 登录流程

```text
┌─────────┐                    ┌─────────┐                    ┌─────────┐
│  前端   │                    │  后端   │                    │ ChatGPT │
└────┬────┘                    └────┬────┘                    └────┬────┘
     │                              │                              │
     │  1. 点击登录                 │                              │
     │ ───────────────────────────> │                              │
     │                              │                              │
     │  2. POST /api/providers/{id}/auth/start                    │
     │ ───────────────────────────> │                              │
     │                              │                              │
     │                              │  3. 生成 OAuth state         │
     │                              │  存储到 analysis_provider_auth_states
     │                              │                              │
     │  4. 返回 OAuth URL           │                              │
     │ <─────────────────────────── │                              │
     │                              │                              │
     │  5. 跳转到 ChatGPT 授权页面  │                              │
     │ ───────────────────────────────────────────────────────────>│
     │                              │                              │
     │  6. 用户授权                 │                              │
     │ <─────────────────────────────────────────────────────────── │
     │                              │                              │
     │  7. 重定向到 callback URL    │                              │
     │ ───────────────────────────> │                              │
     │                              │                              │
     │                              │  8. 验证 state，交换 token   │
     │                              │ ─────────────────────────────>│
     │                              │                              │
     │                              │  9. 返回 access_token        │
     │                              │ <─────────────────────────────│
     │                              │                              │
     │                              │  10. 加密存储 token          │
     │                              │                              │
     │  11. 返回登录成功            │                              │
     │ <─────────────────────────── │                              │
     │                              │                              │
```

### 10.2 OAuth API 端点

#### 发起 OAuth 登录

```bash
POST /api/providers/analysis/codex_app_server/auth/start

# 响应
{
  "auth_url": "https://chatgpt.com/oauth/authorize?...",
  "state": "random_state_string"
}
```

#### OAuth 回调

```bash
GET /api/providers/analysis/codex_app_server/auth/callback?code=xxx&state=xxx

# 响应
{
  "status": "success",
  "user_email": "user@example.com"
}
```

#### 查询登录状态

```bash
GET /api/providers/analysis/codex_app_server/auth/status

# 响应
{
  "logged_in": true,
  "user_email": "user@example.com",
  "expires_at": "2024-02-15T10:30:00Z"
}
```

#### 退出登录

```bash
POST /api/providers/analysis/codex_app_server/auth/logout

# 响应
{
  "status": "success"
}
```

### 10.3 Token 刷新机制

```python
def refresh_access_token(provider_id: str) -> str:
    """
    刷新 OAuth access token
    
    1. 从数据库读取 encrypted_refresh_token
    2. 解密 refresh_token
    3. 调用 OAuth provider 刷新接口
    4. 加密存储新的 access_token 和 refresh_token
    5. 返回新的 access_token
    """
    pass
```

## 11. API 使用示例

### 11.1 保存 API Key

```bash
curl -X PUT http://localhost:8000/api/providers/analysis/openai_compatible/secret \
  -H "Content-Type: application/json" \
  -d '{"api_key": "sk-xxx"}'
```

### 11.2 设置默认 Provider

```bash
curl -X PUT http://localhost:8000/api/providers/analysis/default \
  -H "Content-Type: application/json" \
  -d '{
    "provider_id": "openai_compatible",
    "model": "gpt-4"
  }'
```

### 11.3 获取 Provider 状态

```bash
curl -X GET http://localhost:8000/api/providers/analysis

# 响应
[
  {
    "id": "mock",
    "enabled": true,
    "auth_mode": "none",
    "status": "ready"
  },
  {
    "id": "openai_compatible",
    "enabled": true,
    "auth_mode": "api_key",
    "status": "ready",
    "models": ["gpt-4", "gpt-3.5-turbo"],
    "has_secret": true
  },
  {
    "id": "codex_app_server",
    "enabled": false,
    "auth_mode": "chatgpt_oauth",
    "status": "not_configured",
    "has_account": false
  }
]
```

### 11.4 运行个股分析

```bash
curl -X POST http://localhost:8000/api/analysis/stocks/AAPL/run \
  -H "Content-Type: application/json" \
  -d '{
    "provider_id": "openai_compatible",
    "model": "gpt-4",
    "skill_id": "stock_analysis"
  }'
```

## 12. 凭据解析流程

```python
def resolve_credentials(
    provider_id: str,
    model: str,
    db_url: str
) -> Tuple[str, str, Optional[str], Optional[str]]:
    """
    解析 provider 凭据
    
    Args:
        provider_id: Provider ID
        model: 模型名称
        db_url: 数据库 URL
    
    Returns:
        (provider_id, model, api_key, access_token)
    
    Raises:
        ProviderNotFoundError: Provider 不存在
        ValidationError: 凭据未配置
    """
    # 1. 获取 provider 配置
    provider = get_provider_config(provider_id)
    
    # 2. 根据认证模式获取凭据
    if provider.auth_mode == "none":
        return provider_id, model, None, None
    
    elif provider.auth_mode == "api_key":
        secret = get_provider_secret(provider_id, db_url)
        api_key = decrypt_text(secret.encrypted_api_key)
        return provider_id, model, api_key, None
    
    elif provider.auth_mode == "chatgpt_oauth":
        account = get_provider_account(provider_id, db_url)
        access_token = decrypt_text(account.encrypted_access_token)
        
        # 检查是否需要刷新
        if account.token_expires_at < datetime.now():
            access_token = refresh_access_token(provider_id)
        
        return provider_id, model, None, access_token
```

## 13. 与其他模块的交互

### 13.1 与 agent 模块

- analysis 模块通过 `AgentService` 调用 agent 子包
- `resolve_credentials()` 为 agent 提供统一的凭据解析接口

### 13.2 与 reports 模块

- reports 模块复用 `resolve_credentials()` 获取分析凭据
- 共享 provider 配置和凭据管理

### 13.3 与 news_listener 模块

- news_listener 模块调用 `analyze_news_alert_batch()` 批量分析告警
- 使用配置的分析 provider 和 model
