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
