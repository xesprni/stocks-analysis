# symbol_search 模块

## 1. 模块职责

根据 query + 市场范围检索标的列表，融合多 provider 结果并做评分去重。

## 2. 核心文件

- `market_reporter/modules/symbol_search/service.py`
- `market_reporter/modules/symbol_search/schemas.py`
- providers:
  - `finnhub_search_provider.py`
  - `yfinance_search_provider.py`
  - `akshare_search_provider.py`
  - `longbridge_search_provider.py`

## 3. 检索策略

- 首选 `provider_id`（请求或配置指定）。
- provider 失败时回退 `composite`。
- `composite` 聚合多源，按 score 排序。
- `(symbol, market)` 维度去重，保留最高分。
- `longbridge` 走 SDK，优先处理 ticker/code 形态查询（名称查询自动回退其他 provider）。

## 4. 启发式回退

当所有 provider 返回空时，生成手工候选：

- US ticker 规则
- HK 数字代码规则
- CN 6 位代码规则

确保搜索接口尽量不返回空。

## 5. 评分规则（典型）

- 完全命中 symbol 最高分
- 前缀命中次之
- 子串命中/名称命中逐级下降

## 6. 模块输出

`StockSearchResult`：

- `symbol`
- `market`
- `name`
- `exchange`
- `source`
- `score`

## 7. API 对应

`GET /api/stocks/search`

## 8. 配置示例

### 8.1 完整配置（`config/settings.yaml`）

```yaml
modules:
  symbol_search:
    default_provider: composite
    providers:
      - id: yfinance
        enabled: true
      - id: akshare
        enabled: true
      - id: finnhub
        enabled: false
      - id: longbridge
        enabled: false
```

### 8.2 Provider 配置说明

| Provider | 说明 | 适用市场 | 备注 |
|----------|------|----------|------|
| `yfinance` | Yahoo Finance 搜索 | US, HK, CN | 免费，数据全面 |
| `akshare` | AkShare 搜索 | CN, HK | 中国A股数据准确 |
| `finnhub` | Finnhub API | US | 需要 API Key |
| `longbridge` | Longbridge SDK | CN, HK, US | 需要 SDK 配置 |

### 8.3 API 使用示例

#### 基本搜索

```bash
curl -X GET "http://localhost:8000/api/stocks/search?query=AAPL"
```

#### 指定市场搜索

```bash
curl -X GET "http://localhost:8000/api/stocks/search?query=苹果&market=CN"
```

#### 指定 provider 搜索

```bash
curl -X GET "http://localhost:8000/api/stocks/search?query=Apple&provider_id=yfinance"
```

#### 限制结果数量

```bash
curl -X GET "http://localhost:8000/api/stocks/search?query=腾讯&limit=5"
```

## 9. 搜索匹配算法说明

### 9.1 评分算法

```python
def calculate_score(query: str, result: StockSearchResult) -> float:
    """
    计算搜索结果的匹配得分
    
    Args:
        query: 搜索关键词
        result: 搜索结果
    
    Returns:
        匹配得分（0-100）
    """
    score = 0.0
    query_lower = query.lower()
    symbol_lower = result.symbol.lower()
    name_lower = result.name.lower() if result.name else ""
    
    # 完全匹配 symbol（最高分）
    if query_lower == symbol_lower:
        score = 100.0
    # symbol 前缀匹配
    elif symbol_lower.startswith(query_lower):
        score = 80.0 + (len(query_lower) / len(symbol_lower)) * 10
    # symbol 包含查询词
    elif query_lower in symbol_lower:
        score = 60.0 + (len(query_lower) / len(symbol_lower)) * 10
    # 名称完全匹配
    elif query_lower == name_lower:
        score = 70.0
    # 名称前缀匹配
    elif name_lower.startswith(query_lower):
        score = 50.0 + (len(query_lower) / len(name_lower)) * 10
    # 名称包含查询词
    elif query_lower in name_lower:
        score = 30.0 + (len(query_lower) / len(name_lower)) * 10
    
    return min(score, 100.0)
```

### 9.2 评分规则详解

| 匹配类型 | 得分范围 | 示例 |
|----------|----------|------|
| Symbol 完全匹配 | 100 | query="AAPL", symbol="AAPL" |
| Symbol 前缀匹配 | 80-90 | query="AAP", symbol="AAPL" |
| Symbol 包含匹配 | 60-70 | query="AP", symbol="AAPL" |
| 名称完全匹配 | 70 | query="苹果", name="苹果" |
| 名称前缀匹配 | 50-60 | query="苹", name="苹果" |
| 名称包含匹配 | 30-40 | query="果", name="苹果" |

### 9.3 去重策略

```python
def deduplicate_results(results: List[StockSearchResult]) -> List[StockSearchResult]:
    """
    按 (symbol, market) 去重，保留最高分
    
    Args:
        results: 原始搜索结果列表
    
    Returns:
        去重后的搜索结果列表
    """
    seen = {}
    for result in results:
        key = (result.symbol, result.market)
        if key not in seen or result.score > seen[key].score:
            seen[key] = result
    return sorted(seen.values(), key=lambda x: x.score, reverse=True)
```

## 10. 启发式回退详解

### 10.1 US 市场

```python
# US ticker 规则：纯字母，长度 1-5
if market == "US" and query.isalpha() and 1 <= len(query) <= 5:
    return [
        StockSearchResult(
            symbol=query.upper(),
            market="US",
            name=f"{query.upper()} (Generated)",
            source="heuristic",
            score=50.0
        )
    ]
```

### 10.2 HK 市场

```python
# HK 数字代码规则：纯数字，长度 1-5
if market == "HK" and query.isdigit() and 1 <= len(query) <= 5:
    return [
        StockSearchResult(
            symbol=query.zfill(5),  # 补零到 5 位
            market="HK",
            name=f"港股 {query.zfill(5)} (Generated)",
            source="heuristic",
            score=50.0
        )
    ]
```

### 10.3 CN 市场

```python
# CN 6位代码规则：纯数字，长度 6
if market == "CN" and query.isdigit() and len(query) == 6:
    return [
        StockSearchResult(
            symbol=query,
            market="CN",
            name=f"A股 {query} (Generated)",
            source="heuristic",
            score=50.0
        )
    ]
```

## 11. 输出格式示例

### 11.1 单个搜索结果

```json
{
  "symbol": "AAPL",
  "market": "US",
  "name": "Apple Inc.",
  "exchange": "NASDAQ",
  "source": "yfinance",
  "score": 100.0
}
```

### 11.2 搜索结果列表

```json
[
  {
    "symbol": "AAPL",
    "market": "US",
    "name": "Apple Inc.",
    "exchange": "NASDAQ",
    "source": "yfinance",
    "score": 100.0
  },
  {
    "symbol": "AAPL.BA",
    "market": "AR",
    "name": "Apple Inc.",
    "exchange": "Buenos Aires",
    "source": "yfinance",
    "score": 85.0
  }
]
```

## 12. 与其他模块的交互

### 12.1 与 watchlist 模块

- 用户在添加 watchlist 时通过搜索找到正确的 symbol
- 搜索结果直接用于创建 watchlist 项目

### 12.2 与 market_data 模块

- 搜索结果的 symbol 格式与 market_data 模块一致
- 用户选择搜索结果后可直接获取行情数据

### 12.3 与 analysis 模块

- analysis 模块在个股分析时使用搜索功能定位标的
- 搜索结果用于填充分析请求的 symbol 和 market 字段
