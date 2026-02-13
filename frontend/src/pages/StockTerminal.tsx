import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, BarChart3, Bot, Play } from "lucide-react";

import { api, type StockAnalysisRun, type WatchlistItem } from "@/api/client";
import { CandlestickChart } from "@/components/charts/CandlestickChart";
import { TradeCurveChart } from "@/components/charts/TradeCurveChart";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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

const ALLOWED_TIMEFRAMES = ["1d", "5m", "1m"] as const;

function parseTimeframes(input: string): string[] {
  const tokens = input
    .split(",")
    .map((item) => item.trim().toLowerCase())
    .filter((item) => ALLOWED_TIMEFRAMES.includes(item as (typeof ALLOWED_TIMEFRAMES)[number]));
  return Array.from(new Set(tokens));
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" ? (value as Record<string, unknown>) : {};
}

function formatLevels(raw: unknown): string {
  if (!Array.isArray(raw) || raw.length === 0) return "N/A";
  return raw
    .slice(0, 3)
    .map((item) => {
      const row = asRecord(item);
      const label = row.level ?? "-";
      const price = row.price ?? "-";
      const touches = row.touches ?? "-";
      return `${label}:${price}(touches=${touches})`;
    })
    .join("; ");
}

function formatPatterns(raw: unknown): string {
  if (!Array.isArray(raw) || raw.length === 0) return "N/A";
  return raw
    .slice(0, 3)
    .map((item) => {
      const row = asRecord(item);
      return `${String(row.type ?? "pattern")}:${String(row.direction ?? "neutral")}`;
    })
    .join("; ");
}

type TechnicalPrimaryView = {
  trend: Record<string, unknown>;
  momentum: Record<string, unknown>;
  volume: Record<string, unknown>;
  patterns: Record<string, unknown>;
  sr: Record<string, unknown>;
  strategy: Record<string, unknown>;
  asOf: string;
};

