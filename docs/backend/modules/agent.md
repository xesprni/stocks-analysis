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
- `get_fundamentals`（基本面）
- `get_filings`（US 文档）
- `search_news`（新闻检索，支持 ticker/别名匹配）
- `compute_indicators`（技术指标/策略打分/信号时间线）
- `peer_compare`（同行对比）
- `get_macro_data`（宏观资金流）

## 4. 执行流程（stock 模式）

1. 解析问题与时间范围（news/filing/price）。
2. 采集多周期行情（1d/5m/1m 可配置）。
3. 采集基本面、新闻、可选 filings、可选 peer compare。
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
