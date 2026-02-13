import { useState } from "react";
import { Rocket, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

type Props = {
  onRunReport: (payload: {
    mode: "market" | "stock";
    symbol?: string;
    market?: string;
    question?: string;
    peer_list?: string[];
  }) => void;
  running: boolean;
};

export function ReportRunnerPage({ onRunReport, running }: Props) {
  const [reportMode, setReportMode] = useState<"market" | "stock">("market");
  const [reportSymbol, setReportSymbol] = useState("");
  const [reportMarket, setReportMarket] = useState("US");
  const [reportQuestion, setReportQuestion] = useState("");
  const [reportPeers, setReportPeers] = useState("");

  return (
    <div className="space-y-6">
      <section className="relative overflow-hidden rounded-3xl border border-sky-300/50 bg-gradient-to-br from-sky-500/15 via-cyan-400/10 to-emerald-400/15 p-6">
        <div className="pointer-events-none absolute -left-10 -top-16 h-40 w-40 rounded-full bg-sky-400/20 blur-3xl" />
        <div className="pointer-events-none absolute -right-8 -bottom-12 h-44 w-44 rounded-full bg-emerald-400/20 blur-3xl" />
        <div className="relative">
          <h2 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <Sparkles className="h-5 w-5 text-sky-600" />
            Report Runner
          </h2>
          <p className="mt-2 text-sm text-muted-foreground">集中执行市场模式与个股模式报告任务，结果在 Reports 页面查看。</p>
        </div>
      </section>

      <Card className="border-sky-200/60 bg-gradient-to-br from-white to-sky-50/40 dark:from-slate-900 dark:to-sky-950/20">
        <CardHeader>
          <CardTitle>生成报告</CardTitle>
          <CardDescription>支持市场模式与个股模式，个股模式可附加 peers 与问题。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="report_mode">报告模式</Label>
              <Select value={reportMode} onValueChange={(value: "market" | "stock") => setReportMode(value)}>
                <SelectTrigger id="report_mode">
                  <SelectValue placeholder="选择报告模式" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="market">market</SelectItem>
                  <SelectItem value="stock">stock</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="report_question">问题（可选）</Label>
              <Input id="report_question" value={reportQuestion} onChange={(event) => setReportQuestion(event.target.value)} />
            </div>
            {reportMode === "stock" ? (
              <>
                <div className="space-y-2">
                  <Label htmlFor="report_symbol">Symbol</Label>
                  <Input id="report_symbol" value={reportSymbol} onChange={(event) => setReportSymbol(event.target.value)} />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="report_market">Market</Label>
                  <Select value={reportMarket} onValueChange={(value: string) => setReportMarket(value)}>
                    <SelectTrigger id="report_market">
                      <SelectValue placeholder="选择市场" />
                    </SelectTrigger>
                    <SelectContent>
                      {["CN", "HK", "US"].map((entry) => (
                        <SelectItem key={entry} value={entry}>
                          {entry}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2 md:col-span-2">
                  <Label htmlFor="report_peers">Peers (comma separated)</Label>
                  <Input id="report_peers" value={reportPeers} onChange={(event) => setReportPeers(event.target.value)} />
                </div>
              </>
            ) : null}
          </div>

          <div className="flex justify-end">
            <Button
              size="lg"
              className="bg-gradient-to-r from-sky-600 to-emerald-600 text-white hover:from-sky-700 hover:to-emerald-700"
              onClick={() => {
                const peerList = reportPeers
                  .split(",")
                  .map((item) => item.trim())
                  .filter(Boolean);
                onRunReport({
                  mode: reportMode,
                  symbol: reportMode === "stock" ? reportSymbol.trim().toUpperCase() : undefined,
                  market: reportMode === "stock" ? reportMarket : undefined,
                  question: reportQuestion.trim() || undefined,
                  peer_list: peerList.length ? peerList : undefined,
                });
              }}
              disabled={running || (reportMode === "stock" && !reportSymbol.trim())}
            >
              <Rocket className="mr-2 h-4 w-4" />
              {running ? "执行中..." : "立即生成报告"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
