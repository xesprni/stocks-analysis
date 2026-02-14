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

## 3. 检索策略

- 首选 `provider_id`（请求或配置指定）。
- provider 失败时回退 `composite`。
- `composite` 聚合多源，按 score 排序。
- `(symbol, market)` 维度去重，保留最高分。

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
