# dashboard 模块

## 1. 模块职责

构建 Dashboard 快照数据，聚合指数行情与 watchlist 行情，并支持分页与自动刷新配置。

## 2. 核心文件

- `market_reporter/modules/dashboard/service.py`
- `market_reporter/modules/dashboard/schemas.py`

## 3. 快照接口

- `get_snapshot(page, page_size, enabled_only)`
- `get_index_snapshot(enabled_only)`
- `get_watchlist_snapshot(page, page_size, enabled_only)`

`get_snapshot` 通过 `asyncio.gather` 并发拉取指数与 watchlist，降低接口耗时。

## 4. 数据来源

- 指数列表来自 `config.dashboard.indices`
- watchlist 来自 `WatchlistService`
- 实时报价来自 `MarketDataService.get_quote`

## 5. 错误处理

- 非法 symbol/market 或行情异常时返回 `source=unavailable` 占位 quote，避免整个快照失败。

## 6. 自动刷新配置

- `config.dashboard.auto_refresh_enabled`
- `config.dashboard.auto_refresh_seconds`

API 可独立更新开关，不影响其它 dashboard 配置项。
