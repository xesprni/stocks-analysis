import { useState } from "react";
import { Eye, Plus, RefreshCw, Search, Trash2 } from "lucide-react";

import type { StockSearchResult, WatchlistItem } from "@/api/client";
import { SymbolSearchDialog } from "@/components/SymbolSearchDialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

type Props = {
  items: Array<WatchlistItem & { keywords?: string[] }>;
  markets: string[];
  refreshing?: boolean;
  onRefresh?: () => void;
  onSearch: (query: string, market: string) => Promise<StockSearchResult[]>;
  onAdd: (payload: {
    symbol: string;
    market: string;
    alias?: string;
    display_name?: string;
    keywords?: string[];
  }) => Promise<void>;
  onDelete: (id: number) => Promise<void>;
};

export function WatchlistPage({ items, markets, refreshing, onRefresh, onSearch, onAdd, onDelete }: Props) {
  const [symbol, setSymbol] = useState("AAPL");
  const [market, setMarket] = useState("US");
  const [alias, setAlias] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [keywordsText, setKeywordsText] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);

  return (
    <div className="space-y-6">
      {/* Hero header */}
      <section className="relative overflow-hidden rounded-3xl border border-violet-300/50 bg-gradient-to-br from-violet-500/15 via-fuchsia-500/10 to-pink-400/15 p-6">
        <div className="pointer-events-none absolute -left-12 -top-14 h-44 w-44 rounded-full bg-violet-400/20 blur-3xl" />
        <div className="pointer-events-none absolute right-0 top-10 h-32 w-32 rounded-full bg-fuchsia-400/20 blur-2xl" />
        <div className="pointer-events-none absolute -bottom-12 right-10 h-44 w-44 rounded-full bg-pink-400/20 blur-3xl" />
        <div className="relative flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
              <Eye className="h-5 w-5 text-violet-600" />
              Watchlist 监控列表
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              管理您的股票监控列表，添加或删除跟踪标的。当前共 {items.length} 个标的。
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

      <SymbolSearchDialog
        open={searchOpen}
        markets={markets}
        onOpenChange={setSearchOpen}
        onSearch={onSearch}
        title="添加到 Watchlist"
        onSelect={(item: StockSearchResult) => {
          setSymbol(item.symbol);
          setMarket(item.market);
          setDisplayName(item.name);
        }}
      />

      <div className="grid gap-6 lg:grid-cols-5">
        {/* Add form */}
        <Card className="border-violet-200/60 bg-gradient-to-br from-white to-violet-50/40 dark:from-slate-900 dark:to-violet-950/20 lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Plus className="h-4 w-4 text-violet-600" />
              新增监控标的
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
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
              <Label htmlFor="alias">Alias</Label>
              <Input id="alias" value={alias} onChange={(e) => setAlias(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="display_name">Display Name</Label>
              <Input id="display_name" value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="keywords">Keywords (逗号分隔)</Label>
              <Input
                id="keywords"
                value={keywordsText}
                onChange={(e) => setKeywordsText(e.target.value)}
                placeholder="苹果, iPhone, Apple"
              />
            </div>
            <Button
              className="w-full bg-gradient-to-r from-violet-600 to-fuchsia-600 text-white hover:from-violet-700 hover:to-fuchsia-700"
              onClick={async () => {
                const keywords = keywordsText
                  .split(",")
                  .map((entry) => entry.trim())
                  .filter(Boolean);
                await onAdd({
                  symbol,
                  market,
                  alias: alias || undefined,
                  display_name: displayName || undefined,
                  keywords: keywords.length ? keywords : undefined,
                });
                setAlias("");
                setDisplayName("");
                setKeywordsText("");
              }}
            >
              <Plus className="mr-2 h-4 w-4" />
              添加到 Watchlist
            </Button>
          </CardContent>
        </Card>

        {/* Watchlist table */}
        <Card className="border-fuchsia-200/60 bg-gradient-to-br from-white to-fuchsia-50/40 dark:from-slate-900 dark:to-fuchsia-950/20 lg:col-span-3">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Eye className="h-4 w-4 text-fuchsia-600" />
              Watchlist
              <Badge variant="outline" className="ml-1 text-xs">
                {items.length} 项
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto rounded-lg border border-fuchsia-200/40 dark:border-fuchsia-800/30">
              <Table>
                <TableHeader>
                  <TableRow className="bg-fuchsia-50/50 dark:bg-fuchsia-950/20">
                    <TableHead>ID</TableHead>
                    <TableHead>Symbol</TableHead>
                    <TableHead>Market</TableHead>
                    <TableHead>Alias</TableHead>
                    <TableHead>Display</TableHead>
                    <TableHead>Keywords</TableHead>
                    <TableHead>Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((item) => (
                    <TableRow key={item.id} className="hover:bg-fuchsia-50/30 dark:hover:bg-fuchsia-950/10">
                      <TableCell className="font-mono text-xs">{item.id}</TableCell>
                      <TableCell className="font-medium">{item.symbol}</TableCell>
                      <TableCell>
                        <Badge variant="outline">{item.market}</Badge>
                      </TableCell>
                      <TableCell>{item.alias ?? "-"}</TableCell>
                      <TableCell>{item.display_name ?? "-"}</TableCell>
                      <TableCell className="max-w-[200px] truncate text-xs text-muted-foreground">
                        {item.keywords?.join(", ") || "-"}
                      </TableCell>
                      <TableCell>
                        <Button variant="destructive" size="sm" onClick={() => void onDelete(item.id)}>
                          <Trash2 className="mr-1 h-3 w-3" />
                          删除
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                  {!items.length && (
                    <TableRow>
                      <TableCell colSpan={7} className="py-8 text-center text-sm text-muted-foreground">
                        暂无监控标的，请添加。
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
