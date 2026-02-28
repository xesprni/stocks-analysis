# reports 模块

## 1. 模块职责

提供市场/个股报告任务执行、异步任务管理、历史报告检索与删除能力。

## 2. 核心文件

- `market_reporter/modules/reports/service.py`
- `market_reporter/modules/reports/renderer.py`

## 3. 任务模型

- 同步：`run_report(overrides)`
- 异步：`start_report_async(overrides)`
- 内存任务状态：`_tasks` + `ReportRunTaskView`

状态：`PENDING/RUNNING/SUCCEEDED/FAILED`。

## 4. 报告执行流程

1. 读取配置并应用请求覆盖项（provider/model/timezone 等）。
2. 构建 `NewsService/FundFlowService/AnalysisService/AgentService`。
3. 通过 `ReportSkillRegistry` 选择并执行报告 skill（非硬编码分支）。
4. 生成 `raw_payload` 与 markdown。
5. 写入 `output/<run_id>/`：
   - `report.md`
   - `raw_data.json`
   - `meta.json`

### 4.1 内置报告 Skills

- `market_report`（别名 `market`）
- `stock_report`（别名 `stock`）
- `watchlist_report`（别名 `watchlist`）

`RunRequest` 新增可选字段 `skill_id`，用于显式选择 skill；未传时仍按 `mode` 兼容映射。

## 5. 产物字段

- `meta.json`：摘要 + warnings
- `raw_data.json`：完整分析 payload（含 tool_calls、evidence、guardrail）
- `report.md`：最终报告正文

## 6. 失败降级

- 模型执行失败时生成 fallback 报告与低置信度输出。
- 报告目录命名冲突时自动追加序号，保证幂等写入。

## 7. 删除保护

`delete_report(run_id)` 会校验目标目录必须在 `output_root` 内，防止误删越界路径。

## 8. 配置示例

### 8.1 完整配置（`config/settings.yaml`）

```yaml
reports:
  output_root: output
  default_skill: market_report
  max_concurrent_tasks: 3
  retention_days: 30
```

### 8.2 Skill 配置说明

| Skill ID | 别名 | 说明 | 输出内容 |
|----------|------|------|----------|
| `market_report` | `market` | 市场总览报告 | 新闻摘要、资金流、宏观分析 |
| `stock_report` | `stock` | 个股深度报告 | 行情分析、基本面、技术指标 |
| `watchlist_report` | `watchlist` | Watchlist 批量报告 | 所有 watchlist 项目概览 |

## 9. API 使用示例

### 9.1 同步生成报告

```bash
curl -X POST http://localhost:8000/api/reports/run \
  -H "Content-Type: application/json" \
  -d '{
    "skill_id": "market_report",
    "provider_id": "openai_compatible",
    "model": "gpt-4"
  }'

# 响应
{
  "run_id": "20240115_103000",
  "status": "completed",
  "output_path": "output/20240115_103000",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### 9.2 异步生成报告

```bash
curl -X POST http://localhost:8000/api/reports/run/async \
  -H "Content-Type: application/json" \
  -d '{
    "skill_id": "stock_report",
    "symbol": "AAPL",
    "market": "US"
  }'

# 响应
{
  "task_id": "task_abc123",
  "status": "PENDING",
  "created_at": "2024-01-15T10:30:00Z"
}
```

### 9.3 查询任务状态

```bash
curl -X GET http://localhost:8000/api/reports/tasks/task_abc123

# 响应
{
  "task_id": "task_abc123",
  "status": "RUNNING",
  "progress": 50,
  "created_at": "2024-01-15T10:30:00Z",
  "started_at": "2024-01-15T10:30:05Z"
}
```

### 9.4 获取报告列表

```bash
curl -X GET "http://localhost:8000/api/reports?limit=10"

# 响应
[
  {
    "run_id": "20240115_103000",
    "skill_id": "market_report",
    "status": "completed",
    "created_at": "2024-01-15T10:30:00Z",
    "size_kb": 125
  }
]
```

### 9.5 获取报告详情

```bash
curl -X GET http://localhost:8000/api/reports/20240115_103000

# 响应
{
  "run_id": "20240115_103000",
  "skill_id": "market_report",
  "status": "completed",
  "markdown": "# 市场总览报告\n\n...",
  "meta": {
    "summary": "今日市场整体上涨...",
    "warnings": [],
    "confidence": 85
  },
  "created_at": "2024-01-15T10:30:00Z"
}
```

### 9.6 删除报告

```bash
curl -X DELETE http://localhost:8000/api/reports/20240115_103000

# 响应
{
  "status": "deleted",
  "run_id": "20240115_103000"
}
```

## 10. 报告模板示例

### 10.1 市场总览报告模板

```markdown
# 市场总览报告

**生成时间**: {timestamp}
**置信度**: {confidence}%

## 摘要

{summary}

## 市场概况

### 指数表现

| 指数 | 当前点位 | 日涨跌 | 涨跌幅 |
|------|----------|--------|--------|
| {index_table} |

### 资金流向

{fund_flow_summary}

## 新闻摘要

### 重要新闻

{news_summary}

## 宏观分析

{macro_analysis}

## 风险提示

{risk_factors}

---
*本报告由 AI 生成，仅供参考*
```

### 10.2 个股深度报告模板

```markdown
# {symbol} 深度分析报告

