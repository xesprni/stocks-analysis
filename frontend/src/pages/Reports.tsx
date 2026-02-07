import { useEffect, useRef } from "react";
import type { ReportDetail, ReportSummary, ReportTask } from "@/api/client";
import { MarkdownViewer } from "@/components/MarkdownViewer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AlertCircle, CheckCircle2, Clock, Loader2, Trash2, XCircle } from "lucide-react";

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

function elapsed(start: string, end?: string | null): string {
  const startMs = new Date(start).getTime();
  const endMs = end ? new Date(end).getTime() : Date.now();
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
  // Force re-render every second while there are active tasks, so elapsed time updates
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const hasActiveTasks = tasks.some((t) => t.status === "PENDING" || t.status === "RUNNING");

  useEffect(() => {
    if (hasActiveTasks) {
      intervalRef.current = setInterval(() => {
        // trigger re-render by forcing update — we rely on parent re-render via refetchInterval
      }, 1000);
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [hasActiveTasks]);

  const activeTasks = tasks.filter((t) => t.status === "PENDING" || t.status === "RUNNING");
  const recentTasks = tasks.filter((t) => t.status === "SUCCEEDED" || t.status === "FAILED").slice(0, 10);

  return (
    <div className="space-y-6">
      {/* Task Status Panel */}
      {tasks.length > 0 && (
        <Card>
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
                    {elapsed(task.started_at ?? task.created_at)}
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
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Report List</CardTitle>
          </CardHeader>
          <CardContent>
            {reports.length === 0 ? (
              <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
                No reports generated yet. Use the Dashboard to generate a report.
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
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
                      className="cursor-pointer"
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
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>Report Content</CardTitle>
          </CardHeader>
          <CardContent>
            {!detail ? (
              <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
                Select a report to view its content.
              </div>
            ) : (
              <Tabs defaultValue="markdown">
                <TabsList>
                  <TabsTrigger value="markdown">Markdown</TabsTrigger>
                  <TabsTrigger value="json">Raw JSON</TabsTrigger>
                </TabsList>
                <TabsContent value="markdown">
                  <MarkdownViewer markdown={detail.report_markdown} />
                </TabsContent>
                <TabsContent value="json">
                  <pre className="max-h-[600px] overflow-auto rounded-md bg-muted p-4 text-xs">
                    {JSON.stringify(detail.raw_data, null, 2)}
                  </pre>
                </TabsContent>
              </Tabs>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
