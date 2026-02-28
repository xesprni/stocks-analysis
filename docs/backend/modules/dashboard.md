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

## 7. 配置示例

### 7.1 完整配置（`config/settings.yaml`）

```yaml
dashboard:
  auto_refresh_enabled: true
  auto_refresh_seconds: 60
  indices:
    # A股指数
    - symbol: "000001"
      market: CN
      display_name: "上证指数"
    - symbol: "399001"
      market: CN
      display_name: "深证成指"
    - symbol: "399006"
      market: CN
      display_name: "创业板指"
    # 港股指数
    - symbol: "HSI"
      market: HK
      display_name: "恒生指数"
    - symbol: "HSCEI"
      market: HK
      display_name: "国企指数"
    # 美股指数
    - symbol: "^DJI"
      market: US
      display_name: "道琼斯"
    - symbol: "^GSPC"
      market: US
      display_name: "标普500"
    - symbol: "^IXIC"
      market: US
      display_name: "纳斯达克"
```

### 7.2 配置项说明

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `auto_refresh_enabled` | `true` | 是否启用自动刷新 |
| `auto_refresh_seconds` | `60` | 自动刷新间隔（秒） |
| `indices` | `[]` | 指数列表配置 |

### 7.3 指数配置字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `symbol` | string | 指数代码 |
| `market` | string | 市场标识（CN/HK/US） |
| `display_name` | string | 显示名称 |

## 8. API 使用示例

### 8.1 获取完整快照

```bash
curl -X GET "http://localhost:8000/api/dashboard/snapshot"

# 响应
{
  "indices": [
    {
      "symbol": "000001",
      "market": "CN",
      "display_name": "上证指数",
      "quote": {
        "price": 3050.12,
        "change": 36.25,
        "change_percent": 1.20,
        "source": "akshare"
      }
    }
  ],
  "watchlist": {
    "items": [...],
    "total": 50,
    "page": 1,
    "page_size": 20
  },
  "updated_at": "2024-01-15T10:30:00Z"
}
```

### 8.2 获取指数快照

```bash
curl -X GET "http://localhost:8000/api/dashboard/indices"

# 响应
[
  {
    "symbol": "000001",
    "market": "CN",
    "display_name": "上证指数",
    "quote": {
      "price": 3050.12,
      "change": 36.25,
      "change_percent": 1.20,
      "volume": 125000000,
      "source": "akshare",
      "timestamp": "2024-01-15T15:00:00Z"
    }
  },
  {
    "symbol": "^DJI",
    "market": "US",
    "display_name": "道琼斯",
    "quote": {
      "price": 37850.25,
      "change": 125.50,
      "change_percent": 0.33,
      "volume": 0,
      "source": "yfinance",
      "timestamp": "2024-01-15T21:00:00Z"
    }
  }
]
```

### 8.3 获取 Watchlist 快照（分页）

```bash
curl -X GET "http://localhost:8000/api/dashboard/watchlist?page=1&page_size=10"

# 响应
{
  "items": [
    {
      "id": 1,
      "symbol": "AAPL",
      "market": "US",
      "display_name": "Apple Inc.",
      "enabled": true,
      "quote": {
        "price": 178.52,
        "change": 2.35,
        "change_percent": 1.33,
        "source": "yfinance"
      }
    }
  ],
  "total": 50,
  "page": 1,
  "page_size": 10
}
```

### 8.4 更新自动刷新配置

```bash
curl -X PUT http://localhost:8000/api/dashboard/auto-refresh \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "interval_seconds": 30
  }'

# 响应
{
  "auto_refresh_enabled": true,
  "auto_refresh_seconds": 30
}
```

## 9. 分页参数说明

### 9.1 分页参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `page` | int | 1 | 页码（从1开始） |
| `page_size` | int | 20 | 每页数量 |
| `enabled_only` | bool | false | 仅返回启用的项目 |

### 9.2 分页响应结构

```json
{
  "items": [...],      // 当前页数据
  "total": 100,        // 总数量
  "page": 1,           // 当前页码
  "page_size": 20      // 每页数量
}
```

### 9.3 分页计算示例

