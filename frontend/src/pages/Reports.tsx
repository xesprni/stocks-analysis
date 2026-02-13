import { useEffect, useState } from "react";
import type { ReportDetail, ReportSummary, ReportTask } from "@/api/client";
import { MarkdownViewer } from "@/components/MarkdownViewer";
import { ReportDetailCharts } from "@/components/reports/ReportDetailCharts";
import { ReportHistoryCharts } from "@/components/reports/ReportHistoryCharts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { AlertCircle, CheckCircle2, Clock, FileText, Loader2, Trash2, XCircle } from "lucide-react";

type Props = {
  reports: ReportSummary[];
  tasks: ReportTask[];
  selectedRunId: string;
  detail: ReportDetail | null;
  onSelect: (runId: string) => void;
  onDelete: (runId: string) => Promise<void>;
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
          Succeeded
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

export function ReportsPage({ reports, tasks, selectedRunId, detail, onSelect, onDelete }: Props) {
  const [tickNow, setTickNow] = useState<number>(() => Date.now());
  const hasActiveTasks = tasks.some((t) => t.status === "PENDING" || t.status === "RUNNING");

  useEffect(() => {
    if (!hasActiveTasks) {
      return;
    }
    const timer = window.setInterval(() => {
      setTickNow(Date.now());
    }, 1000);
    return () => {
      window.clearInterval(timer);
    };
  }, [hasActiveTasks]);

  const activeTasks = tasks.filter((t) => t.status === "PENDING" || t.status === "RUNNING");
  const recentTasks = tasks.filter((t) => t.status === "SUCCEEDED" || t.status === "FAILED").slice(0, 10);

  return (
    <div className="space-y-6">
      {/* Hero header */}
      <section className="relative overflow-hidden rounded-3xl border border-emerald-300/50 bg-gradient-to-br from-emerald-500/15 via-teal-500/10 to-cyan-400/15 p-6">
        <div className="pointer-events-none absolute -left-12 -top-14 h-44 w-44 rounded-full bg-emerald-400/20 blur-3xl" />
        <div className="pointer-events-none absolute right-0 top-10 h-32 w-32 rounded-full bg-teal-400/20 blur-2xl" />
        <div className="pointer-events-none absolute -bottom-12 right-10 h-44 w-44 rounded-full bg-cyan-400/20 blur-3xl" />
        <div className="relative">
          <h2 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <FileText className="h-5 w-5 text-emerald-600" />
            Reports 报告中心
          </h2>
          <p className="mt-2 text-sm text-muted-foreground">
            查看已生成的分析报告与任务执行状态。当前 {reports.length} 份报告{activeTasks.length > 0 ? `，${activeTasks.length} 个任务执行中` : ""}。
          </p>
        </div>
      </section>

      {/* Task Status Panel */}
      {tasks.length > 0 && (
        <Card className="border-teal-200/60 bg-gradient-to-br from-white to-teal-50/40 dark:from-slate-900 dark:to-teal-950/20">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Loader2 className={`h-4 w-4 ${activeTasks.length > 0 ? "animate-spin text-blue-500" : "text-muted-foreground"}`} />
              Report Tasks
              {activeTasks.length > 0 && (
                <Badge variant="secondary" className="ml-1">
                  {activeTasks.length} active
                </Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {/* Active tasks */}
            {activeTasks.map((task) => (
              <div
                key={task.task_id}
                className="flex items-center justify-between rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 dark:border-blue-800 dark:bg-blue-950/40"
              >
                <div className="flex items-center gap-3">
                  {statusBadge(task.status)}
                  <span className="font-mono text-xs text-muted-foreground">{task.task_id.slice(0, 12)}...</span>
                </div>
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  <span>Started: {task.started_at ? formatTime(task.started_at) : formatTime(task.created_at)}</span>
                  <Badge variant="outline" className="font-mono">
                    {elapsed(task.started_at ?? task.created_at, undefined, tickNow)}
                  </Badge>
                </div>
              </div>
            ))}

            {/* Recent completed/failed tasks */}
            {recentTasks.length > 0 && activeTasks.length > 0 && <Separator />}
            {recentTasks.map((task) => (
              <div
                key={task.task_id}
                className={`flex items-center justify-between rounded-lg border px-4 py-2 ${
                  task.status === "FAILED"
                    ? "border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950/30"
                    : "border-border bg-muted/30"
                }`}
              >
                <div className="flex items-center gap-3">
                  {statusBadge(task.status)}
                  <span className="font-mono text-xs text-muted-foreground">{task.task_id.slice(0, 12)}...</span>
                  {task.status === "FAILED" && task.error_message && (
                    <span className="flex items-center gap-1 text-xs text-destructive">
                      <AlertCircle className="h-3 w-3" />
                      {task.error_message.length > 80 ? `${task.error_message.slice(0, 80)}...` : task.error_message}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  {task.finished_at && <span>{formatTime(task.finished_at)}</span>}
                  {task.started_at && task.finished_at && (
                    <Badge variant="outline" className="font-mono">
                      {elapsed(task.started_at, task.finished_at)}
                    </Badge>
                  )}
                </div>
              </div>
            ))}

            {tasks.length === 0 && (
              <div className="py-4 text-center text-sm text-muted-foreground">No report tasks yet.</div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Report List + Detail */}
      <div className="grid gap-6 lg:grid-cols-5">
        <div className="space-y-6 lg:col-span-2">
          <ReportHistoryCharts reports={reports} />
          <Card className="border-emerald-200/60 bg-gradient-to-br from-white to-emerald-50/40 dark:from-slate-900 dark:to-emerald-950/20">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileText className="h-4 w-4 text-emerald-600" />
                Report List
                <Badge variant="outline" className="ml-1 text-xs">
                  {reports.length} 份
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {reports.length === 0 ? (
                <div className="rounded-xl border border-dashed border-emerald-200 p-8 text-center text-sm text-muted-foreground dark:border-emerald-800">
                  No reports generated yet. Use the Run Reports page to generate a report.
                </div>
              ) : (
                <div className="overflow-x-auto rounded-lg border border-emerald-200/40 dark:border-emerald-800/30">
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-emerald-50/50 dark:bg-emerald-950/20">
                        <TableHead>Run ID</TableHead>
                        <TableHead>Provider</TableHead>
                        <TableHead>Model</TableHead>
                        <TableHead>Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {reports.map((item) => (
                        <TableRow
                          key={item.run_id}
                          className="cursor-pointer hover:bg-emerald-50/30 dark:hover:bg-emerald-950/10"
                          data-state={item.run_id === selectedRunId ? "selected" : undefined}
                          onClick={() => onSelect(item.run_id)}
                        >
                          <TableCell className="font-mono text-xs">{item.run_id}</TableCell>
                          <TableCell>{item.provider_id || "-"}</TableCell>
                          <TableCell>{item.model || "-"}</TableCell>
                          <TableCell>
                            <Button
                              size="sm"
                              variant="destructive"
                              onClick={(event) => {
                                event.stopPropagation();
                                void onDelete(item.run_id);
                              }}
                            >
                              <Trash2 className="mr-1 h-3.5 w-3.5" />
                              Delete
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <Card className="border-cyan-200/60 bg-gradient-to-br from-white to-cyan-50/40 dark:from-slate-900 dark:to-cyan-950/20 lg:col-span-3">
          <CardHeader>
            <CardTitle>Report Content</CardTitle>
          </CardHeader>
          <CardContent>
            {!detail ? (
              <div className="rounded-xl border border-dashed border-cyan-200 p-8 text-center text-sm text-muted-foreground dark:border-cyan-800">
                Select a report to view its content.
              </div>
            ) : (
              <div className="space-y-6">
                <ReportDetailCharts detail={detail} />
                <Separator />
                <MarkdownViewer markdown={detail.report_markdown} />
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
