import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, BarChart3, Bot, Play } from "lucide-react";

import { api, type StockAnalysisRun, type WatchlistItem } from "@/api/client";
import { CandlestickChart } from "@/components/charts/CandlestickChart";
import { TradeCurveChart } from "@/components/charts/TradeCurveChart";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { useNotifier } from "@/components/ui/notifier";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

type Props = {
  defaultProvider: string;
  defaultModel: string;
  intervals: string[];
  watchlistItems: WatchlistItem[];
};

export function StockTerminalPage({ defaultProvider, defaultModel, intervals, watchlistItems }: Props) {
  const notifier = useNotifier();
  const [selectedWatchlistId, setSelectedWatchlistId] = useState("");
  const [interval, setInterval] = useState("1m");
  const [analysis, setAnalysis] = useState<StockAnalysisRun | null>(null);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const [analysisError, setAnalysisError] = useState("");

  const watchlistOptions = useMemo(
    () =>
      watchlistItems
        .filter((item) => item.enabled)
        .map((item) => ({
          id: String(item.id),
          symbol: item.symbol.trim().toUpperCase(),
          market: item.market.trim().toUpperCase(),
          label: (item.display_name || item.alias || item.symbol).trim(),
        })),
    [watchlistItems]
  );

  useEffect(() => {
    if (!watchlistOptions.length) {
      setSelectedWatchlistId("");
      return;
    }
    const exists = watchlistOptions.some((item) => item.id === selectedWatchlistId);
    if (!exists) {
      setSelectedWatchlistId(watchlistOptions[0].id);
    }
  }, [watchlistOptions, selectedWatchlistId]);

  const selectedWatchItem = useMemo(
    () => watchlistOptions.find((item) => item.id === selectedWatchlistId) ?? null,
    [watchlistOptions, selectedWatchlistId]
  );
  const normalizedSymbol = selectedWatchItem?.symbol ?? "";
  const market = selectedWatchItem?.market ?? "US";
  const canQueryMarketData = Boolean(selectedWatchItem);

  const quoteQuery = useQuery({
    queryKey: ["quote", normalizedSymbol, market],
    queryFn: () => api.getQuote(normalizedSymbol, market),
    enabled: canQueryMarketData,
    retry: false,
    refetchInterval: 5000,
  });

  const klineQuery = useQuery({
    queryKey: ["kline", normalizedSymbol, market, interval],
    queryFn: () => api.getKline(normalizedSymbol, market, interval, 300),
    enabled: canQueryMarketData,
    retry: false,
    refetchInterval: 10000,
  });

  const curveQuery = useQuery({
    queryKey: ["curve", normalizedSymbol, market],
    queryFn: () => api.getCurve(normalizedSymbol, market, "1d"),
    enabled: canQueryMarketData,
    retry: false,
    refetchInterval: 5000,
  });

  const quoteText = useMemo(() => {
    if (!canQueryMarketData) return "请先选择有效 Symbol";
    const quote = quoteQuery.data;
    if (!quote) return "--";
    if (quote.source === "unavailable") return "暂无可用行情";
    const pct = quote.change_percent != null ? `${quote.change_percent.toFixed(2)}%` : "--";
    return `${quote.price.toFixed(2)} (${pct})`;
  }, [quoteQuery.data, canQueryMarketData]);

  const runAnalysis = async () => {
    if (!canQueryMarketData) {
      const message = "请先从 Watchlist 下拉中选择股票。";
      setAnalysisError(message);
      notifier.warning("无法执行分析", message, { dedupeKey: "analysis-invalid-symbol" });
      return;
    }
    setLoadingAnalysis(true);
    try {
      notifier.info("分析任务已提交", `${normalizedSymbol} (${market})`);
      const task = await api.runStockAnalysisAsync(normalizedSymbol, {
        market,
        provider_id: defaultProvider,
        model: defaultModel,
        interval,
        lookback_bars: 120,
      });

      const deadline = Date.now() + 15 * 60 * 1000;
      while (Date.now() < deadline) {
        const snapshot = await api.getStockAnalysisTask(task.task_id);
        if (snapshot.status === "SUCCEEDED") {
          if (!snapshot.result) {
            throw new Error("分析任务已完成，但结果为空。");
          }
          setAnalysis(snapshot.result);
          setAnalysisError("");
          notifier.success("分析已完成", `${normalizedSymbol} (${market})`);
          return;
        }
        if (snapshot.status === "FAILED") {
          throw new Error(snapshot.error_message || "分析任务失败。");
        }
        await new Promise<void>((resolve) => window.setTimeout(resolve, 2000));
      }
      throw new Error("分析任务执行超时，请稍后重试。");
    } catch (error) {
      const message = (error as Error).message;
      setAnalysisError(message);
      notifier.error("分析执行失败", message);
    } finally {
      setLoadingAnalysis(false);
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Stock Terminal</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-4">
          <div className="space-y-2">
            <Label htmlFor="watchlist_symbol">Watchlist Symbol</Label>
            <Select value={selectedWatchlistId} onValueChange={(value: string) => setSelectedWatchlistId(value)}>
              <SelectTrigger id="watchlist_symbol">
                <SelectValue placeholder="选择 Watchlist 股票" />
              </SelectTrigger>
              <SelectContent>
                {watchlistOptions.map((entry) => (
                  <SelectItem key={entry.id} value={entry.id}>
                    {entry.label} ({entry.symbol}/{entry.market})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="market">Market</Label>
            <div id="market" className="rounded-md border bg-card px-3 py-2 text-sm">
              {market || "--"}
            </div>
          </div>
          <div className="space-y-2">
            <Label htmlFor="interval">K线周期(1m/5m/1d)</Label>
            <Select value={interval} onValueChange={(value: string) => setInterval(value)}>
              <SelectTrigger id="interval">
                <SelectValue placeholder="周期" />
              </SelectTrigger>
              <SelectContent>
                {intervals.map((entry) => (
                  <SelectItem key={entry} value={entry}>
                    {entry}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>最新价</Label>
            <div className="rounded-md border bg-card px-3 py-2 text-sm">{quoteText}</div>
          </div>
        </CardContent>
      </Card>

      {!watchlistOptions.length ? (
        <Card>
          <CardContent className="py-6 text-sm text-muted-foreground">
            当前没有可用的 Watchlist 股票，请先在 Watchlist 页面添加并启用股票。
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BarChart3 className="h-4 w-4" />
              K线
            </CardTitle>
          </CardHeader>
          <CardContent>
            <CandlestickChart data={klineQuery.data ?? []} />
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-4 w-4" />
              实时交易曲线
            </CardTitle>
          </CardHeader>
          <CardContent>
            <TradeCurveChart data={curveQuery.data ?? []} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Bot className="h-4 w-4" />
            模型分析
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Button onClick={() => void runAnalysis()} disabled={loadingAnalysis}>
            <Play className="mr-2 h-4 w-4" />
            {loadingAnalysis ? "分析中..." : "一键分析"}
          </Button>
          {analysisError ? <div className="mt-3 text-sm text-destructive">{analysisError}</div> : null}

          {analysis ? (
            <Tabs defaultValue="markdown" className="mt-4">
              <TabsList>
                <TabsTrigger value="markdown">Markdown</TabsTrigger>
                <TabsTrigger value="json">JSON</TabsTrigger>
              </TabsList>
              <TabsContent value="markdown">
                <pre>{analysis.markdown}</pre>
              </TabsContent>
              <TabsContent value="json">
                <pre>{JSON.stringify(analysis.output, null, 2)}</pre>
              </TabsContent>
            </Tabs>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
