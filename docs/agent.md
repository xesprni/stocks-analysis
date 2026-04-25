# Agent — AI 分析引擎

`market_reporter/modules/analysis/agent/` 是系统的核心分析引擎，通过 LLM function calling 循环自主调用工具、收集数据、生成研报。

## 代码结构

```
agent/
├── schemas.py              # 数据模型（请求/响应/追踪/证据）
├── core/
│   ├── tool_protocol.py    # ToolDefinition + ToolExecutor 类型
│   └── tool_registry.py    # ToolRegistry（注册 + 执行工具）
├── runtime/
│   ├── openai_tool_runtime.py   # LLM function calling 主循环
│   └── payload_normalizer.py   # LLM 输出 → RuntimeDraft 规范化
├── tools/
│   ├── builtin_metrics_tool.py  # get_metrics 工具（Longbridge 行情）
│   └── builtin_news_tool.py     # search_news 工具（RSS + Bing）
├── orchestrator.py         # AgentOrchestrator（编排器）
├── guardrails.py           # AgentGuardrails（校验 + 置信度惩罚）
├── report_formatter.py     # AgentReportFormatter（Markdown 报告生成）
├── skill_catalog.py        # SkillCatalog（SKILL.md 加载 + CRUD）
└── service.py              # AgentService（入口，组装 Registry + Orchestrator）
```

## 调用链路

```
AgentService.run()
  → AgentOrchestrator.run()
    → OpenAIToolRuntime.run()        # LLM 循环
      → LLM 返回 tool_calls
      → ToolRegistry.execute()       # 执行工具
      → 循环直到 LLM 返回最终文本
    → Guardrails.validate()          # 校验
    → ReportFormatter.format_report() # 生成 Markdown
  → AgentRunResult
```

## 核心数据模型（schemas.py）

### 请求与响应

```python
class AgentRunRequest(BaseModel):
    question: str = ""
    symbol: Optional[str] = None
    market: Optional[str] = None
    mode: Literal["stock", "market"] = "stock"
    skill_id: Optional[str] = None
    # ... 可选字段：peer_list, indicators, news_from/to, timeframes 等

class AgentRunResult(BaseModel):
    analysis_input: Dict[str, Any]       # 原始输入 + tool_results
    runtime_draft: RuntimeDraft           # LLM 产出草稿
    final_report: AgentFinalReport        # 最终报告
    tool_calls: List[ToolCallTrace]       # 工具调用追踪
    guardrail_issues: List[GuardrailIssue] # 校验问题
    evidence_map: List[AgentEvidence]     # 证据映射
```

### 中间数据

```python
class RuntimeDraft(BaseModel):
    summary, sentiment, key_levels, risks, action_items, confidence
    conclusions, scenario_assumptions, markdown, raw

class AgentFinalReport(BaseModel):
    question, conclusions, data_sources, guardrail_issues, confidence, markdown

class ToolCallTrace(BaseModel):
    tool, arguments, result_preview, started_at, finished_at, duration_ms, status

class AgentEvidence(BaseModel):
    evidence_id, statement, source, as_of, pointer

class GuardrailIssue(BaseModel):
    code, severity (LOW/MEDIUM/HIGH), message, details
```

## Tool 系统

### ToolDefinition（tool_protocol.py）

```python
ToolExecutor = Callable[..., Awaitable[Dict[str, Any]]]

class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: Dict[str, Any]         # JSON Schema
    source: Literal["builtin", "mcp", "skill"] = "builtin"

    def to_openai_spec(self) -> Dict[str, Any]  # 转为 OpenAI function calling 格式
```

### ToolRegistry（tool_registry.py）

```python
class ToolRegistry:
    def register(definition: ToolDefinition, executor: ToolExecutor) -> None
    def execute(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]
    def get_tool_specs(self) -> List[Dict[str, Any]]  # 所有工具的 OpenAI spec
```

内部存储 `Dict[str, (ToolDefinition, ToolExecutor)]`，按 `name.lower()` 索引。

### 内置工具

#### get_metrics（builtin_metrics_tool.py）

通过 Longbridge SDK 获取行情数据，支持 5 种 action：

| action | 说明 | 返回字段 |
|--------|------|----------|
| `candlesticks` | K 线历史 | bars[] (ts, OHLCV) |
| `quote` | 实时报价 | price, prev_close, change, volume |
| `static_info` | 公司信息 | name_cn/en/hk, listing_date, shares, eps, bps |
| `calc_indexes` | 计算指标 | trailing_pe, pb_ratio, market_cap, turnover_rate |
| `intraday` | 分时数据 | points[] (ts, price, volume) |

**核心语法**：`asyncio.to_thread()` 将 Longbridge SDK 的同步调用包装为异步；`Config(app_key, app_secret, access_token)` 初始化 SDK 上下文。

#### search_news（builtin_news_tool.py）

组合 RSS 新闻搜索 + Bing 网页搜索：

