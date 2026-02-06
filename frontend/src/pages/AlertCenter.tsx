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
  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Bell className="h-4 w-4" />
            告警中心
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-6">
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
          <div className="flex items-end gap-2 md:col-span-2">
            <Button variant="outline" onClick={() => void onRefresh()}>
              <RefreshCw className="mr-2 h-4 w-4" />
              刷新
            </Button>
            <Button onClick={() => void onRunNow()}>
              <Play className="mr-2 h-4 w-4" />
              立即执行监听
            </Button>
            <Button variant="secondary" onClick={() => void onMarkAllRead()}>
              <CheckCheck className="mr-2 h-4 w-4" />
              全部已读
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>告警列表</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>时间</TableHead>
                  <TableHead>Symbol</TableHead>
                  <TableHead>异动</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {alerts.map((alert) => (
                  <TableRow key={alert.id}>
                    <TableCell className="text-xs">{new Date(alert.created_at).toLocaleString()}</TableCell>
                    <TableCell>
                      {alert.symbol} ({alert.market})
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
                    <TableCell>{alert.status}</TableCell>
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
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>监听运行历史</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Alerts</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.map((run) => (
                  <TableRow key={run.id}>
                    <TableCell>{run.id}</TableCell>
                    <TableCell>{run.status}</TableCell>
                    <TableCell>{run.alerts_count}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
