# market_data 模块

## 1. 模块职责

提供行情能力：报价、K 线、分时曲线，并内置 provider 失败回退与本地缓存。

## 2. 核心文件

- `market_reporter/modules/market_data/service.py`
- `market_reporter/modules/market_data/symbol_mapper.py`
- providers:
  - `yfinance_provider.py`
  - `akshare_provider.py`
  - `composite_provider.py`

## 3. Provider 注册与路由

- 注册 provider：`yfinance`、`akshare`、`composite`
- 默认 provider 由 `config.modules.market_data.default_provider` 控制
- `composite` 按市场优先级自动选择：
  - CN/HK：`akshare -> yfinance`
  - US：`yfinance -> akshare`

## 4. Symbol 标准化

`symbol_mapper` 负责不同市场代码统一：

- CN：补 `.SH/.SZ/.BJ`
- HK：补 `.HK` + 4 位补零
- yfinance 适配：`.SH` 映射为 `.SS`

## 5. 缓存策略

- 获取 K 线成功后 `upsert_kline` 写库。
- 获取曲线成功后 `save_curve_points` 写库并做点数裁剪。
- provider 失败时优先读缓存：
  - quote 从曲线或 K 线推导
  - kline/curve 直接返回缓存

## 6. 对外输出与降级

- quote 失败且无缓存时返回 `price=0.0, source=unavailable`。
- 始终返回结构化 `Quote/KLineBar/CurvePoint`，保持 API 合约稳定。

## 7. 上游依赖

- 行情 provider：`yfinance`、`akshare`
- 持久化：`MarketDataRepo`
- 使用方：`stocks API`、`dashboard`、`analysis`、`news_listener`

## 8. 配置示例

### 8.1 完整配置（`config/settings.yaml`）

```yaml
modules:
  market_data:
    default_provider: composite
    providers:
      - id: yfinance
        enabled: true
      - id: akshare
        enabled: true
      - id: composite
        enabled: true
```

### 8.2 Provider 配置说明

| Provider | 说明 | 适用市场 | 备注 |
|----------|------|----------|------|
| `yfinance` | Yahoo Finance API | US, HK, CN | 免费，数据质量高 |
| `akshare` | AkShare API | CN, HK | 中国A股数据全面 |
| `composite` | 组合provider | 所有市场 | 自动选择最佳provider |

### 8.3 API 使用示例

#### 获取单股报价

```bash
curl -X GET "http://localhost:8000/api/stocks/AAPL/quote"
```

#### 获取批量报价

```bash
curl -X POST http://localhost:8000/api/stocks/quotes \
  -H "Content-Type: application/json" \
  -d '[
    {"symbol": "AAPL", "market": "US"},
    {"symbol": "0700", "market": "HK"},
    {"symbol": "600519", "market": "CN"}
  ]'
```

#### 获取K线数据

```bash
curl -X GET "http://localhost:8000/api/stocks/AAPL/kline?interval=1d&limit=30"
```

#### 获取分时曲线

```bash
curl -X GET "http://localhost:8000/api/stocks/AAPL/curve?interval=5m&limit=100"
```

## 9. 缓存策略详细说明

### 9.1 缓存数据结构

```python
# K线缓存表结构
stock_kline_bars (
    symbol VARCHAR(20),
    market VARCHAR(10),
    interval VARCHAR(10),  # 1d, 1h, 5m, 1m
    time DATETIME,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    source VARCHAR(50)
)

# 分时曲线缓存表结构
stock_curve_points (
    symbol VARCHAR(20),
    market VARCHAR(10),
    time DATETIME,
    price REAL,
    volume REAL,
    source VARCHAR(50)
)
```

### 9.2 缓存更新策略

| 操作 | 缓存行为 |
|------|----------|
| 成功获取数据 | 更新或插入缓存 |
| 缓存存在但过期 | 优先使用缓存，后台异步更新 |
| provider失败 | 使用缓存数据，标记为降级 |
| 缓存为空 | 返回 `source=unavailable` |

### 9.3 缓存有效期

| 数据类型 | 有效期 | 更新频率 |
|----------|--------|----------|
| 1m K线 | 1小时 | 每分钟更新 |
| 5m K线 | 24小时 | 每5分钟更新 |
| 1h K线 | 7天 | 每小时更新 |
| 1d K线 | 30天 | 每日收盘后更新 |
| 分时曲线 | 24小时 | 每5分钟更新 |

## 10. 降级策略

### 10.1 降级流程

```text
1. 尝试首选 provider
2. 如果失败，尝试次选 provider
3. 如果所有 provider 都失败，检查缓存
4. 如果缓存存在，返回缓存数据（source=cache）
5. 如果缓存不存在，返回 source=unavailable
```

### 10.2 降级响应示例

```json
{
  "symbol": "AAPL",
  "market": "US",
  "price": 0.0,
  "change": 0.0,
  "change_percent": 0.0,
  "volume": 0,
  "source": "unavailable",
  "timestamp": "2024-01-15T21:00:00Z"
}
```

### 10.3 缓存降级响应示例

```json
{
  "symbol": "AAPL",
  "market": "US",
  "price": 178.52,
  "change": 2.35,
  "change_percent": 1.33,
  "volume": 52340000,
  "source": "cache",
  "timestamp": "2024-01-15T21:00:00Z"
}
```

## 11. 与其他模块的交互

### 11.1 与 dashboard 模块

- dashboard 模块通过 `MarketDataService.get_quote()` 获取 watchlist 和指数的实时行情
- 通过 `get_kline()` 获取指数历史K线

### 11.2 与 news_listener 模块

- news_listener 模块通过 `get_curve()` 和 `get_quote()` 计算新闻事件发生时的价格异动
- 使用 `get_curve()` 获取事件前后60分钟的价格走势

### 11.3 与 analysis 模块

- analysis 模块通过 `get_kline()` 获取股票历史价格数据用于技术分析
- 通过 `get_quote()` 获取实时价格用于分析上下文

### 11.4 与 symbol_search 模块

- symbol_search 模块使用 `MarketDataService` 的 symbol 规范化逻辑
- 保证搜索结果的 symbol 格式与行情数据一致
