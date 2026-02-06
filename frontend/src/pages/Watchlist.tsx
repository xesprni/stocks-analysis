import { useState } from "react";
import { Plus, Search, Trash2 } from "lucide-react";

import type { StockSearchResult, WatchlistItem } from "@/api/client";
import { SymbolSearchDialog } from "@/components/SymbolSearchDialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

type Props = {
  items: Array<WatchlistItem & { keywords?: string[] }>;
  markets: string[];
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

export function WatchlistPage({ items, markets, onSearch, onAdd, onDelete }: Props) {
  const [symbol, setSymbol] = useState("AAPL");
  const [market, setMarket] = useState("US");
  const [alias, setAlias] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [keywordsText, setKeywordsText] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);

  return (
    <div className="grid gap-6 lg:grid-cols-5">
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

      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle>新增监控标的</CardTitle>
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
            className="w-full"
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

      <Card className="lg:col-span-3">
        <CardHeader>
          <CardTitle>Watchlist</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
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
                <TableRow key={item.id}>
                  <TableCell>{item.id}</TableCell>
                  <TableCell>{item.symbol}</TableCell>
                  <TableCell>{item.market}</TableCell>
                  <TableCell>{item.alias ?? "-"}</TableCell>
                  <TableCell>{item.display_name ?? "-"}</TableCell>
                  <TableCell>{item.keywords?.join(", ") || "-"}</TableCell>
                  <TableCell>
                    <Button variant="destructive" size="sm" onClick={() => void onDelete(item.id)}>
                      <Trash2 className="mr-1 h-3 w-3" />
                      删除
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