**股票名称**: {name}
**当前价格**: {price}
**生成时间**: {timestamp}
**置信度**: {confidence}%

## 摘要

{summary}

## 行情分析

### 价格走势

{price_analysis}

### 技术指标

| 指标 | 当前值 | 信号 |
|------|--------|------|
| {indicator_table} |

## 基本面分析

{fundamentals}

## 新闻动态

{news}

## 投资建议

{recommendations}

### 仓位建议

- **建议仓位**: {position_suggestion}
- **止损价位**: {stop_loss}
- **止盈价位**: {take_profit}

## 风险提示

{risk_factors}

## 数据来源

{data_sources}

---
*本报告由 AI 生成，仅供参考*
```

## 11. 输出格式说明

### 11.1 meta.json 结构

```json
{
  "run_id": "20240115_103000",
  "skill_id": "market_report",
  "summary": "今日市场整体上涨，北向资金净流入52亿...",
  "confidence": 85,
  "warnings": [],
  "data_sources": ["yfinance", "eastmoney", "rss"],
  "tool_calls": 15,
  "duration_seconds": 45,
  "created_at": "2024-01-15T10:30:00Z"
}
```

### 11.2 raw_data.json 结构

```json
{
  "input": {
    "skill_id": "market_report",
    "config": {...}
  },
  "tool_calls": [
    {
      "name": "get_macro_data",
      "arguments": {...},
      "result": {...},
      "duration_ms": 150
    }
  ],
  "evidence": [
    {
      "id": "E1",
      "type": "price",
      "source": "yfinance",
      "content": "AAPL 当前价格 $178.52"
    }
  ],
  "guardrail_result": {
    "passed": true,
    "warnings": [],
    "confidence_adjustment": 0
  },
  "draft": {
    "content": "## 市场总览\n\n...",
    "confidence": 90
  }
}
```

### 11.3 report.md 示例

```markdown
# 市场总览报告

**生成时间**: 2024-01-15 10:30:00
**置信度**: 85%

## 摘要

今日市场整体上涨，北向资金净流入52亿元，南向资金净流出15亿元。
主要指数表现良好，上证指数上涨1.2%，深证成指上涨1.5%。

## 市场概况

### 指数表现

| 指数 | 当前点位 | 日涨跌 | 涨跌幅 |
|------|----------|--------|--------|
| 上证指数 | 3050.12 | +36.25 | +1.20% |
| 深证成指 | 10250.35 | +151.82 | +1.50% |
| 道琼斯 | 37850.25 | +125.50 | +0.33% |

### 资金流向

- 北向资金净流入：52.3亿元
- 南向资金净流出：15.6亿元
- 主力资金净流入：125.8亿元

## 新闻摘要

### 重要新闻

1. **央行宣布降准0.5个百分点**
   - 时间：2024-01-15 10:00
   - 影响：利好银行、地产板块

2. **科技部发布人工智能发展规划**
   - 时间：2024-01-15 09:30
   - 影响：利好AI相关概念股

## 宏观分析

[E1] 根据央行最新数据，M2增速维持在8.5%左右，流动性保持合理充裕。
[E2] 北向资金连续5日净流入，显示外资对A股市场信心增强。

当前市场处于震荡上行阶段，建议关注：
1. 低估值蓝筹股
2. 科技成长股
3. 消费复苏概念

## 风险提示

- 美联储加息预期仍存不确定性
- 地缘政治风险需关注
- 市场成交量有待进一步放大

---
*本报告由 AI 生成，仅供参考*
```

## 12. 任务状态管理

### 12.1 任务状态流转

```text
PENDING -> RUNNING -> SUCCEEDED
                   -> FAILED
```

### 12.2 任务状态说明

| 状态 | 说明 |
|------|------|
| `PENDING` | 任务已创建，等待执行 |
| `RUNNING` | 任务正在执行中 |
| `SUCCEEDED` | 任务执行成功 |
| `FAILED` | 任务执行失败 |

### 12.3 内存任务管理

```python
class ReportTaskManager:
    _tasks: Dict[str, ReportRunTaskView] = {}
    _max_tasks: int = 100
    
    def add_task(self, task: ReportRunTaskView) -> None:
        """添加任务，超过限制时清理最旧的任务"""
        if len(self._tasks) >= self._max_tasks:
            self._cleanup_old_tasks()
        self._tasks[task.task_id] = task
    
    def get_task(self, task_id: str) -> Optional[ReportRunTaskView]:
        """获取任务状态"""
        return self._tasks.get(task_id)
    
    def list_tasks(self) -> List[ReportRunTaskView]:
        """列出所有任务"""
        return list(self._tasks.values())
```

## 13. 与其他模块的交互

### 13.1 与 analysis 模块

- reports 模块调用 `AnalysisService.resolve_credentials()` 获取分析凭据
- 通过 `AgentService` 执行分析任务

### 13.2 与 news 模块

- 市场报告包含新闻摘要
- 调用 `NewsService.collect()` 获取新闻数据

### 13.3 与 fund_flow 模块

- 市场报告包含资金流数据
- 调用 `FundFlowService.collect()` 获取资金流数据

### 13.4 与 market_data 模块

- 报告中包含指数行情数据
- 调用 `MarketDataService` 获取行情数据
