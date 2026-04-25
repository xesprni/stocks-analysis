import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import type { ReportDetail, ReportSummary, ReportTask } from "@/api/client";
import { api, getReportTaskWebSocketUrl, reportTaskSchema } from "@/api/client";
import { MarkdownViewer } from "@/components/MarkdownViewer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  Clock,
  Copy,
  FileText,
  Loader2,
  RefreshCw,
  Save,
  Trash2,
  Wrench,
  XCircle,
} from "lucide-react";

type Props = {
  reports: ReportSummary[];
  tasks: ReportTask[];
  selectedRunId: string;
  detail: ReportDetail | null;
  refreshing?: boolean;
  onRefresh?: () => void;
  onSelectSavedReport: (runId: string) => void;
  onDeleteSavedReport: (runId: string) => Promise<void>;
};

function statusBadge(status: ReportTask["status"]) {
  switch (status) {
    case "PENDING":
      return (
        <Badge variant="secondary" className="gap-1">
          <Clock className="h-3 w-3" />
          Pending
        </Badge>
      );
    case "RUNNING":
      return (
        <Badge className="gap-1 bg-blue-600 text-white hover:bg-blue-700">
          <Loader2 className="h-3 w-3 animate-spin" />
          Running
        </Badge>
      );
    case "SUCCEEDED":
      return (
        <Badge className="gap-1 bg-green-600 text-white hover:bg-green-700">
          <CheckCircle2 className="h-3 w-3" />
          Done
        </Badge>
      );
    case "FAILED":
      return (
        <Badge variant="destructive" className="gap-1">
          <XCircle className="h-3 w-3" />
          Failed
        </Badge>
      );
    default:
      return <Badge variant="outline">{status}</Badge>;
  }
}

function elapsed(start: string, end?: string | null, nowMs?: number): string {
  const startMs = new Date(start).getTime();
  const endMs = end ? new Date(end).getTime() : (nowMs ?? Date.now());
  const diffSec = Math.max(0, Math.round((endMs - startMs) / 1000));
  if (diffSec < 60) return `${diffSec}s`;
  const min = Math.floor(diffSec / 60);
  const sec = diffSec % 60;
  return `${min}m ${sec}s`;
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return iso;
  }
}

