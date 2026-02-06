import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, BarChart3, Bot, Play, Search } from "lucide-react";

import { api, type StockAnalysisRun, type StockSearchResult } from "@/api/client";
import { SymbolSearchDialog } from "@/components/SymbolSearchDialog";
import { CandlestickChart } from "@/components/charts/CandlestickChart";
import { TradeCurveChart } from "@/components/charts/TradeCurveChart";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

type Props = {
  defaultProvider: string;
  defaultModel: string;
  markets: string[];
  intervals: string[];
  onSearch: (query: string, market: string) => Promise<StockSearchResult[]>;
};

export function StockTerminalPage({ defaultProvider, defaultModel, markets, intervals, onSearch }: Props) {
  const [symbol, setSymbol] = useState("AAPL");
  const [market, setMarket] = useState("US");
  const [interval, setInterval] = useState("1m");
  const [analysis, setAnalysis] = useState<StockAnalysisRun | null>(null);
  const [loadingAnalysis, setLoadingAnalysis] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);

  const quoteQuery = useQuery({
    queryKey: ["quote", symbol, market],
    queryFn: () => api.getQuote(symbol, market),
    refetchInterval: 5000,
  });

  const klineQuery = useQuery({
    queryKey: ["kline", symbol, market, interval],
    queryFn: () => api.getKline(symbol, market, interval, 300),
    refetchInterval: 10000,
  });

  const curveQuery = useQuery({
    queryKey: ["curve", symbol, market],
    queryFn: () => api.getCurve(symbol, market, "1d"),
    refetchInterval: 5000,
  });

  const quoteText = useMemo(() => {
    const quote = quoteQuery.data;
    if (!quote) return "--";
    const pct = quote.change_percent != null ? `${quote.change_percent.toFixed(2)}%` : "--";
    return `${quote.price.toFixed(2)} (${pct})`;
  }, [quoteQuery.data]);

  const runAnalysis = async () => {
    setLoadingAnalysis(true);
    try {
      const result = await api.runStockAnalysis(symbol, {
        market,
        provider_id: defaultProvider,
        model: defaultModel,
        interval,
        lookback_bars: 120,
      });
      setAnalysis(result);
    } finally {
      setLoadingAnalysis(false);
    }
  };

  return (
    <div className="space-y-6">
      <SymbolSearchDialog
        open={searchOpen}
        markets={markets}
        onOpenChange={setSearchOpen}
        onSearch={onSearch}
        title="选择股票"
        onSelect={(item: StockSearchResult) => {
          setSymbol(item.symbol);
          setMarket(item.market);
        }}
      />

      <Card>
        <CardHeader>
          <CardTitle>Stock Terminal</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-4">
          <div className="space-y-2">
            <Label htmlFor="symbol">Symbol</Label>
            <Input
              id="symbol"
              value={symbol}
              onChange={(e) => {
                const next = e.target.value.toUpperCase();
                setSymbol(next);
              }}
            />
            <Button variant="outline" size="sm" className="mt-2" onClick={() => setSearchOpen(true)}>
              <Search className="mr-2 h-4 w-4" />
              添加Symbol
            </Button>
          </div>
          <div className="space-y-2">
            <Label htmlFor="market">Market</Label>
            <Select
              value={market}
              onValueChange={(value: string) => setMarket(value)}
            >
              <SelectTrigger id="market">
                <SelectValue placeholder="Market" />
              </SelectTrigger>
              <SelectContent>
                {markets
                  .filter((entry) => entry !== "ALL")
                  .map((entry) => (
                    <SelectItem key={entry} value={entry}>
                      {entry}
                    </SelectItem>
                  ))}
              </SelectContent>
            </Select>
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
            <div className="rounded-md border bg-white px-3 py-2 text-sm">{quoteText}</div>
          </div>
        </CardContent>
      </Card>

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
