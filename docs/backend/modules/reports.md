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
3. 执行 agent 分析（market 或 stock）。
4. 生成 `raw_payload` 与 markdown。
5. 写入 `output/<run_id>/`：
   - `report.md`
   - `raw_data.json`
   - `meta.json`

## 5. 产物字段

- `meta.json`：摘要 + warnings
- `raw_data.json`：完整分析 payload（含 tool_calls、evidence、guardrail）
- `report.md`：最终报告正文

## 6. 失败降级

- 模型执行失败时生成 fallback 报告与低置信度输出。
- 报告目录命名冲突时自动追加序号，保证幂等写入。

## 7. 删除保护

`delete_report(run_id)` 会校验目标目录必须在 `output_root` 内，防止误删越界路径。
