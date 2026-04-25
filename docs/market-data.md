# Market Data — 行情模块

`market_reporter/modules/market_data/` 负责股票行情数据的获取、缓存和多 Provider 路由。

## 代码结构

```
market_data/
├── service.py                # MarketDataService（统一入口 + Provider 路由）
├── symbol_mapper.py          # 跨市场 symbol 规范化
├── yf_throttle.py            # Yahoo Finance 限频器
└── providers/
    ├── longbridge_provider.py   # Longbridge OpenAPI（主力）
    ├── yfinance_provider.py     # Yahoo Finance
    ├── akshare_provider.py      # AKShare（A股）
    └── composite_provider.py    # 多 Provider 回退
```

## MarketDataService（service.py）

统一行情入口，封装 Provider 路由、数据缓存和降级策略。

```python
class MarketDataService:
    MODULE_NAME = "market_data"

    def __init__(self, config: AppConfig, registry: ProviderRegistry)
    async def get_quote(symbol, market, provider_id) -> Quote
    async def get_quotes(items: List[tuple[str,str]], provider_id) -> List[Quote]
    async def get_kline(symbol, market, interval, limit, provider_id) -> List[KLineBar]
    async def get_curve(symbol, market, window, provider_id) -> List[CurvePoint]
```

### Provider 路由策略

```
请求 → 默认 provider (longbridge)
       ↓ 失败
       → composite (回退)
       ↓ 失败
       → SQLite 缓存 (kline/curve)
       ↓ 缓存也没有
       → placeholder Quote (price=0, source="unavailable")
```

- `get_quotes()` 先尝试批量接口 `provider.get_quotes()`，再逐个回退 `get_quote()`
- K 线和分时数据成功后自动写入 SQLite 缓存（write-through）
- 缓存回退时从 `MarketDataRepo.list_kline()` / `list_curve_points()` 读取

### Quote 缓存合成

当所有 Provider 都失败时，`_quote_from_cache()` 尝试从缓存合成 Quote：

1. 优先从 `stock_curve_points`（通常最新鲜）取最近 2 个点计算 change
2. 回退到 `stock_kline_bars`，按 interval `1m → 5m → 1d` 优先级查找

### 货币映射

```python
{"CN": "CNY", "HK": "HKD", "US": "USD"}
```

## Symbol 规范化（symbol_mapper.py）

跨市场 symbol 格式转换：

```python
normalize_symbol(symbol, market)     # "AAPL" + "US" → "AAPL.US"
strip_market_suffix(symbol)          # "AAPL.US" → "AAPL"
to_longbridge_symbol(symbol, market) # "AAPL" + "US" → "AAPL.US" (Longbridge 格式)
```

## Longbridge Provider（longbridge_provider.py）

主力行情 Provider，使用 `longbridge` Python SDK。

```python
class LongbridgeMarketDataProvider:
    async def get_quote(symbol, market) -> Quote
    async def get_kline(symbol, market, interval, limit) -> List[KLineBar]
    async def get_curve(symbol, market, window) -> List[CurvePoint]
```

- 使用 `QuoteContext` SDK 对象进行查询
- 内部通过 `asyncio.to_thread()` 包装同步 SDK 调用
- K 线支持 `history_candlesticks_by_date()` 按日期范围查询，失败回退到 `candlesticks()` 按 count 查询
- 分时数据使用 `ctx.intraday()` 获取当日分钟级数据

## 其他 Providers

| Provider | 覆盖市场 | 说明 |
|----------|----------|------|
| `yfinance_provider.py` | US/HK | Yahoo Finance，受 `yf_throttle.py` 限频 |
| `akshare_provider.py` | CN | AKShare，A股专用 |
| `composite_provider.py` | 全部 | 组合多个 Provider 的回退链 |

## Yahoo Finance 限频（yf_throttle.py）

防止 Yahoo Finance API 被限频的请求节流器。