```python
def get_watchlist_snapshot(
    page: int = 1,
    page_size: int = 20,
    enabled_only: bool = False
) -> PaginatedWatchlistSnapshot:
    """
    获取 watchlist 分页快照
    
    Args:
        page: 页码（从1开始）
        page_size: 每页数量
        enabled_only: 仅返回启用的项目
    
    Returns:
        分页快照数据
    """
    # 获取所有 watchlist 项目
    all_items = watchlist_service.list_items(enabled_only=enabled_only)
    
    # 计算分页
    total = len(all_items)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = all_items[start:end]
    
    # 并发获取报价
    quotes = await asyncio.gather(*[
        market_data_service.get_quote(item.symbol, item.market)
        for item in page_items
    ])
    
    # 组装结果
    return PaginatedWatchlistSnapshot(
        items=[...],
        total=total,
        page=page,
        page_size=page_size
    )
```

## 10. 快照数据结构

### 10.1 DashboardSnapshot

```python
@dataclass
class DashboardSnapshot:
    indices: List[IndexSnapshot]           # 指数快照列表
    watchlist: PaginatedWatchlistSnapshot  # watchlist 分页快照
    updated_at: str                        # 更新时间
```

### 10.2 IndexSnapshot

```python
@dataclass
class IndexSnapshot:
    symbol: str           # 指数代码
    market: str           # 市场
    display_name: str     # 显示名称
    quote: Quote          # 报价数据
```

### 10.3 WatchlistItemSnapshot

```python
@dataclass
class WatchlistItemSnapshot:
    id: int               # watchlist ID
    symbol: str           # 股票代码
    market: str           # 市场
    display_name: str     # 显示名称
    enabled: bool         # 是否启用
    quote: Quote          # 报价数据
```

### 10.4 Quote

```python
@dataclass
class Quote:
    price: float              # 当前价格
    change: float             # 涨跌额
    change_percent: float     # 涨跌幅
    volume: float             # 成交量
    source: str               # 数据来源
    timestamp: str            # 时间戳
```

## 11. 并发获取优化

### 11.1 并发获取实现

```python
async def get_snapshot(
    page: int = 1,
    page_size: int = 20,
    enabled_only: bool = False
) -> DashboardSnapshot:
    """
    并发获取完整快照
    """
    # 并发获取指数和 watchlist
    indices_task = get_index_snapshot(enabled_only)
    watchlist_task = get_watchlist_snapshot(page, page_size, enabled_only)
    
    indices, watchlist = await asyncio.gather(indices_task, watchlist_task)
    
    return DashboardSnapshot(
        indices=indices,
        watchlist=watchlist,
        updated_at=datetime.now().isoformat()
    )
```

### 11.2 性能优化策略

| 策略 | 说明 |
|------|------|
| 并发请求 | 使用 `asyncio.gather` 并发获取多个报价 |
| 批量请求 | 对 watchlist 批量获取报价 |
| 缓存复用 | 复用 market_data 模块的缓存 |
| 降级处理 | 单个报价失败不影响整体快照 |

## 12. 自动刷新机制

### 12.1 前端自动刷新

前端通过轮询 `/api/dashboard/snapshot` 实现自动刷新：

```javascript
// 前端轮询示例
let refreshInterval;

function startAutoRefresh(intervalSeconds) {
  refreshInterval = setInterval(async () => {
    const snapshot = await fetch('/api/dashboard/snapshot');
    updateDashboard(snapshot);
  }, intervalSeconds * 1000);
}

function stopAutoRefresh() {
  clearInterval(refreshInterval);
}
```

### 12.2 刷新间隔建议

| 场景 | 建议间隔 |
|------|----------|
| 交易时段 | 30-60秒 |
| 非交易时段 | 300秒或关闭 |
| 移动网络 | 60-120秒 |

## 13. 与其他模块的交互

### 13.1 与 watchlist 模块

- dashboard 模块调用 `WatchlistService.list_items()` 获取 watchlist 列表
- 支持分页和过滤

### 13.2 与 market_data 模块

- dashboard 模块调用 `MarketDataService.get_quote()` 获取实时报价
- 复用 market_data 模块的缓存和降级策略

### 13.3 与 config 模块

- dashboard 模块从 `ConfigStore` 读取指数配置
- 支持运行时更新自动刷新配置
