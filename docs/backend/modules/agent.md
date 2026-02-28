# agent 子包（analysis/agent）

## 1. 模块职责

`analysis` 模块的子包，将"多工具数据采集 + LLM 结构化推理 + 规则护栏校验 + 报告格式化"串成统一执行链。

## 2. 核心文件

- 编排：`market_reporter/modules/analysis/agent/orchestrator.py`
- 门面：`market_reporter/modules/analysis/agent/service.py`
- 运行时：
  - `runtime/openai_tool_runtime.py`
  - `runtime/action_json_runtime.py`
  - `runtime/factory.py`
- 护栏：`guardrails.py`
- 报告输出：`report_formatter.py`
- 工具集合：`tools/*.py`

## 3. 工具清单

- `get_price_history`（行情历史）
- `get_fundamentals_info`（基本面，基于 Longbridge SDK）
- `get_financial_reports`（财报信息）
- `search_news`（新闻检索，支持 ticker/别名匹配）
- `search_web`（联网检索）
- `compute_indicators`（技术指标/策略打分/信号时间线）
- `peer_compare`（同行对比）
- `get_macro_data`（宏观资金流）

## 4. 执行流程（stock 模式）

1. 解析问题与时间范围（news/filing/price）。
2. 采集多周期行情（1d/5m/1m 可配置）。
3. 采集基本面、财报、新闻、联网检索、可选 peer compare。
4. `compute_indicators` 生成趋势/动量/量价/形态/支撑阻力/策略评分。
5. 进入 runtime（OpenAI tools 或 Action-JSON）生成草稿。
6. 护栏校验证据完整性与关键一致性（如 PE 一致性）。
7. 报告格式化输出 `AgentFinalReport`。

market 模式仅保留新闻 + 宏观数据工具。

## 5. Runtime 策略

- `OpenAIToolRuntime`：使用 tools API 循环调用。
- `ActionJSONRuntime`：要求模型输出 `action_json_v1` 协议（call_tool/final）。
- 失败时生成 fallback `RuntimeDraft`，保证输出可用。

## 5.1 Skills（能力抽象）

- Agent 运行入口已改为 skill 驱动，`AgentOrchestrator` 通过 `AgentSkillRegistry` 选择能力。
- 内置 skill：
  - `stock_analysis`（别名 `stock`）
  - `market_overview`（别名 `market`）
- `AgentRunRequest` 新增 `skill_id`（可选），用于在兼容 `mode` 的同时显式指定 skill。

## 6. 指标计算后端回退

`compute_tools.ComputeTools`：

- 优先 `ta-lib`
- 回退 `pandas-ta`
- 最终回退 builtin 算法

输出统一包含：

- `trend/momentum/volume_price/patterns/support_resistance`
- `strategy`（score/stance/仓位/止损止盈）
- `signal_timeline`

## 7. 护栏与置信度

`AgentGuardrails`：

- 检查 tool 输出元数据（`as_of/source`）
- 检查结论是否有证据标记 `[E*]`
- 可选 PE 一致性校验
- 根据问题严重度施加置信度惩罚

## 8. 对外产物

- `AgentRunResult`（analysis_input/runtime_draft/final_report/tool_calls/evidence）
- 最终由 `AnalysisService` 转换为 `AnalysisOutput`

## 9. 配置示例

### 9.1 完整配置（`config/settings.yaml`）

```yaml
agent:
  default_skill: stock_analysis
  runtime: openai_tools
  max_tool_iterations: 10
  guardrails:
    pe_consistency_check: true
    evidence_required: true
  tools:
    price_history:
      enabled: true
      periods:
        - interval: 1d
          lookback: 365
        - interval: 1h
          lookback: 30
    fundamentals:
      enabled: true
    financial_reports:
      enabled: true
    news:
      enabled: true
      max_items: 20
    web_search:
      enabled: true
      max_results: 5
    indicators:
      enabled: true
      backend: auto  # auto, ta-lib, pandas-ta, builtin
    peer_compare:
      enabled: false
    macro_data:
      enabled: true
```

### 9.2 Skill 配置说明

| Skill ID | 别名 | 说明 | 可用工具 |
|----------|------|------|----------|
| `stock_analysis` | `stock` | 个股深度分析 | 全部工具 |
| `market_overview` | `market` | 市场总览 | news, macro_data |

### 9.3 Runtime 配置说明

| Runtime | 说明 | 适用模型 |
|---------|------|----------|
| `openai_tools` | OpenAI Tools API 循环调用 | GPT-4, GPT-3.5-turbo |
| `action_json` | Action-JSON 协议 | 支持结构化输出的模型 |

## 10. 工具调用规范

### 10.1 工具定义格式

```python
@dataclass
class ToolDefinition:
    name: str           # 工具名称
    description: str    # 工具描述
    parameters: dict    # JSON Schema 参数定义
    required: List[str] # 必需参数列表
```

### 10.2 工具调用示例

#### get_price_history

```python
# 工具定义
{
    "name": "get_price_history",
    "description": "获取股票历史价格数据",
    "parameters": {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "股票代码"},
            "market": {"type": "string", "enum": ["CN", "HK", "US"]},
            "interval": {"type": "string", "enum": ["1d", "1h", "5m", "1m"]},
            "lookback": {"type": "integer", "description": "回溯天数"}
        },
        "required": ["symbol", "market"]
    }
}

# 调用示例
{
    "name": "get_price_history",
    "arguments": {
        "symbol": "AAPL",
        "market": "US",
        "interval": "1d",
        "lookback": 365
    }
}

# 返回结果
{
    "bars": [
        {"time": "2024-01-15", "open": 176.17, "high": 179.23, "low": 175.82, "close": 178.52, "volume": 52340000}
    ],
    "source": "yfinance",
    "as_of": "2024-01-15T21:00:00Z"
}
```

