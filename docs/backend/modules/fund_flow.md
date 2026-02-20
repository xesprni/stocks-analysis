# fund_flow 模块

## 1. 模块职责

聚合不同来源的资金流/宏观序列数据，输出标准化 `FlowPoint` 序列。

## 2. 核心文件

- `market_reporter/modules/fund_flow/service.py`
- providers:
  - `eastmoney_provider.py`
  - `fred_provider.py`

## 3. Provider 组织

- 模块名：`fund_flow`
- 实际执行顺序由 `config.modules.fund_flow.providers` 定义
- 每个 provider 独立容错：单个失败仅记 warning

## 4. EastMoney provider

- 接口：`EASTMONEY_FLOW_URL`
- 输出主序列：
  - A 股北向净流入
  - 港股南向净流入
- 支持 `s2n/n2s` 与兼容字段 `hk2sh/hk2sz` 合并逻辑

## 5. FRED provider

- 接口：`FRED_CSV_URL`
- 读取 `FRED_SERIES` 配置，按序列逐个拉取 CSV
- 输出美国基金/ETF 相关序列

## 6. 模块输出

`collect(periods)` -> `(Dict[str, List[FlowPoint]], warnings)`。

每个 key 对应一个 series，取最新 `periods` 条。

## 7. 使用方

- `analysis`（个股分析与监听告警上下文）
- `analysis/agent/macro_tools`（市场模式工具链）
