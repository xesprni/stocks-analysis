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

## 8. 配置示例

### 8.1 完整配置（`config/settings.yaml`）

```yaml
modules:
  fund_flow:
    providers:
      - id: eastmoney
        enabled: true
      - id: fred
        enabled: true

# FRED 序列配置（可选）
default_fred_series:
  - id: "SP500"
    name: "S&P 500 Index"
  - id: "VIXCLS"
    name: "CBOE Volatility Index (VIX)"
```

### 8.2 Provider 配置说明

| Provider | 说明 | 数据类型 | 更新频率 |
|----------|------|----------|----------|
| `eastmoney` | 东方财富资金流 | A股北向/港股南向 | 每日 |
| `fred` | 美联储经济数据 | 宏观指标/ETF资金流 | 每日/每周 |

## 9. 数据源详细说明

### 9.1 EastMoney 数据源

#### 数据接口

```python
EASTMONEY_FLOW_URL = "https://push2.eastmoney.com/api/qt/stock/fflow/kline/get"
```

#### 支持的序列

| 序列 ID | 说明 | 单位 |
|---------|------|------|
| `north_net_inflow` | 北向资金净流入 | 亿元 |
| `south_net_inflow` | 南向资金净流入 | 亿元 |
| `north_accumulated` | 北向资金累计净流入 | 亿元 |
| `south_accumulated` | 南向资金累计净流入 | 亿元 |

#### 数据格式

```json
{
  "date": "2024-01-15",
  "north_net_inflow": 52.3,
  "south_net_inflow": -15.6,
  "source": "eastmoney"
}
```

### 9.2 FRED 数据源

#### 数据接口

```python
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
```

#### 常用序列

| 序列 ID | 说明 | 频率 |
|---------|------|------|
| `SP500` | 标普500指数 | 日度 |
| `VIXCLS` | VIX波动率指数 | 日度 |
| `DFF` | 联邦基金利率 | 日度 |
| `T10Y2Y` | 10年-2年期国债利差 | 日度 |
| `WILL5000INDFC` | 威尔希尔5000指数 | 日度 |

#### 数据格式

```json
{
  "date": "2024-01-15",
  "value": 4783.35,
  "series_id": "SP500",
  "source": "fred"
}
```

## 10. 输出格式说明

### 10.1 FlowPoint 数据结构

```python
@dataclass
class FlowPoint:
    date: str          # 日期 "YYYY-MM-DD"
    value: float       # 数值
    series_id: str     # 序列标识
    series_name: str   # 序列名称
    source: str        # 数据来源
```

### 10.2 collect() 输出示例

```python
{
  "north_net_inflow": [
    FlowPoint(date="2024-01-15", value=52.3, series_id="north_net_inflow", ...),
    FlowPoint(date="2024-01-14", value=38.7, series_id="north_net_inflow", ...),
  ],
  "south_net_inflow": [
    FlowPoint(date="2024-01-15", value=-15.6, series_id="south_net_inflow", ...),
    FlowPoint(date="2024-01-14", value=22.1, series_id="south_net_inflow", ...),
  ],
  "SP500": [
    FlowPoint(date="2024-01-15", value=4783.35, series_id="SP500", ...),
    FlowPoint(date="2024-01-14", value=4776.12, series_id="SP500", ...),
  ]
}
```

## 11. API 使用示例

### 11.1 在分析中使用

```python
from market_reporter.modules.fund_flow.service import FundFlowService

# 创建服务
service = FundFlowService(config)

# 获取最近30天的资金流数据
flows, warnings = service.collect(periods=30)

# 访问特定序列
north_flow = flows.get("north_net_inflow", [])
sp500_data = flows.get("SP500", [])
```

### 11.2 在 Agent 工具中使用

```python
# market_reporter/modules/analysis/agent/tools/macro_tools.py

async def get_macro_data() -> dict:
    """获取宏观资金流数据"""
    flows, warnings = fund_flow_service.collect(periods=30)
    
    return {
        "north_flow_summary": summarize_flow(flows.get("north_net_inflow", [])),
        "south_flow_summary": summarize_flow(flows.get("south_net_inflow", [])),
        "warnings": warnings
    }
```

## 12. 错误处理与降级

### 12.1 Provider 失败处理

```python
def collect(self, periods: int) -> Tuple[Dict[str, List[FlowPoint]], List[str]]:
    results = {}
    warnings = []
    
    for provider_config in self.providers:
        try:
            provider = self._get_provider(provider_config.id)
            data = provider.collect(periods)
            results.update(data)
        except Exception as e:
            warnings.append(f"Provider {provider_config.id} failed: {str(e)}")
            continue  # 继续处理其他 provider
    
    return results, warnings
```

### 12.2 降级策略

| 场景 | 处理方式 |
|------|----------|
| 单个 provider 失败 | 记录 warning，返回其他 provider 数据 |
| 所有 provider 失败 | 返回空字典 + warning 列表 |
| 网络超时 | 重试 2 次，失败后降级 |
| 数据格式错误 | 跳过错误数据点，记录 warning |

## 13. 与其他模块的交互

### 13.1 与 analysis 模块

- analysis 模块在个股分析时获取资金流数据作为上下文
- 用于判断市场整体资金面情况

### 13.2 与 agent 模块

- agent 模块的 `get_macro_data` 工具调用 fund_flow 服务
- 将资金流数据纳入分析报告的宏观面部分

### 13.3 与 reports 模块

- reports 模块在生成市场报告时包含资金流数据
- 用于市场总览报告的资金面分析