#### compute_indicators

```python
# 调用示例
{
    "name": "compute_indicators",
    "arguments": {
        "symbol": "AAPL",
        "market": "US",
        "bars": [...]  # K线数据
    }
}

# 返回结果
{
    "trend": {
        "direction": "up",
        "strength": 0.75,
        "ma_alignment": "bullish"
    },
    "momentum": {
        "rsi": 65.2,
        "macd": {"value": 2.5, "signal": 1.8, "histogram": 0.7},
        "stochastic": {"k": 72.5, "d": 68.3}
    },
    "volume_price": {
        "obv_trend": "up",
        "volume_sma_ratio": 1.2
    },
    "patterns": ["cup_and_handle", "breakout"],
    "support_resistance": {
        "support": [175.0, 170.0],
        "resistance": [180.0, 185.0]
    },
    "strategy": {
        "score": 75,
        "stance": "bullish",
        "position_suggestion": "0.6",
        "stop_loss": 172.0,
        "take_profit": 190.0
    },
    "signal_timeline": [
        {"date": "2024-01-10", "signal": "buy", "confidence": 0.8},
        {"date": "2024-01-15", "signal": "hold", "confidence": 0.7}
    ]
}
```

#### search_news

```python
# 调用示例
{
    "name": "search_news",
    "arguments": {
        "symbol": "AAPL",
        "market": "US",
        "keywords": ["苹果", "iPhone", "Apple"],
        "max_items": 20
    }
}

# 返回结果
{
    "news": [
        {
            "title": "Apple announces new iPhone",
            "link": "https://...",
            "published": "2024-01-15T10:30:00Z",
            "summary": "Apple Inc. announced...",
            "relevance_score": 0.95
        }
    ],
    "source": "rss",
    "as_of": "2024-01-15T21:00:00Z"
}
```

### 10.3 工具调用流程

```text
1. Agent 接收用户问题
2. 根据 skill 确定可用工具集
3. Runtime 循环调用工具：
   a. 构造工具调用请求
   b. 执行工具获取结果
   c. 将结果反馈给 LLM
   d. LLM 决定继续调用工具或输出最终答案
4. 达到 max_tool_iterations 或 LLM 输出最终答案时停止
5. 护栏校验结果
6. 格式化输出报告
```

## 11. 护栏校验规范

### 11.1 证据标记规范

```markdown
[E1] 价格数据：AAPL 当前价格 $178.52
[E2] 新闻数据：苹果发布新款 iPhone
[E3] 指标数据：RSI 65.2，MACD 金叉
```

### 11.2 校验规则

| 校验项 | 规则 | 失败处理 |
|--------|------|----------|
| 证据完整性 | 结论必须有至少一个 `[E*]` 标记 | 置信度 -20% |
| PE 一致性 | 基本面 PE 与计算 PE 误差 < 10% | 置信度 -10% |
| 数据时效性 | 数据 as_of 时间在 24 小时内 | 置信度 -5% |
| 来源多样性 | 至少使用 2 个不同数据源 | 置信度 -5% |

### 11.3 置信度计算

```python
def calculate_confidence(draft: RuntimeDraft, evidence: List[Evidence]) -> float:
    """
    计算分析结果置信度
    
    Args:
        draft: LLM 生成的草稿
        evidence: 证据列表
    
    Returns:
        置信度（0-100）
    """
    confidence = 100.0
    
    # 证据完整性检查
    if not has_evidence_markers(draft.content):
        confidence -= 20
    
    # PE 一致性检查
    if not check_pe_consistency(evidence):
        confidence -= 10
    
    # 数据时效性检查
    if not check_data_freshness(evidence, hours=24):
        confidence -= 5
    
    # 来源多样性检查
    if not check_source_diversity(evidence, min_sources=2):
        confidence -= 5
    
    return max(confidence, 0)
```

## 12. 输出格式说明

### 12.1 AgentRunResult 结构

```python
@dataclass
class AgentRunResult:
    analysis_input: AnalysisInput      # 输入数据
    runtime_draft: RuntimeDraft        # LLM 草稿
    final_report: AgentFinalReport     # 最终报告
    tool_calls: List[ToolCall]         # 工具调用记录
    evidence: List[Evidence]           # 证据列表
    confidence: float                  # 置信度
    warnings: List[str]                # 警告列表
```

### 12.2 AgentFinalReport 结构

```python
@dataclass
class AgentFinalReport:
    markdown: str           # Markdown 格式报告
    summary: str            # 摘要
    key_points: List[str]   # 关键点
    recommendations: List[str]  # 建议
    risk_factors: List[str] # 风险因素
    data_sources: List[str] # 数据来源
    confidence: float       # 置信度
```

## 13. 与其他模块的交互

### 13.1 与 analysis 模块

- analysis 模块通过 `AgentService` 调用 agent 子包
- `resolve_credentials()` 为 agent 提供凭据

### 13.2 与 market_data 模块

- `get_price_history` 工具调用 `MarketDataService`
- 获取 K线、分时曲线数据

### 13.3 与 news 模块

- `search_news` 工具调用 `NewsService`
- 获取相关新闻数据

### 13.4 与 fund_flow 模块

- `get_macro_data` 工具调用 `FundFlowService`
- 获取资金流和宏观数据
