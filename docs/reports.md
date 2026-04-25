# Reports — 报告生成模块

`market_reporter/modules/reports/` 负责报告的异步任务管理、Skill 分发和报告持久化。

## 代码结构

```
reports/
├── service.py    # ReportService（异步任务 + 报告 CRUD + Telegram 通知）
├── renderer.py   # 报告渲染（辅助）
└── skills.py     # ReportSkillRegistry + ReportSkill（策略分发）
```

## ReportService（service.py）

报告生成的统一入口，管理异步任务生命周期。

### 异步任务

```python
class ReportService:
    async def start_report_async(overrides, user_id) -> ReportRunTaskView
    async def get_report_task(task_id, user_id) -> ReportRunTaskView
    async def list_report_tasks(user_id) -> List[ReportRunTaskView]
    async def run_report(overrides, user_id) -> RunResult
```

任务生命周期：`PENDING → RUNNING → SUCCEEDED/FAILED`

- `start_report_async()` 创建 `asyncio.Task` 后台执行，立即返回 task_id
- `_update_task()` 使用 `model_copy(update=...)` 保持 Pydantic 不可变语义
- 任务按 user_id 隔离

### 报告生成流程（run_report）

```
1. 解析 overrides → 构建 AppConfig
2. ReportSkillRegistry.resolve(skill_id, mode) → 获取 ReportSkill
3. AnalysisService.resolve_credentials() → 获取 provider/model/api_key
4. AgentService(config) → 构建 agent 环境
5. skill.run(ReportSkillContext) → 执行分析
6. 输出持久化：
   - output/{user_id}/YYYYMMDD_HHMMSS/
     ├── report.md        # Markdown 报告
     ├── raw_data.json    # 完整分析数据（含 agent 原始输出）
     └── meta.json        # 摘要 + warnings
7. Telegram 通知（成功/失败）
```

### 报告 CRUD

```python
def list_reports(user_id) -> List[ReportRunSummary]   # 按时间倒序列出
def get_report(run_id, user_id) -> ReportRunDetail     # 获取报告详情
def delete_report(run_id, user_id) -> bool             # 删除报告目录
```

- 报告输出路径：`output/` (全局) 或 `output/user_{id}/` (用户隔离)
- 目录名按时间戳 `YYYYMMDD_HHMMSS`，同一秒内追加 `_1`, `_2` 避免冲突
- `delete_report()` 包含路径安全检查，防止目录遍历

### 配置加载

```python
def _load_config(user_id) -> AppConfig
```

无 user_id 时加载全局配置；有 user_id 时通过 `UserConfigStore` 加载用户级覆盖配置（无覆盖时从全局配置初始化）。

## Skill 系统（skills.py）

### 核心 Protocol

```python
class ReportSkill(Protocol):
    skill_id: str
    mode: str
    aliases: Sequence[str]
    async def run(self, context: ReportSkillContext) -> ReportSkillResult: ...
```

### ReportSkillContext

```python
@dataclass
class ReportSkillContext:
    config: AppConfig
    overrides: Optional[RunRequest]
    generated_at: str
    agent_service: AgentService
    provider_cfg: AnalysisProviderConfig
    selected_model: str
    api_key: Optional[str]
    skill_content: str = ""
```

### ReportSkillResult

```python
@dataclass
class ReportSkillResult:
    markdown: str
    analysis_payload: Dict[str, object]
    news_total: int
    warnings: List[str]
    mode: str
    skill_id: str
```

### Skill 实现类

#### CatalogReportSkill

从 `SkillCatalog` 加载的 SKILL.md 文件驱动的 skill，支持 market/stock 两种 mode：

```python
class CatalogReportSkill:
    def __init__(self, skill_id, mode, aliases, require_symbol, skill_content)
    async def run(self, context) -> ReportSkillResult
```

内部调用 `_run_single_agent_report()` 构建单个 `AgentRunRequest`，执行 agent 分析。

#### WatchlistReportSkill

持仓报告专用 skill，遍历用户自选股逐个分析：

```python
class WatchlistReportSkill:
    skill_id = "watchlist_report"
    mode = "watchlist"

    async def run(self, context) -> ReportSkillResult
```

业务逻辑：
1. 从 `WatchlistService` 获取启用的自选股列表
2. 逐个构建 `AgentRunRequest(mode="stock")` 执行分析
3. 汇总：平均置信度、组合情绪（bullish/bearish/neutral 投票）
4. 生成持仓概览 Markdown 表格 + 各标的详细分析

### ReportSkillRegistry

```python
class ReportSkillRegistry:
    def __init__(self, catalog: Optional[SkillCatalog])
    def resolve(skill_id, mode) -> ReportSkill
    def reload(self)
```

- 从 `SkillCatalog` 加载所有带 `mode` 的 skill
- 按 skill_id、mode、aliases 建立多级别名索引
- 无 catalog skills 时注册内置默认值（market_report、stock_report、watchlist_report）
- `resolve()` 优先按 skill_id 查找，fallback 到 mode

## 关键数据流

```
API Request (RunRequest)
  → ReportService.start_report_async()
    → ReportSkillRegistry.resolve(skill_id, mode)
    → ReportSkill.run(ReportSkillContext)
      → AgentService.run(AgentRunRequest)
        → OpenAIToolRuntime (LLM 循环)
        → ToolRegistry.execute (get_metrics / search_news)
      → AgentRunResult
    → ReportSkillResult (markdown + analysis_payload)
  → 写入文件系统 (report.md + raw_data.json + meta.json)
  → Telegram 通知
  → RunResult
```
