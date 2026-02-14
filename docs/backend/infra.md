# 基础设施层（DB / HTTP / 安全）

## 1. 数据库层（`market_reporter/infra/db`）

## 1.1 表模型（`models.py`）

主要 SQLModel 表：

- watchlist：`watchlist_items`
- 行情缓存：`stock_kline_bars`、`stock_curve_points`
- provider 凭据：`analysis_provider_secrets`、`analysis_provider_accounts`
- OAuth state：`analysis_provider_auth_states`
- 个股分析运行历史：`stock_analysis_runs`
- 新闻监听：`news_listener_runs`、`watchlist_news_alerts`
- 新闻源：`news_sources`

## 1.2 Session 与建表（`session.py`）

- `get_engine(url)`：按 URL 缓存 engine。
- `init_db(url)`：`create_all` + SQLite 兼容列补齐。
- `session_scope(url)`：事务上下文（commit/rollback/close）。
- `seed_news_sources(url, sources)`：表空时种子数据。

## 1.3 Repository（`repos.py`）

提供细粒度 repo 类：

- `WatchlistRepo`
- `MarketDataRepo`
- `AnalysisProviderSecretRepo`
- `AnalysisProviderAccountRepo`
- `AnalysisProviderAuthStateRepo`
- `StockAnalysisRunRepo`
- `NewsListenerRunRepo`
- `WatchlistNewsAlertRepo`

风格：短事务 + flush/refresh，避免在 service 层直接拼 SQL。

## 2. HTTP 访问层（`infra/http/client.py`）

`HttpClient` 是异步上下文客户端封装：

- 统一 timeout 与 User-Agent
- `get_text/get_json`
- JSON 解析失败时尝试提取首尾 `{}` 片段回退

主要被 `news`、`fund_flow` 等 provider 复用。

## 3. 安全与密钥（`infra/security`）

## 3.1 对称加密（`crypto.py`）

- 算法：AES-GCM（256 bit）
- `encrypt_text` 输出：`ciphertext_b64 + nonce_b64`
- `decrypt_text` 用于调用前临时解密

## 3.2 主密钥存储（`keychain_store.py`）

优先级：

1. 明确配置的主密钥文件（`MARKET_REPORTER_MASTER_KEY_FILE`）
2. 系统 Keychain（`keyring`）
3. Keychain 不可用时回退到主密钥文件

异常统一包装为 `SecretStorageError`。

## 4. 基础设施设计要点

- 业务层不直接依赖第三方 SDK 细节，通过 repo/client 进行隔离。
- 凭据持久化只存密文，不存明文。
- SQLite 兼容迁移采用“启动补列”策略，避免首次运行失败。
