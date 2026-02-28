# 基础设施层（DB / HTTP / 安全）

## 1. 数据库层（`market_reporter/infra/db`）

### 1.1 表模型（`models.py`）

主要 SQLModel 表：

- watchlist：`watchlist_items`
- 行情缓存：`stock_kline_bars`、`stock_curve_points`
- provider 凭据：`analysis_provider_secrets`、`analysis_provider_accounts`
- OAuth state：`analysis_provider_auth_states`
- 个股分析运行历史：`stock_analysis_runs`
- 新闻监听：`news_listener_runs`、`watchlist_news_alerts`
- 新闻源：`news_sources`

### 1.2 Session 与建表（`session.py`）

- `get_engine(url)`：按 URL 缓存 engine。
- `init_db(url)`：`create_all` + SQLite 兼容列补齐。
- `session_scope(url)`：事务上下文（commit/rollback/close）。
- `seed_news_sources(url, sources)`：表空时种子数据。

### 1.3 Repository（`repos.py`）

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

### 3.1 对称加密（`crypto.py`）

- 算法：AES-GCM（256 bit）
- `encrypt_text` 输出：`ciphertext_b64 + nonce_b64`
- `decrypt_text` 用于调用前临时解密

### 3.2 主密钥存储（`keychain_store.py`）

优先级：

1. 明确配置的主密钥文件（`MARKET_REPORTER_MASTER_KEY_FILE`）
2. 系统 Keychain（`keyring`）
3. Keychain 不可用时回退到主密钥文件

异常统一包装为 `SecretStorageError`。

## 4. 基础设施设计要点

- 业务层不直接依赖第三方 SDK 细节，通过 repo/client 进行隔离。
- 凭据持久化只存密文，不存明文。
- SQLite 兼容迁移采用"启动补列"策略，避免首次运行失败。

## 5. 数据库 Schema 详细说明

### 5.1 watchlist_items 表

```sql
CREATE TABLE watchlist_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(20) NOT NULL,
    market VARCHAR(10) NOT NULL,
    display_name VARCHAR(100),
    alias VARCHAR(100),
    keywords_json TEXT,  -- JSON 数组格式存储关键词
    enabled BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, market)
);
```

**字段说明**：
- `symbol`: 股票代码（如 `AAPL`, `0700`, `000001`）
- `market`: 市场标识（`CN`/`HK`/`US`）
- `display_name`: 显示名称
- `alias`: 别名（用于新闻匹配）
- `keywords_json`: 关键词 JSON 数组（如 `["苹果", "iPhone"]`）

### 5.2 stock_kline_bars 表

```sql
CREATE TABLE stock_kline_bars (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(20) NOT NULL,
    market VARCHAR(10) NOT NULL,
    interval VARCHAR(10) NOT NULL,  -- 1d, 1h, 5m, 1m
    time DATETIME NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    source VARCHAR(50),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, market, interval, time)
);
```

### 5.3 stock_curve_points 表

```sql
CREATE TABLE stock_curve_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol VARCHAR(20) NOT NULL,
    market VARCHAR(10) NOT NULL,
    time DATETIME NOT NULL,
    price REAL NOT NULL,
    volume REAL,
    source VARCHAR(50),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, market, time)
);
```

### 5.4 news_sources 表

```sql
CREATE TABLE news_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL,
    url VARCHAR(500) NOT NULL,
    source_type VARCHAR(20) DEFAULT 'rss',
    enabled BOOLEAN DEFAULT TRUE,
    priority INTEGER DEFAULT 0,
    last_fetch_at DATETIME,
    last_error TEXT,
    error_count INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 5.5 news_listener_runs 表

```sql
CREATE TABLE news_listener_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id VARCHAR(50) NOT NULL UNIQUE,
    started_at DATETIME NOT NULL,
    finished_at DATETIME,
    status VARCHAR(20) DEFAULT 'running',
    news_count INTEGER DEFAULT 0,
    alert_count INTEGER DEFAULT 0,
    error TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 5.6 watchlist_news_alerts 表

```sql
CREATE TABLE watchlist_news_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id VARCHAR(50) NOT NULL,
    watchlist_item_id INTEGER NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    market VARCHAR(10) NOT NULL,
    display_name VARCHAR(100),
    severity VARCHAR(20),  -- low, medium, high
    matched_keywords TEXT,
    price_change_percent REAL,
    news_title TEXT,
    news_link TEXT,
    news_published DATETIME,
    analysis_summary TEXT,
    analysis_markdown TEXT,
    status VARCHAR(20) DEFAULT 'UNREAD',  -- UNREAD, READ, DISMISSED
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 5.7 analysis_provider_secrets 表

```sql
CREATE TABLE analysis_provider_secrets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id VARCHAR(50) NOT NULL UNIQUE,
    encrypted_api_key TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 5.8 analysis_provider_accounts 表

```sql
CREATE TABLE analysis_provider_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id VARCHAR(50) NOT NULL UNIQUE,
    encrypted_access_token TEXT,
    encrypted_refresh_token TEXT,
    token_expires_at DATETIME,
    user_email VARCHAR(100),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 5.9 stock_analysis_runs 表

```sql
CREATE TABLE stock_analysis_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id VARCHAR(50) NOT NULL UNIQUE,
    symbol VARCHAR(20) NOT NULL,
    market VARCHAR(10) NOT NULL,
    provider_id VARCHAR(50),
    model VARCHAR(100),
    skill_id VARCHAR(50),
    input_json TEXT,
    output_json TEXT,
    markdown TEXT,
    confidence REAL,
    status VARCHAR(20) DEFAULT 'completed',
    error TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## 6. 数据库迁移策略

### 6.1 启动时自动迁移

系统采用"启动补列"策略，在 `init_db()` 时自动处理：

```python
def init_db(url: str) -> None:
    engine = get_engine(url)
    SQLModel.metadata.create_all(engine)
    
    # SQLite 兼容：补充新增列
    with Session(engine) as session:
        _add_missing_columns(session, "stock_analysis_runs", ["skill_id"])
        _add_missing_columns(session, "watchlist_news_alerts", ["analysis_markdown"])
```

### 6.2 迁移原则

| 原则 | 说明 |
|------|------|
| 向后兼容 | 新增字段必须有默认值或允许 NULL |
| 无破坏性 | 不执行 DROP TABLE 或 DROP COLUMN |
| 幂等性 | 多次执行 `init_db` 结果一致 |
| 渐进式 | 新版本可平滑升级，无需停机 |

### 6.3 版本升级流程

```text
1. 备份数据库（SQLite 直接复制文件）
2. 部署新版本代码
3. 启动应用，自动执行 init_db()
4. 验证新功能正常
```

### 6.4 数据迁移示例

#### 从 YAML 迁移新闻源到 SQLite

```python
# 首次启动时，若 news_sources 表为空，自动从 YAML 迁移
def seed_news_sources(url: str, sources: List[dict]) -> None:
    with session_scope(url) as session:
        count = session.exec(select(NewsSource)).all()
        if not count:
            for src in sources:
                session.add(NewsSource(**src))
```

## 7. 数据库连接池配置

### 7.1 SQLite 配置

```python
# 默认配置
engine = create_engine(
    "sqlite:///data/market_reporter.db",
    connect_args={"check_same_thread": False},  # 多线程支持
    pool_pre_ping=True,  # 连接健康检查
)
```

### 7.2 PostgreSQL 配置（可选）

```python
# 生产环境推荐
engine = create_engine(
    "postgresql://user:pass@localhost/market_reporter",
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    pool_recycle=3600,
)
```
