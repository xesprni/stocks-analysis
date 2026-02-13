import { useEffect, useState } from "react";
import type { StockAnalysisHistoryItem, StockAnalysisTask } from "@/api/client";
import { MarkdownViewer } from "@/components/MarkdownViewer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { AlertCircle, CheckCircle2, Clock, FileText, Loader2, RefreshCw, XCircle } from "lucide-react";

type Props = {
  runs: StockAnalysisHistoryItem[];
  tasks: StockAnalysisTask[];
  selectedRunId: string;
  detail: StockAnalysisHistoryItem | null;
  refreshing?: boolean;
  onRefresh?: () => void;
  onSelect: (runId: number) => void;
};

function statusBadge(status: StockAnalysisTask["status"]) {
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
    return d.toLocaleString(undefined, {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function StockResultsPage({ runs, tasks, selectedRunId, detail, refreshing, onRefresh, onSelect }: Props) {
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
      <section className="relative overflow-hidden rounded-3xl border border-blue-300/50 bg-gradient-to-br from-blue-500/15 via-cyan-500/10 to-emerald-400/15 p-6">
        <div className="pointer-events-none absolute -left-12 -top-14 h-44 w-44 rounded-full bg-blue-400/20 blur-3xl" />
        <div className="pointer-events-none absolute right-0 top-10 h-32 w-32 rounded-full bg-cyan-400/20 blur-2xl" />
        <div className="pointer-events-none absolute -bottom-12 right-10 h-44 w-44 rounded-full bg-emerald-400/20 blur-3xl" />
        <div className="relative flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
              <FileText className="h-5 w-5 text-blue-600" />
              Stock 分析结果
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              查看 Stock Terminal 历史分析与任务状态。当前 {runs.length} 条记录
              {activeTasks.length > 0 ? `，${activeTasks.length} 个任务执行中` : ""}。
            </p>
          </div>
          {onRefresh && (
            <Button variant="outline" onClick={onRefresh} disabled={refreshing}>
              <RefreshCw className={`mr-2 h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
              刷新数据
            </Button>
          )}
        </div>
      </section>

      {tasks.length > 0 && (
        <Card className="border-sky-200/60 bg-gradient-to-br from-white to-sky-50/40 dark:from-slate-900 dark:to-sky-950/20">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Loader2 className={`h-4 w-4 ${activeTasks.length > 0 ? "animate-spin text-blue-500" : "text-muted-foreground"}`} />
              Stock Analysis Tasks
              {activeTasks.length > 0 && (
                <Badge variant="secondary" className="ml-1">
                  {activeTasks.length} active
                </Badge>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {activeTasks.map((task) => (
              <div
                key={task.task_id}
                className="flex items-center justify-between rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 dark:border-blue-800 dark:bg-blue-950/40"
              >
                <div className="flex items-center gap-3">
                  {statusBadge(task.status)}
                  <span className="font-mono text-xs text-muted-foreground">{task.task_id.slice(0, 12)}...</span>
                  <Badge variant="outline">
                    {task.symbol}/{task.market}
                  </Badge>
                </div>
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  <span>Started: {task.started_at ? formatTime(task.started_at) : formatTime(task.created_at)}</span>
                  <Badge variant="outline" className="font-mono">
                    {elapsed(task.started_at ?? task.created_at, undefined, tickNow)}
                  </Badge>
                </div>
              </div>
            ))}

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
                  <Badge variant="outline" className="text-[11px]">
                    {task.symbol}/{task.market}
                  </Badge>
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
          </CardContent>
        </Card>
      )}

      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="border-blue-200/60 bg-gradient-to-br from-white to-blue-50/40 dark:from-slate-900 dark:to-blue-950/20 lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-blue-600" />
              Analysis Runs
              <Badge variant="outline" className="ml-1 text-xs">
                {runs.length} 条
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {runs.length === 0 ? (
              <div className="rounded-xl border border-dashed border-blue-200 p-8 text-center text-sm text-muted-foreground dark:border-blue-800">
                No stock analysis runs yet. Use Stock Terminal to run analysis.
              </div>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-blue-200/40 dark:border-blue-800/30">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-blue-50/50 dark:bg-blue-950/20">
                      <TableHead>ID</TableHead>
                      <TableHead>Symbol</TableHead>
                      <TableHead>Provider</TableHead>
                      <TableHead>Model</TableHead>
                      <TableHead>Time</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {runs.map((item) => (
                      <TableRow
                        key={item.id}
                        className="cursor-pointer hover:bg-blue-50/30 dark:hover:bg-blue-950/10"
                        data-state={String(item.id) === selectedRunId ? "selected" : undefined}
                        onClick={() => onSelect(item.id)}
                      >
                        <TableCell className="font-mono text-xs">#{item.id}</TableCell>
                        <TableCell>
                          <Badge variant="outline">{item.symbol}/{item.market}</Badge>
                        </TableCell>
                        <TableCell>{item.provider_id || "-"}</TableCell>
                        <TableCell>{item.model || "-"}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{formatTime(item.created_at)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="border-cyan-200/60 bg-gradient-to-br from-white to-cyan-50/40 dark:from-slate-900 dark:to-cyan-950/20 lg:col-span-3">
          <CardHeader>
            <CardTitle>Analysis Content</CardTitle>
          </CardHeader>
          <CardContent>
            {!detail ? (
              <div className="rounded-xl border border-dashed border-cyan-200 p-8 text-center text-sm text-muted-foreground dark:border-cyan-800">
                Select a stock analysis run to view details.
              </div>
            ) : (
              <div className="space-y-4">
                <div className="rounded-xl border bg-card/80 px-4 py-3 text-sm text-muted-foreground">
                  #{detail.id} · {detail.symbol}/{detail.market} · {detail.provider_id} / {detail.model} · {formatTime(detail.created_at)}
                </div>
                <Separator />
                <MarkdownViewer markdown={detail.markdown} />
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
