import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, BarChart3, RefreshCw } from "lucide-react";

import { api, type WatchlistItem } from "@/api/client";
import {
  CandlestickChart,
  type IndicatorVisibility,
} from "@/components/charts/CandlestickChart";
import { TradeCurveChart } from "@/components/charts/TradeCurveChart";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

type Props = {
  intervals: string[];
  watchlistItems: WatchlistItem[];
};

export function StockTerminalPage({ intervals, watchlistItems }: Props) {
  const [selectedWatchlistId, setSelectedWatchlistId] = useState("");
  const [interval, setInterval] = useState("1m");
  const [indicatorVisibility, setIndicatorVisibility] = useState<IndicatorVisibility>({
    sma5: true,
    sma10: true,
    sma20: false,
    ema12: false,
    ema26: false,
    boll: false,
    bbiboll: false,
    rsi: true,
    macd: true,
    kdj: false,
    wr: false,
    cci: false,
    atr: false,
  });

  const toggleIndicator = (key: keyof IndicatorVisibility) => {
    setIndicatorVisibility((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

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

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Stock Terminal</CardTitle>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                void quoteQuery.refetch();
                void klineQuery.refetch();
                void curveQuery.refetch();
              }}
              disabled={quoteQuery.isFetching || klineQuery.isFetching || curveQuery.isFetching}
            >
              <RefreshCw className={`mr-2 h-4 w-4 ${quoteQuery.isFetching || klineQuery.isFetching || curveQuery.isFetching ? "animate-spin" : ""}`} />
              刷新数据
            </Button>
          </div>
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
          <CardContent className="space-y-3">
            <div className="flex flex-wrap gap-2">
              <Button
                variant={indicatorVisibility.sma5 ? "default" : "outline"}
                size="sm"
                onClick={() => toggleIndicator("sma5")}
              >
                SMA5
              </Button>
              <Button
                variant={indicatorVisibility.sma10 ? "default" : "outline"}
                size="sm"
                onClick={() => toggleIndicator("sma10")}
              >
                SMA10
              </Button>
              <Button
                variant={indicatorVisibility.sma20 ? "default" : "outline"}
                size="sm"
                onClick={() => toggleIndicator("sma20")}
              >
                SMA20
              </Button>
              <Button
                variant={indicatorVisibility.ema12 ? "default" : "outline"}
                size="sm"
                onClick={() => toggleIndicator("ema12")}
              >
                EMA12
              </Button>
              <Button
                variant={indicatorVisibility.ema26 ? "default" : "outline"}
                size="sm"
                onClick={() => toggleIndicator("ema26")}
              >
                EMA26
              </Button>
              <Button
                variant={indicatorVisibility.boll ? "default" : "outline"}
                size="sm"
                onClick={() => toggleIndicator("boll")}
              >
                BOLL
              </Button>
              <Button
                variant={indicatorVisibility.bbiboll ? "default" : "outline"}
                size="sm"
                onClick={() => toggleIndicator("bbiboll")}
              >
                BBIBOLL
              </Button>
              <Button
                variant={indicatorVisibility.rsi ? "default" : "outline"}
                size="sm"
                onClick={() => toggleIndicator("rsi")}
              >
                RSI
              </Button>
              <Button
                variant={indicatorVisibility.macd ? "default" : "outline"}
                size="sm"
                onClick={() => toggleIndicator("macd")}
              >
                MACD
              </Button>
              <Button
                variant={indicatorVisibility.kdj ? "default" : "outline"}
                size="sm"
                onClick={() => toggleIndicator("kdj")}
              >
                KDJ
              </Button>
              <Button
                variant={indicatorVisibility.wr ? "default" : "outline"}
                size="sm"
                onClick={() => toggleIndicator("wr")}
              >
                WR
              </Button>
              <Button
                variant={indicatorVisibility.cci ? "default" : "outline"}
                size="sm"
                onClick={() => toggleIndicator("cci")}
              >
                CCI
              </Button>
              <Button
                variant={indicatorVisibility.atr ? "default" : "outline"}
                size="sm"
                onClick={() => toggleIndicator("atr")}
              >
                ATR
              </Button>
            </div>
            <CandlestickChart
              data={klineQuery.data ?? []}
              indicators={indicatorVisibility}
            />
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
    </div>
  );
}
