import { useEffect, useMemo, useState } from "react";
import { Search, X } from "lucide-react";

import type { StockSearchResult } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

type Props = {
  open: boolean;
  markets: string[];
  onOpenChange: (open: boolean) => void;
  onSearch: (query: string, market: string) => Promise<StockSearchResult[]>;
  onSelect: (item: StockSearchResult) => void;
  title?: string;
};

export function SymbolSearchDialog({
  open,
  markets,
  onOpenChange,
  onSearch,
  onSelect,
  title = "搜索股票",
}: Props) {
  const [query, setQuery] = useState("");
  const [market, setMarket] = useState("ALL");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<StockSearchResult[]>([]);
  const [error, setError] = useState("");

  const supportedMarkets = useMemo(() => {
    const base = ["ALL", ...markets.filter((entry) => entry !== "ALL")];
    return Array.from(new Set(base));
  }, [markets]);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setResults([]);
      setError("");
      setLoading(false);
      return;
    }
    const q = query.trim();
    if (q.length < 2) {
      setResults([]);
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(async () => {
      setLoading(true);
      try {
        const rows = await onSearch(q, market);
        if (!cancelled) {
          setResults(rows);
          setError("");
        }
      } catch (exc) {
        if (!cancelled) {
          setResults([]);
          setError((exc as Error).message);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }, 280);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [open, query, market, onSearch]);

  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-4 backdrop-blur-[1px]">
      <Card className="w-full max-w-2xl">
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle className="text-lg">{title}</CardTitle>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            <X className="h-4 w-4" />
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-[1fr_180px]">
            <div className="space-y-2">
              <Label htmlFor="symbol-search-query">关键词</Label>
              <Input
                id="symbol-search-query"
                autoFocus
                placeholder="输入 symbol 或公司名称，如 AAPL / Apple"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="symbol-search-market">市场</Label>
              <Select value={market} onValueChange={(value: string) => setMarket(value)}>
                <SelectTrigger id="symbol-search-market">
                  <SelectValue placeholder="市场" />
                </SelectTrigger>
                <SelectContent>
                  {supportedMarkets.map((entry) => (
                    <SelectItem key={entry} value={entry}>
                      {entry}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="rounded-xl border border-border/80 bg-white">
            <div className="border-b border-border/70 px-4 py-2 text-xs text-muted-foreground">搜索结果</div>
            <div className="max-h-72 overflow-y-auto p-2">
              {query.trim().length < 2 ? (
                <div className="px-2 py-6 text-center text-sm text-muted-foreground">至少输入 2 个字符开始搜索</div>
              ) : loading ? (
                <div className="px-2 py-6 text-center text-sm text-muted-foreground">联网搜索中...</div>
              ) : error ? (
                <div className="px-2 py-6 text-center text-sm text-destructive">{error}</div>
              ) : results.length === 0 ? (
                <div className="px-2 py-6 text-center text-sm text-muted-foreground">未找到结果</div>
              ) : (
                <div className="space-y-1">
                  {results.map((item) => (
                    <button
                      key={`${item.market}:${item.symbol}:${item.source}`}
                      type="button"
                      className="flex w-full items-center justify-between rounded-lg border border-transparent px-3 py-2 text-left transition-colors hover:border-border hover:bg-muted/55"
                      onClick={() => {
                        onSelect(item);
                        onOpenChange(false);
                      }}
                    >
                      <div>
                        <div className="text-sm font-medium">
                          {item.symbol} ({item.market})
                        </div>
                        <div className="text-xs text-muted-foreground">{item.name}</div>
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {item.exchange || item.source}
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="flex justify-end">
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              <Search className="mr-2 h-4 w-4" />
              完成
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
