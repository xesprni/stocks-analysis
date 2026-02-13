import { Bell, CheckCheck, Play, RefreshCw } from "lucide-react";

import type { NewsAlert, NewsListenerRun } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

type Props = {
  alerts: NewsAlert[];
  runs: NewsListenerRun[];
  status: string;
  setStatus: (value: string) => void;
  market: string;
  setMarket: (value: string) => void;
  symbol: string;
  setSymbol: (value: string) => void;
  onRunNow: () => Promise<void>;
  onMarkAllRead: () => Promise<void>;
  onMarkAlert: (id: number, status: "READ" | "DISMISSED") => Promise<void>;
  onRefresh: () => Promise<void>;
};

export function AlertCenterPage({
  alerts,
  runs,
  status,
  setStatus,
  market,
  setMarket,
  symbol,
  setSymbol,
  onRunNow,
  onMarkAllRead,
  onMarkAlert,
  onRefresh,
}: Props) {
  const unreadCount = alerts.filter((a) => a.status === "UNREAD").length;

  return (
    <div className="space-y-6">
      {/* Hero header */}
      <section className="relative overflow-hidden rounded-3xl border border-rose-300/50 bg-gradient-to-br from-rose-500/15 via-red-500/10 to-orange-400/15 p-6">
        <div className="pointer-events-none absolute -left-12 -top-14 h-44 w-44 rounded-full bg-rose-400/20 blur-3xl" />
        <div className="pointer-events-none absolute right-0 top-10 h-32 w-32 rounded-full bg-red-400/20 blur-2xl" />
        <div className="pointer-events-none absolute -bottom-12 right-10 h-44 w-44 rounded-full bg-orange-400/20 blur-3xl" />
        <div className="relative flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
              <Bell className="h-5 w-5 text-rose-600" />
              告警中心
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              实时监控异动告警，当前 {alerts.length} 条告警{unreadCount > 0 ? `，${unreadCount} 条未读` : ""}。
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" onClick={() => void onRefresh()}>
              <RefreshCw className="mr-2 h-4 w-4" />
              刷新
            </Button>
            <Button
              className="bg-gradient-to-r from-rose-600 to-red-600 text-white hover:from-rose-700 hover:to-red-700"
              onClick={() => void onRunNow()}
            >
              <Play className="mr-2 h-4 w-4" />
              立即执行监听
            </Button>
          </div>
        </div>
      </section>

      {/* Filters */}
      <Card className="border-rose-200/60 bg-gradient-to-br from-white to-rose-50/40 dark:from-slate-900 dark:to-rose-950/20">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">筛选条件</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-5">
          <div className="space-y-2">
            <Label>状态</Label>
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger>
                <SelectValue placeholder="状态" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="UNREAD">UNREAD</SelectItem>
                <SelectItem value="READ">READ</SelectItem>
                <SelectItem value="DISMISSED">DISMISSED</SelectItem>
                <SelectItem value="ALL">ALL</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>市场</Label>
            <Select value={market} onValueChange={setMarket}>
              <SelectTrigger>
                <SelectValue placeholder="市场" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ALL">ALL</SelectItem>
                <SelectItem value="CN">CN</SelectItem>
                <SelectItem value="HK">HK</SelectItem>
                <SelectItem value="US">US</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2 md:col-span-2">
            <Label>Symbol</Label>
            <Input value={symbol} onChange={(e) => setSymbol(e.target.value.toUpperCase())} placeholder="AAPL" />
          </div>
          <div className="flex items-end">
            <Button variant="secondary" className="w-full" onClick={() => void onMarkAllRead()}>
              <CheckCheck className="mr-2 h-4 w-4" />
              全部已读
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-5">
        {/* Alerts table */}
        <Card className="border-red-200/60 bg-gradient-to-br from-white to-red-50/40 dark:from-slate-900 dark:to-red-950/20 lg:col-span-3">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Bell className="h-4 w-4 text-red-600" />
              告警列表
              <Badge variant="outline" className="ml-1 text-xs">
                {alerts.length} 条
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto rounded-lg border border-red-200/40 dark:border-red-800/30">
              <Table>
                <TableHeader>
                  <TableRow className="bg-red-50/50 dark:bg-red-950/20">
                    <TableHead>时间</TableHead>
                    <TableHead>Symbol</TableHead>
                    <TableHead>异动</TableHead>
                    <TableHead>状态</TableHead>
                    <TableHead>操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {alerts.map((alert) => (
                    <TableRow key={alert.id} className="hover:bg-red-50/30 dark:hover:bg-red-950/10">
                      <TableCell className="whitespace-nowrap text-xs">{new Date(alert.created_at).toLocaleString()}</TableCell>
                      <TableCell className="font-medium">
                        {alert.symbol}
                        <Badge variant="outline" className="ml-1 text-[10px]">{alert.market}</Badge>
                      </TableCell>
                      <TableCell>
                        <div className="space-y-1">
                          <Badge variant={alert.severity === "HIGH" ? "destructive" : "secondary"}>
                            {alert.severity}
                          </Badge>
                          <div className="text-xs text-muted-foreground">
                            {alert.move_window_minutes}m {alert.price_change_percent.toFixed(2)}%
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant={alert.status === "UNREAD" ? "default" : "outline"}>
                          {alert.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="space-x-2">
                        <Button size="sm" variant="outline" onClick={() => void onMarkAlert(alert.id, "READ")}>
                          已读
                        </Button>
                        <Button size="sm" variant="destructive" onClick={() => void onMarkAlert(alert.id, "DISMISSED")}>
                          忽略
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                  {!alerts.length && (
                    <TableRow>
                      <TableCell colSpan={5} className="py-8 text-center text-sm text-muted-foreground">
                        暂无告警记录
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>

        {/* Run history */}
        <Card className="border-orange-200/60 bg-gradient-to-br from-white to-orange-50/40 dark:from-slate-900 dark:to-orange-950/20 lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Play className="h-4 w-4 text-orange-600" />
              监听运行历史
              <Badge variant="outline" className="ml-1 text-xs">
                {runs.length} 次
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto rounded-lg border border-orange-200/40 dark:border-orange-800/30">
              <Table>
                <TableHeader>
                  <TableRow className="bg-orange-50/50 dark:bg-orange-950/20">
                    <TableHead>ID</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Alerts</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {runs.map((run) => (
                    <TableRow key={run.id} className="hover:bg-orange-50/30 dark:hover:bg-orange-950/10">
                      <TableCell className="font-mono text-xs">{run.id}</TableCell>
                      <TableCell>
                        <Badge variant={run.status === "SUCCEEDED" ? "secondary" : run.status === "FAILED" ? "destructive" : "outline"}>
                          {run.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-medium">{run.alerts_count}</TableCell>
                    </TableRow>
                  ))}
                  {!runs.length && (
                    <TableRow>
                      <TableCell colSpan={3} className="py-8 text-center text-sm text-muted-foreground">
                        暂无运行记录
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