1. 通过 `NewsService.collect()` 获取 RSS 新闻
2. 按 symbol 构建 ticker_terms + name_terms 匹配（ticker 用 `\b` 单词边界，name 用大小写不敏感包含）
3. 无命中时 fallback 到最新头条 + `no_news_matched` 警告
4. 可选 Bing RSS 搜索补充 web_results
5. 通过 Longbridge `static_info` 获取公司别名（name_cn/en/hk）

## LLM 运行时（openai_tool_runtime.py）

```python
class OpenAIToolRuntime:
    async def run(
        self, model, question, mode, context, tool_specs, tool_executor,
        max_steps, max_tool_calls, skill_content
    ) -> Tuple[RuntimeDraft, List[ToolCallTrace]]
```

核心循环逻辑：

1. **初始化 LLM**：`ChatOpenAI(model, base_url, temperature=0.1)` + `bind_tools(tool_specs)`
2. **循环**（最多 `max_steps` 轮）：
   - 调用 LLM，检查返回的 `tool_calls`
   - 如有 tool_calls 且未超限：逐个执行，`ToolMessage` 追加到 messages
   - 同一 tool+arguments 最多重试 2 次（`MAX_RETRIES_PER_TOOL_SIGNATURE`）
   - 如无 tool_calls：提取 content_text，跳出循环
3. **解析 LLM 输出**：`parse_json(content_text)` → `payload_normalizer.runtime_draft_from_payload()`
4. **返回** `(RuntimeDraft, traces)`

**关键保护**：
- `max_tool_calls` 限制总工具调用次数，超出时返回 `tool_budget_exhausted` 草稿
- LLM 调用超时自动重试 2 次（`MAX_MODEL_CALL_RETRIES`）
- 非 JSON 输出 fallback 为 `unstructured_content_payload`

## Payload 规范化（payload_normalizer.py）

`runtime_draft_from_payload(payload)` 将 LLM 返回的任意 dict 转为 `RuntimeDraft`：

- `coerce_confidence()`: 支持百分比（>1 自动除以100）、嵌套字段提取（confidence/value/score）
- `_coerce_text_list()`: 兼容 list 和单 string 输入

## 护栏系统（guardrails.py）

```python
class AgentGuardrails:
    def validate(tool_results, conclusions, evidence_map, consistency_tolerance) -> List[GuardrailIssue]
    def apply_confidence_penalty(base_confidence, issues) -> float
```

三项校验：

1. **元数据完整性**：每个 tool result 必须有 `as_of` 和 `source`
2. **PE 一致性**：`market_cap / net_income ≈ trailing_pe`（在 tolerance 内）
3. **证据引用**：每条 conclusion 必须包含 `[Ex]` 证据指针

置信度惩罚：HIGH=-0.25, MEDIUM=-0.20, LOW=-0.10，最低 0.20。

## 报告格式化（report_formatter.py）

`AgentReportFormatter.format_report()` 将 `RuntimeDraft` + 工具结果组装为结构化 Markdown：

1. **结论摘要**：从 conclusions/action_items/risks 补齐 3-6 条，附加 `[Ex]` 证据指针
2. **行情与技术面**：趋势/动量/量价/形态/支撑压力/策略级输出
3. **关键指标表**：Markdown 表格（维度/指标/值/说明）
4. **基本面**：营收/净利/PE/PB 等（仅 stock 模式）
5. **催化剂与风险**：新闻摘要 + 风险清单 + 护栏冲突
6. **风险动作清单**：Markdown 表格
7. **估值情景**：base/bull/bear 三情景
8. **数据来源表**：证据 ID/描述/来源/时间/指针

## Skill 目录（skill_catalog.py）

```python
class SkillCatalog:
    def __init__(self, root_dir: Path)  # 通常指向 skills/ 目录
    def reload(self)                    # 扫描 */SKILL.md
    def list_skills(self) -> List[SkillSummary]
    def load_skill_content(name) -> Optional[str]
    def load_skill_body(name) -> Optional[str]   # 跳过 frontmatter
    # CRUD: create_skill, update_skill, delete_skill
```

`SKILL.md` 使用 YAML frontmatter 格式：

```yaml
---
name: stock_report
description: 个股分析报告
mode: stock
require_symbol: true
aliases: [stock, 个股]
---

正文内容...
```

`SkillSummary` 是 `frozen=True` 的 dataclass，存储 name、description、path、mode、require_symbol、aliases。

## AgentService（service.py）

```python
class AgentService:
    def __init__(self, config: AppConfig)
    async def run(request, provider_cfg, model, api_key, skill_content) -> AgentRunResult
    def to_analysis_payload(request, run_result) -> Tuple[AnalysisInput, AnalysisOutput]
```

组装流程：
1. `_build_tool_registry(config)` → 注册 `get_metrics` + `search_news`
2. `AgentOrchestrator(config, tool_registry)` → 执行
3. `to_analysis_payload()` → 将 `AgentRunResult` 转为标准 `AnalysisInput`/`AnalysisOutput`
