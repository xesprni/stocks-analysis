# Infra — 基础设施层

`market_reporter/infra/` 提供数据库访问、HTTP 客户端和加密存储三个基础设施模块。

## 代码结构

```
infra/
├── db/
│   ├── models.py       # SQLModel 表定义（14 张表）
│   ├── repos.py        # Repository 层（CRUD 封装）
│   └── session.py      # 引擎管理、session_scope、建表、种子数据
├── http/
│   └── client.py       # 异步 HTTP 客户端封装
└── security/
    ├── crypto.py        # AES-GCM 加密/解密
    └── keychain_store.py # 主密钥管理（环境变量/密钥链/文件）
```

## 数据库模型（models.py）

14 张 SQLModel 表，均使用 `table=True` 声明：

| 表名 | 用途 | 关键唯一约束 |
|------|------|-------------|
| `users` | 用户 | username |
| `api_keys` | API Key | key_hash |
| `watchlist_items` | 自选股 | user_id + symbol + market |
| `stock_kline_bars` | K 线缓存 | symbol + market + interval + ts |
| `stock_curve_points` | 分时缓存 | — |
| `analysis_provider_secrets` | Provider API Key | user_id + provider_id |
| `longbridge_credentials` | Longbridge 凭证 | user_id |
| `telegram_configs` | Telegram 配置 | user_id |
| `analysis_provider_accounts` | OAuth 账户 | user_id + provider_id |
| `analysis_provider_auth_states` | OAuth 状态 | state (unique) |
| `stock_analysis_runs` | 分析运行记录 | — |
| `news_sources` | 新闻源 | source_id |
| `user_configs` | 用户配置覆盖 | user_id |

**核心语法**：`SQLModel` 结合 Pydantic 验证和 SQLAlchemy ORM；`Field(foreign_key="users.id")` 声明外键；`UniqueConstraint` 在 `__table_args__` 中定义复合唯一约束。

## Repository 层（repos.py）

每个表对应一个 Repo 类，封装 CRUD 操作：

```python
class UserRepo:          # create, get, get_by_username, list_all, update, update_password, delete
class ApiKeyRepo:        # create, get_by_key_hash, list_by_user, deactivate, delete
class WatchlistRepo:     # list_all, list_enabled, add, get_by_symbol_market, update, delete
class MarketDataRepo:    # upsert_kline, save_curve_points, list_curve_points, list_kline
class AnalysisProviderSecretRepo:   # upsert, get, delete
class AnalysisProviderAccountRepo:  # upsert, get, delete
class LongbridgeCredentialRepo:     # upsert, get, delete
class TelegramConfigRepo:           # upsert, get, delete
class AnalysisProviderAuthStateRepo: # create, get_valid, mark_used, delete_expired
class StockAnalysisRunRepo:         # add, list_by_symbol, get, list_recent, delete
class UserConfigRepo:               # get, upsert, delete
```

所有 Repo 接受 `Session` 作为构造参数，由调用方控制事务生命周期。

**核心语法**：`self.session.exec(select(...).where(...)).first()` 是 SQLModel 查询模式；`self.session.flush()` 刷新到数据库但不提交；`self.session.refresh(obj)` 从数据库重新读取。

## Session 管理（session.py）

```python
# 获取引擎（带 LRU 缓存，每个 URL 复用同一引擎）
engine = get_engine(database_url)

# 初始化数据库（建表 + SQLite 列补齐）
init_db(database_url)

# 上下文管理器，自动提交/回滚
with session_scope(database_url) as session:
    repo = UserRepo(session)
    ...

# 种子数据
seed_news_sources(database_url, sources)

# 初始化默认管理员
init_default_admin(database_url, username, password) -> Optional[str]
```

`_ensure_sqlite_columns()` 在 SQLite 上检测并补齐缺失的列（兼容旧数据库）。`session_scope` 使用 context manager 模式保证事务原子性。

## HTTP 客户端（client.py）

```python
async with HttpClient(timeout_seconds=30, user_agent="market-reporter") as client:
    text = await client.get_text(url, params={...})
    data = await client.get_json(url, params={...})
```

- 基于 `httpx.AsyncClient`，支持自动重定向
- `get_json()` 在 JSON 解析失败时尝试提取 `{…}` 子串
- 必须作为 async context manager 使用

## 加密（crypto.py）

```python
key = generate_master_key()          # 生成 256-bit AES-GCM 密钥
ciphertext, nonce = encrypt_text(plaintext, key)
plaintext = decrypt_text(ciphertext, nonce, key)
```

使用 `cryptography.hazmat.primitives.ciphers.aead.AESGCM`，输出 base64 编码。

## 主密钥管理（keychain_store.py）

`KeychainStore` 按优先级获取或创建主密钥：

1. 环境变量 `MARKET_REPORTER_MASTER_KEY`（base64）
2. 主密钥文件（`data/master_key.b64`）
3. 系统 keyring（service=`market-reporter`, account=`master-key`）
4. 自动生成新密钥 → 尝试写入 keyring + 文件

```python
store = KeychainStore(master_key_file=..., database_url=...)
key = store.get_or_create_master_key()  # bytes (32-byte)
```

**核心语法**：`keyring.get_password()` / `keyring.set_password()` 跨平台安全存储；`os.chmod(path, 0o600)` 限制文件权限。
