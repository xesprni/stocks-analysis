# Data Modules — 数据采集与管理模块

包含新闻聚合、资金流、股票搜索、自选股管理和仪表盘五个数据模块。

## 代码结构

```
modules/
├── news/                    # 新闻聚合
│   ├── service.py           # NewsService
│   ├── schemas.py           # NewsItem schema
│   └── providers/
│       └── rss_provider.py  # RSS 采集
├── fund_flow/               # 资金流
│   ├── service.py           # FundFlowService
│   └── providers/
│       ├── eastmoney_provider.py  # 东方财富
│       └── fred_provider.py       # FRED（美联储经济数据）
├── symbol_search/           # 股票搜索
│   ├── service.py           # SymbolSearchService
│   └── providers/
│       ├── longbridge_search_provider.py
│       ├── akshare_search_provider.py
│       ├── yfinance_search_provider.py
│       └── finnhub_search_provider.py
├── watchlist/               # 自选股
│   ├── service.py           # WatchlistService
│   └── schemas.py           # WatchlistItem, WatchlistCreateRequest 等
└── dashboard/               # 仪表盘
    ├── service.py           # DashboardService
    └── schemas.py           # DashboardSnapshot, IndexQuote 等
```

## 新闻模块（news/）

### NewsService

```python
class NewsService:
    async def collect(self, limit: int) -> Tuple[List[NewsItem], List[str]]
```

- 从数据库加载启用的 `NewsSource`，逐个通过 RSS Provider 采集
- 返回 `(news_items, warnings)`，warnings 包含采集失败的源
- 使用 `HttpClient` 异步获取 RSS feed

### RssProvider

实现 `NewsProvider` Protocol：

```python
class RssProvider:
    provider_id: str = "rss"
    async def collect(self, limit: int) -> List[NewsItem]
```

使用 `feedparser` 解析 RSS feed，将 `entry` 映射为 `NewsItem(source_id, category, source, title, link, published, content)`。

## 资金流模块（fund_flow/）

### FundFlowService

```python
class FundFlowService:
    async def collect(self, periods: int) -> Dict[str, List[FlowPoint]]
```

通过 ProviderRegistry 路由到具体 Provider。

### Providers

| Provider | 数据源 | 说明 |
|----------|--------|------|
| `eastmoney_provider.py` | 东方财富 | A 股北向资金、行业资金流 |
| `fred_provider.py` | FRED API | 美联储经济数据（利率、M2、CPI 等），使用 series_id 查询 |

`FlowPoint(market, series_key, series_name, date, value, unit)` 为通用数据点模型。

## 股票搜索模块（symbol_search/）

### SymbolSearchService

```python
class SymbolSearchService:
    async def search(query, market, limit) -> List[dict]
```

通过 ProviderRegistry 路由，支持 4 个搜索源：

| Provider | 特点 |
|----------|------|
| `longbridge_search_provider` | Longbridge API，精确搜索 |
| `akshare_search_provider` | AKShare，A 股为主 |
| `yfinance_search_provider` | Yahoo Finance |
| `finnhub_search_provider` | Finnhub API |

## 自选股模块（watchlist/）

### WatchlistService

```python
class WatchlistService:
    def list_items(user_id) -> List[WatchlistItem]
    def list_enabled_items(user_id) -> List[WatchlistItem]
    def add_item(symbol, market, alias, display_name, keywords, user_id) -> WatchlistItem
    def update_item(item_id, alias, enabled, display_name, keywords, user_id) -> WatchlistItem
    def remove_item(item_id, user_id) -> bool
```

所有操作通过 `WatchlistRepo` 执行，支持用户隔离（user_id 过滤）。

### 数据模型

```python
class WatchlistItem(BaseModel):
    id: int
    symbol: str
    market: str
    alias: Optional[str]
    display_name: Optional[str]
    keywords: List[str]            # 从 keywords_json 解析
    enabled: bool
    created_at: str
    updated_at: str
```

`keywords_json` 在数据库中存储为 JSON 字符串，在 schema 层序列化/反序列化为 `List[str]`。

## 仪表盘模块（dashboard/）

### DashboardService

```python
class DashboardService:
    async def get_snapshot(config) -> DashboardSnapshot
    async def get_indices(config) -> List[IndexQuote]
    async def get_watchlist_quotes(config, watchlist_items) -> List[WatchlistQuote]
```

- `get_indices()`：获取配置中定义的指数行情（如上证指数、恒生指数、S&P 500）
- `get_watchlist_quotes()`：批量获取自选股报价
- `get_snapshot()`：组合 indices + watchlist 数据

### 配置示例

```yaml
dashboard:
  indices:
    cn: [{name: "上证指数", symbol: "000001", market: "CN"}, ...]
    hk: [{name: "恒生指数", symbol: "HSI", market: "HK"}, ...]
    us: [{name: "S&P 500", symbol: "SPX", market: "US"}, ...]
```

所有模块数据获取使用 `MarketDataService`，行情失败时有缓存降级。