function StepCard({ step, index, isLatest }: { step: Record<string, unknown>; index: number; isLatest?: boolean }) {
  const tool = String(step.tool || "unknown");
  const status = String(step.status || "");
  const args = step.arguments as Record<string, unknown> | undefined;
  const preview = step.result_preview as Record<string, unknown> | undefined;
  const duration = step.duration_ms as number | undefined;

  // Model thinking step
  if (tool === "__model_thinking__") {
    const stepNum = args?.step as number | undefined;
    const maxSteps = args?.max_steps as number | undefined;
    return (
      <div className="rounded-lg border border-violet-200 bg-violet-50/50 px-4 py-3 dark:border-violet-800 dark:bg-violet-950/30">
        <div className="flex items-center gap-2">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-violet-600 text-[10px] font-bold text-white">
            {stepNum ?? index + 1}
          </span>
          <Loader2 className="h-3.5 w-3.5 animate-spin text-violet-600" />
          <span className="text-sm font-medium text-violet-700 dark:text-violet-300">
            模型正在思考...
          </span>
          {maxSteps != null && (
            <span className="text-xs text-muted-foreground">
              轮次 {stepNum}/{maxSteps}
            </span>
          )}
        </div>
      </div>
    );
  }

  if (tool === "__agent_finished__") {
    const reason = String(args?.reason || "unknown");
    const reasonText: Record<string, string> = {
      model_final_response: "模型已返回最终结论",
      tool_budget_exhausted: "工具调用达到上限",
      step_budget_exhausted: "LLM 轮次达到上限",
      wall_timeout: "执行达到时间上限",
    };
    return (
      <div className="rounded-lg border border-emerald-200 bg-emerald-50/60 px-4 py-3 dark:border-emerald-800 dark:bg-emerald-950/30">
        <div className="flex items-center gap-2">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-emerald-600 text-[10px] font-bold text-white">
            {index + 1}
          </span>
          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
          <span className="text-sm font-medium text-emerald-700 dark:text-emerald-300">
            {reasonText[reason] ?? "Agent 已结束"}
          </span>
          <span className="text-xs text-muted-foreground">
            工具调用 {String(args?.tool_calls ?? 0)} 次
          </span>
        </div>
        {preview?.summary ? (
          <div className="mt-2 text-xs text-muted-foreground">
            {String(preview.summary)}
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-blue-200 bg-blue-50/50 px-4 py-3 dark:border-blue-800 dark:bg-blue-950/30">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-600 text-[10px] font-bold text-white">
            {index + 1}
          </span>
          <Wrench className="h-3.5 w-3.5 text-blue-600" />
          <span className="font-mono text-sm font-medium">{tool}</span>
          {duration != null && (
            <span className="text-xs text-muted-foreground">{duration}ms</span>
          )}
          {status === "error" && (
            <span className="text-xs text-destructive">failed</span>
          )}
        </div>
      </div>
      {args && Object.keys(args).length > 0 && (
        <pre className="mt-2 overflow-x-auto rounded bg-muted/50 px-2 py-1 text-xs text-muted-foreground">
          {JSON.stringify(args, null, 2)}
        </pre>
      )}
      {preview && Object.keys(preview).length > 0 && (
        <div className="mt-2 text-xs text-muted-foreground">
          {preview.error ? (
            <span className="text-destructive">Error: {String(preview.error)}</span>
          ) : (
            <span>
              {preview.quote
                ? `quote: ${String((preview.quote as Record<string, unknown>).price ?? "")}`
                : ""}
              {(preview.bars_count ?? preview.items_count ?? preview.points_count) != null
                ? ` | ${String(preview.bars_count ?? preview.items_count ?? preview.points_count)} 条数据`
                : ""}
              {preview.source ? ` | ${String(preview.source)}` : ""}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

export function ReportsPage({
  reports,
  tasks,
  selectedRunId,
  detail,
  refreshing,
  onRefresh,
  onSelectSavedReport,
  onDeleteSavedReport,
}: Props) {
  const queryClient = useQueryClient();
  const [tickNow, setTickNow] = useState<number>(() => Date.now());
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [savedReportSelected, setSavedReportSelected] = useState(false);
  const [saving, setSaving] = useState(false);
  const [copied, setCopied] = useState(false);

  const hasActiveTasks = tasks.some((t) => t.status === "PENDING" || t.status === "RUNNING");
  const activeTasks = useMemo(
    () => tasks.filter((t) => t.status === "PENDING" || t.status === "RUNNING"),
    [tasks]
  );
  const completedTasks = useMemo(
    () => tasks.filter((t) => t.status === "SUCCEEDED" || t.status === "FAILED"),
    [tasks]
  );
  const selectedTask = tasks.find((t) => t.task_id === selectedTaskId);
  const selectedTaskStatus = selectedTask?.status;

  useEffect(() => {
    if (!hasActiveTasks) return;
    const timer = window.setInterval(() => setTickNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [hasActiveTasks]);

  useEffect(() => {
    if (savedReportSelected) {
      return;
    }
    if (selectedTaskId && tasks.some((task) => task.task_id === selectedTaskId)) {
      return;
    }
    const nextTask = activeTasks[0] ?? tasks[0] ?? null;
    setSelectedTaskId(nextTask?.task_id ?? null);
  }, [activeTasks, savedReportSelected, selectedTaskId, tasks]);

  useEffect(() => {
    if (!selectedTaskId || !selectedTaskStatus) {
      return;
    }
    if (selectedTaskStatus !== "PENDING" && selectedTaskStatus !== "RUNNING") {
      return;
    }

    const socket = new WebSocket(getReportTaskWebSocketUrl(selectedTaskId));
    socket.onmessage = (event) => {
      try {
        const payload = reportTaskSchema.parse(JSON.parse(event.data));
        queryClient.setQueryData<ReportTask[]>(["report-tasks"], (current = []) => {
          let found = false;
          const next = current.map((task) => {
            if (task.task_id !== payload.task_id) {
              return task;
            }
            found = true;
            return payload;
          });
          return found ? next : [payload, ...next];
        });
        if (payload.status === "SUCCEEDED" || payload.status === "FAILED") {
          void queryClient.invalidateQueries({ queryKey: ["report-tasks"] });
        }
      } catch {
        // Ignore malformed transient frames; polling remains as a fallback.
      }
    };
    socket.onerror = () => {
      void queryClient.invalidateQueries({ queryKey: ["report-tasks"] });
    };

    return () => {
      socket.close();
    };
  }, [queryClient, selectedTaskId, selectedTaskStatus]);

  const handleSave = async (taskId: string) => {
    setSaving(true);
    try {
      await api.saveReport(taskId);
      onRefresh?.();
    } finally {
      setSaving(false);
    }
  };

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-6">
      {/* Hero header */}
      <section className="relative overflow-hidden rounded-3xl border border-emerald-300/50 bg-gradient-to-br from-emerald-500/15 via-teal-500/10 to-cyan-400/15 p-6">
        <div className="pointer-events-none absolute -left-12 -top-14 h-44 w-44 rounded-full bg-emerald-400/20 blur-3xl" />
        <div className="pointer-events-none absolute right-0 top-10 h-32 w-32 rounded-full bg-teal-400/20 blur-2xl" />
        <div className="pointer-events-none absolute -bottom-12 right-10 h-44 w-44 rounded-full bg-cyan-400/20 blur-3xl" />
        <div className="relative flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
              <FileText className="h-5 w-5 text-emerald-600" />
              Reports 报告中心
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              {activeTasks.length > 0
                ? `${activeTasks.length} 个任务执行中`
                : reports.length > 0
                  ? `${reports.length} 份已保存报告`
                  : "从 Dashboard 触发市场或个股分析"}
            </p>
          </div>
          {onRefresh && (
            <Button variant="outline" onClick={onRefresh} disabled={refreshing}>
              <RefreshCw className={`mr-2 h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
              刷新
            </Button>
          )}
        </div>
      </section>

      {/* Task list — always visible */}
      <Card className="border-teal-200/60 bg-gradient-to-br from-white to-teal-50/40 dark:from-slate-900 dark:to-teal-950/20">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Loader2 className={`h-4 w-4 ${activeTasks.length > 0 ? "animate-spin text-blue-500" : "text-muted-foreground"}`} />
            任务列表
            {activeTasks.length > 0 && (
              <Badge variant="secondary" className="ml-1">
                {activeTasks.length} active
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {tasks.length === 0 && (
            <div className="py-4 text-center text-sm text-muted-foreground">
              暂无任务。前往 Dashboard 触发市场或个股分析。
            </div>
          )}

          {/* Active tasks */}
          {activeTasks.map((task) => (
            <div
              key={task.task_id}
              className={`flex cursor-pointer items-center justify-between rounded-lg border px-4 py-3 transition-colors hover:bg-blue-50/50 dark:hover:bg-blue-950/20 ${
                selectedTaskId === task.task_id
                  ? "border-blue-400 bg-blue-50 dark:border-blue-700 dark:bg-blue-950/30"
                  : "border-blue-200 bg-blue-50/50 dark:border-blue-800 dark:bg-blue-950/20"
              }`}
              onClick={() => {
                setSavedReportSelected(false);
                setSelectedTaskId(task.task_id);
              }}
            >
              <div className="flex items-center gap-3">
                {statusBadge(task.status)}
                <span className="text-sm text-muted-foreground">
                  {task.raw_data?.mode ?? "market"} {(task.raw_data?.market ?? task.raw_data?.symbol ?? "") as string}
                </span>
                {task.steps.length > 0 && (
                  <Badge variant="outline" className="text-xs">
                    {task.steps.length} 步骤
                  </Badge>
                )}
              </div>
              <div className="flex items-center gap-2">
                {task.started_at && (
                  <Badge variant="outline" className="font-mono text-xs">
                    {elapsed(task.started_at, undefined, tickNow)}
                  </Badge>
                )}
                <ChevronRight className="h-4 w-4 text-muted-foreground" />
              </div>
            </div>
          ))}

          {/* Completed tasks */}
          {completedTasks.map((task) => (
            <div
              key={task.task_id}
              className={`flex cursor-pointer items-center justify-between rounded-lg border px-4 py-2 transition-colors hover:bg-muted/50 ${
                selectedTaskId === task.task_id ? "border-emerald-300 bg-emerald-50/50 dark:border-emerald-700 dark:bg-emerald-950/20" : ""
              } ${
                task.status === "FAILED"
                  ? "border-red-200 bg-red-50/50 dark:border-red-800 dark:bg-red-950/20"
                  : "border-border"
              }`}
              onClick={() => {
                setSavedReportSelected(false);
                setSelectedTaskId(task.task_id);
              }}
            >
              <div className="flex items-center gap-3">
                {statusBadge(task.status)}
                <span className="text-sm text-muted-foreground">
                  {task.raw_data?.mode ?? "market"} {(task.raw_data?.market ?? task.raw_data?.symbol ?? "") as string}
                </span>
                {task.status === "FAILED" && task.error_message && (
                  <span className="flex items-center gap-1 text-xs text-destructive">
                    <AlertCircle className="h-3 w-3" />
                    {task.error_message.length > 60 ? `${task.error_message.slice(0, 60)}...` : task.error_message}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                {task.finished_at && <span>{formatTime(task.finished_at)}</span>}
                {task.started_at && task.finished_at && (
                  <Badge variant="outline" className="font-mono text-xs">
                    {elapsed(task.started_at, task.finished_at)}
                  </Badge>
                )}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Agent interaction panel — shown when a task is selected */}
      {selectedTask && (
        <Card className="border-blue-200/60 bg-gradient-to-br from-white to-blue-50/40 dark:from-slate-900 dark:to-blue-950/20">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="flex items-center gap-2 text-base">
                  {selectedTask.status === "RUNNING" && <Loader2 className="h-4 w-4 animate-spin text-blue-500" />}
                  Agent 交互详情
                </CardTitle>
                <CardDescription>
                  任务 {selectedTask.task_id.slice(0, 12)}...
                  {selectedTask.status === "RUNNING" && " · 执行中"}
                  {selectedTask.started_at && ` · ${elapsed(selectedTask.started_at, selectedTask.finished_at, tickNow)}`}
                </CardDescription>
              </div>
              {selectedTask.status === "SUCCEEDED" && selectedTask.report_markdown && (
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => handleCopy(selectedTask.report_markdown!)}>
                    <Copy className="mr-1 h-3.5 w-3.5" />
                    {copied ? "已复制" : "复制"}
                  </Button>
                  <Button size="sm" disabled={saving} onClick={() => handleSave(selectedTask.task_id)}>
                    <Save className="mr-1 h-3.5 w-3.5" />
                    {saving ? "保存中..." : "保存报告"}
                  </Button>
                </div>
              )}
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Agent steps — show latest thinking + all tool calls */}
            {selectedTask.steps.length > 0 && (() => {
              // Show only the last thinking step + all non-thinking steps
              const displaySteps: Array<{ step: Record<string, unknown>; originalIndex: number }> = [];
              let lastThinkingIdx = -1;
              selectedTask.steps.forEach((step, i) => {
                if (String(step.tool) === "__model_thinking__") {
                  lastThinkingIdx = i;
                }
              });
              selectedTask.steps.forEach((step, i) => {
                const isThinking = String(step.tool) === "__model_thinking__";
                if (!isThinking || i === lastThinkingIdx) {
                  displaySteps.push({ step, originalIndex: i });
                }
              });
              return (
                <div className="space-y-2">
                  {displaySteps.map(({ step, originalIndex }, i) => (
                    <StepCard
                      key={originalIndex}
                      step={step}
                      index={originalIndex}
                      isLatest={i === displaySteps.length - 1 && selectedTask.status === "RUNNING"}
                    />
                  ))}
                </div>
              );
            })()}

            {/* Running but no steps yet — agent starting */}
            {selectedTask.status === "RUNNING" && selectedTask.steps.length === 0 && (
              <div className="rounded-lg border border-violet-200 bg-violet-50/50 px-4 py-3 dark:border-violet-800 dark:bg-violet-950/30">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin text-violet-600" />
                  Agent 正在初始化，连接分析模型中...
                </div>
              </div>
            )}

            {/* Pending */}
            {selectedTask.status === "PENDING" && (
              <div className="flex items-center gap-2 py-4 text-sm text-muted-foreground">
                <Clock className="h-4 w-4" />
                任务排队中，等待执行...
              </div>
            )}

            {/* Error */}
            {selectedTask.status === "FAILED" && selectedTask.error_message && (
              <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/30 dark:text-red-300">
                {selectedTask.error_message}
              </div>
            )}

            {/* Report markdown preview */}
            {selectedTask.report_markdown && (
              <>
                <Separator />
                <MarkdownViewer markdown={selectedTask.report_markdown} />
              </>
            )}
          </CardContent>
        </Card>
      )}

      {/* Saved reports list */}
      {reports.length > 0 && (
        <Card className="border-emerald-200/60 bg-gradient-to-br from-white to-emerald-50/40 dark:from-slate-900 dark:to-emerald-950/20">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <FileText className="h-4 w-4 text-emerald-600" />
              已保存报告
              <Badge variant="outline" className="ml-1 text-xs">
                {reports.length} 份
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto rounded-lg border border-emerald-200/40 dark:border-emerald-800/30">
              <Table>
                <TableHeader>
                  <TableRow className="bg-emerald-50/50 dark:bg-emerald-950/20">
                    <TableHead>Run ID</TableHead>
                    <TableHead>Mode</TableHead>
                    <TableHead>Provider</TableHead>
                    <TableHead>Model</TableHead>
                    <TableHead>操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {reports.map((item) => (
                      <TableRow
                        key={item.run_id}
                        className={`cursor-pointer hover:bg-emerald-50/30 dark:hover:bg-emerald-950/10 ${
                          item.run_id === selectedRunId ? "bg-emerald-50/60 dark:bg-emerald-950/20" : ""
                        }`}
                      onClick={() => {
                        setSavedReportSelected(true);
                        setSelectedTaskId(null);
                        onSelectSavedReport(item.run_id);
                      }}
                    >
                      <TableCell className="font-mono text-xs">{item.run_id}</TableCell>
                      <TableCell>{item.mode || "market"}</TableCell>
                      <TableCell>{item.provider_id || "-"}</TableCell>
                      <TableCell>{item.model || "-"}</TableCell>
                      <TableCell>
                        <Button
                          size="sm"
                          variant="destructive"
                          onClick={(event) => {
                            event.stopPropagation();
                            void onDeleteSavedReport(item.run_id);
                          }}
                        >
                          <Trash2 className="mr-1 h-3.5 w-3.5" />
                          删除
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Saved report detail */}
      {selectedRunId && detail && !selectedTaskId && (
        <Card className="border-cyan-200/60 bg-gradient-to-br from-white to-cyan-50/40 dark:from-slate-900 dark:to-cyan-950/20">
          <CardHeader>
            <CardTitle>报告内容</CardTitle>
            <CardDescription>{selectedRunId}</CardDescription>
          </CardHeader>
          <CardContent>
            <MarkdownViewer markdown={detail.report_markdown} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