export function StockTerminalPage({ defaultProvider, defaultModel, intervals, watchlistItems }: Props) {
  const notifier = useNotifier();
  const [selectedWatchlistId, setSelectedWatchlistId] = useState("");
  const [interval, setInterval] = useState("1m");
  const [analysis, setAnalysis] = useState<StockAnalysisRun | null>(null);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const [analysisError, setAnalysisError] = useState("");
  const [question, setQuestion] = useState("");
  const [peerListText, setPeerListText] = useState("");
  const [timeframesText, setTimeframesText] = useState("1d,5m");
  const [indicatorProfile, setIndicatorProfile] = useState<"balanced" | "trend" | "momentum">("balanced");

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

  const technicalAnalysis = useMemo(() => {
    if (!analysis) return null;
    const raw = asRecord(analysis.output?.raw);
    const technical = raw.technical_analysis;
    if (!technical || typeof technical !== "object") {
      return null;
    }
    return technical as Record<string, unknown>;
  }, [analysis]);

  const technicalPrimary = useMemo<TechnicalPrimaryView>(() => {
    if (!technicalAnalysis) {
      return {
        trend: {},
        momentum: {},
        volume: {},
        patterns: {},
        sr: {},
        strategy: {},
        asOf: "N/A",
      };
    }
    return {
      trend: asRecord(asRecord(technicalAnalysis.trend).primary),
      momentum: asRecord(asRecord(technicalAnalysis.momentum).primary),
      volume: asRecord(asRecord(technicalAnalysis.volume_price).primary),
      patterns: asRecord(asRecord(technicalAnalysis.patterns).primary),
      sr: asRecord(asRecord(technicalAnalysis.support_resistance).primary),
      strategy: asRecord(technicalAnalysis.strategy),
      asOf: String(technicalAnalysis.as_of ?? "N/A"),
    };
  }, [technicalAnalysis]);

  const runAnalysis = async () => {
    if (!canQueryMarketData) {
      const message = "请先从 Watchlist 下拉中选择股票。";
      setAnalysisError(message);
      notifier.warning("无法执行分析", message, { dedupeKey: "analysis-invalid-symbol" });
      return;
    }
    setLoadingAnalysis(true);
    try {
      const parsedTimeframes = parseTimeframes(timeframesText);
      notifier.info("分析任务已提交", `${normalizedSymbol} (${market})`);
      const task = await api.runStockAnalysisAsync(normalizedSymbol, {
        market,
        provider_id: defaultProvider,
        model: defaultModel,
        interval,
        lookback_bars: 120,
        question: question.trim() || undefined,
        peer_list: peerListText
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        timeframes: parsedTimeframes.length ? parsedTimeframes : ["1d", "5m"],
        indicator_profile: indicatorProfile,
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
          <div className="mb-3 grid gap-3 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="analysis_question">分析问题（可选）</Label>
              <Input
                id="analysis_question"
                placeholder="例如：未来12个月风险收益如何？"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="analysis_peers">同业列表（可选，逗号分隔）</Label>
              <Input
                id="analysis_peers"
                placeholder="MSFT,GOOGL,AMZN"
                value={peerListText}
                onChange={(event) => setPeerListText(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="analysis_timeframes">分析周期（逗号分隔）</Label>
              <Input
                id="analysis_timeframes"
                placeholder="1d,5m"
                value={timeframesText}
                onChange={(event) => setTimeframesText(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="analysis_profile">指标画像</Label>
              <Select
                value={indicatorProfile}
                onValueChange={(value: "balanced" | "trend" | "momentum") => setIndicatorProfile(value)}
              >
                <SelectTrigger id="analysis_profile">
                  <SelectValue placeholder="选择画像" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="balanced">balanced</SelectItem>
                  <SelectItem value="trend">trend</SelectItem>
                  <SelectItem value="momentum">momentum</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <Button onClick={() => void runAnalysis()} disabled={loadingAnalysis}>
            <Play className="mr-2 h-4 w-4" />
            {loadingAnalysis ? "分析中..." : "一键分析"}
          </Button>
          {analysisError ? <div className="mt-3 text-sm text-destructive">{analysisError}</div> : null}

          {analysis && technicalAnalysis ? (
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">趋势指标</CardTitle>
                </CardHeader>
                <CardContent className="space-y-1 text-xs text-muted-foreground">
                  <div>数据时间: {technicalPrimary.asOf}</div>
                  <div>MA 排列: {String(asRecord(technicalPrimary.trend.ma).state ?? "N/A")}</div>
                  <div>MACD: {String(asRecord(technicalPrimary.trend.macd).cross ?? "N/A")}</div>
                  <div>布林: {String(asRecord(technicalPrimary.trend.bollinger).status ?? "N/A")}</div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">动量指标</CardTitle>
                </CardHeader>
                <CardContent className="space-y-1 text-xs text-muted-foreground">
                  <div>RSI: {String(asRecord(technicalPrimary.momentum.rsi).value ?? "N/A")}</div>
                  <div>RSI 状态: {String(asRecord(technicalPrimary.momentum.rsi).status ?? "N/A")}</div>
                  <div>KDJ: {String(asRecord(technicalPrimary.momentum.kdj).status ?? "N/A")}</div>
                  <div>背离: {String(asRecord(technicalPrimary.momentum.divergence).type ?? "N/A")}</div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">量价分析</CardTitle>
                </CardHeader>
                <CardContent className="space-y-1 text-xs text-muted-foreground">
                  <div>量比: {String(technicalPrimary.volume.volume_ratio ?? "N/A")}</div>
                  <div>缩量回调: {String(technicalPrimary.volume.shrink_pullback ?? "N/A")}</div>
                  <div>放量突破: {String(technicalPrimary.volume.volume_breakout ?? "N/A")}</div>
                  <div>ATR14: {String(technicalPrimary.volume.atr_14 ?? "N/A")}</div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">形态识别</CardTitle>
                </CardHeader>
                <CardContent className="space-y-1 text-xs text-muted-foreground">
                  <div>最近形态: {formatPatterns(technicalPrimary.patterns.recent)}</div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">支撑压力</CardTitle>
                </CardHeader>
                <CardContent className="space-y-1 text-xs text-muted-foreground">
                  <div>支撑: {formatLevels(technicalPrimary.sr.supports)}</div>
                  <div>压力: {formatLevels(technicalPrimary.sr.resistances)}</div>
                </CardContent>
              </Card>
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">策略级输出</CardTitle>
                </CardHeader>
                <CardContent className="space-y-1 text-xs text-muted-foreground">
                  <div>Score: {String(technicalPrimary.strategy.score ?? "N/A")}</div>
                  <div>方向: {String(technicalPrimary.strategy.stance ?? "N/A")}</div>
                  <div>建议仓位: {String(technicalPrimary.strategy.position_size ?? "N/A")}%</div>
                  <div>入场区间: {JSON.stringify(technicalPrimary.strategy.entry_zone ?? {})}</div>
                  <div>止损: {String(technicalPrimary.strategy.stop_loss ?? "N/A")}</div>
                  <div>止盈: {String(technicalPrimary.strategy.take_profit ?? "N/A")}</div>
                </CardContent>
              </Card>
            </div>
          ) : null}

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
