import { memo, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, BarChart3, Gauge, Globe2, RefreshCw, TrendingDown, TrendingUp } from "lucide-react";

import { api } from "@/api/client";
import type { DashboardIndexMetric, DashboardSnapshot } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useNotifier } from "@/components/ui/notifier";
import { WatchlistIntradayCards } from "@/components/dashboard/WatchlistIntradayCards";

function pctText(value: number | null | undefined): string {
  if (value == null) return "--";
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

function priceText(price: number, source: string): string {
  if (source === "unavailable" && price === 0) {
    return "--";
  }
  return price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function changeText(change: number | null | undefined): string {
  if (change == null || !Number.isFinite(change)) return "--";
  return `${change >= 0 ? "+" : ""}${change.toFixed(2)}`;
}

function volumeText(volume: number | null | undefined): string {
  if (volume == null || !Number.isFinite(volume)) return "--";
  if (volume >= 1e8) return `${(volume / 1e8).toFixed(2)} 亿`;
  if (volume >= 1e4) return `${(volume / 1e4).toFixed(1)} 万`;
  return volume.toLocaleString();
}

function barWidthByPct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) {
    return "0%";
  }
  const width = Math.min(100, Math.max(3, Math.abs(value) * 8));
  return `${width}%`;
}

function toErrorText(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error ?? "Unknown error");
}

function snapshotFallback(): DashboardSnapshot {
  return {
    generated_at: "",
    auto_refresh_enabled: true,
    auto_refresh_seconds: 15,
    indices: [],
    watchlist: [],
    pagination: {
      page: 1,
      page_size: 10,
      total: 0,
      total_pages: 0,
    },
  };
}

function toneByPct(pct: number | null | undefined): {
  cardClass: string;
  textClass: string;
  barClass: string;
  icon: "up" | "down" | "flat";
} {
  if (pct == null) {
    return {
      cardClass: "border-slate-300/60 bg-gradient-to-br from-slate-100/80 to-slate-200/50 dark:from-slate-900 dark:to-slate-800",
      textClass: "text-slate-600 dark:text-slate-300",
      barClass: "bg-slate-500",
      icon: "flat",
    };
  }
  if (pct >= 0) {
    return {
      cardClass: "border-emerald-300/60 bg-gradient-to-br from-emerald-100/80 via-cyan-100/60 to-sky-100/50 dark:from-emerald-950/40 dark:to-sky-950/30",
      textClass: "text-emerald-700 dark:text-emerald-300",
      barClass: "bg-gradient-to-r from-emerald-500 to-cyan-500",
      icon: "up",
    };
  }
  return {
    cardClass: "border-rose-300/60 bg-gradient-to-br from-rose-100/80 via-orange-100/60 to-amber-100/50 dark:from-rose-950/40 dark:to-amber-950/30",
    textClass: "text-rose-700 dark:text-rose-300",
    barClass: "bg-gradient-to-r from-rose-500 to-orange-500",
    icon: "down",
  };
}

type MarketMeta = {
  key: string;
  label: string;
  labelEn: string;
  icon: typeof Globe2;
  sectionClass: string;
};

const MARKET_META: MarketMeta[] = [
  {
    key: "CN",
    label: "A股市场",
    labelEn: "China A-Shares",
    icon: BarChart3,
    sectionClass: "border-rose-200/60 bg-gradient-to-br from-white to-rose-50/40 dark:from-slate-900 dark:to-rose-950/20",
  },
  {
    key: "HK",
    label: "港股市场",
    labelEn: "Hong Kong",
    icon: Globe2,
    sectionClass: "border-amber-200/60 bg-gradient-to-br from-white to-amber-50/40 dark:from-slate-900 dark:to-amber-950/20",
  },
  {
    key: "US",
    label: "美股市场",
    labelEn: "US Market",
    icon: TrendingUp,
    sectionClass: "border-sky-200/60 bg-gradient-to-br from-white to-sky-50/40 dark:from-slate-900 dark:to-sky-950/20",
  },
];

const IndexCard = memo(function IndexCard({ item }: { item: DashboardIndexMetric }) {
  const tone = toneByPct(item.change_percent);
  return (
    <Card className={`${tone.cardClass} transition-all duration-200 hover:scale-[1.02] hover:shadow-lg`}>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">{item.alias || item.symbol}</CardTitle>
          <Badge variant="outline" className="h-5 px-2 text-[10px]">
            {item.source}
          </Badge>
        </div>
        <CardDescription className="text-xs">
          {item.symbol} / {item.market}
          {item.currency ? ` / ${item.currency}` : ""}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <div className="flex items-end justify-between">
          <div className="text-2xl font-bold tabular-nums">{priceText(item.price, item.source)}</div>
          <div className="text-right">
            <div className={`text-base font-semibold tabular-nums ${tone.textClass}`}>
              {pctText(item.change_percent)}
            </div>
            <div className={`text-xs tabular-nums ${tone.textClass}`}>
              {changeText(item.change)}
            </div>
          </div>
        </div>
        <div className="h-2 rounded-full bg-muted/70">
          <div
            className={`h-2 rounded-full transition-all duration-500 ${tone.barClass}`}
            style={{ width: barWidthByPct(item.change_percent) }}
          />
        </div>
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>vol {volumeText(item.volume)}</span>
          <div className="flex items-center gap-1">
            {tone.icon === "up" ? <TrendingUp className="h-3 w-3 text-emerald-500" /> : null}
            {tone.icon === "down" ? <TrendingDown className="h-3 w-3 text-rose-500" /> : null}
            {tone.icon === "flat" ? <Activity className="h-3 w-3" /> : null}
            <span>{tone.icon === "flat" ? "暂无方向" : tone.icon === "up" ? "偏强" : "偏弱"}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
});

export function DashboardPage() {
  const queryClient = useQueryClient();
  const notifier = useNotifier();
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const snapshotQuery = useQuery({
    queryKey: ["dashboard-snapshot", page, pageSize, true],
    queryFn: () => api.getDashboardSnapshot(page, pageSize, true),
    retry: false,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data?.auto_refresh_enabled) {
        return false;
      }
      return Math.max(3000, data.auto_refresh_seconds * 1000);
    },
  });

  const snapshot = snapshotQuery.data ?? snapshotFallback();
  const indices = snapshot.indices;
  const watchlistRows = snapshot.watchlist;
  const pagination = snapshot.pagination;
  const errorText = snapshotQuery.error ? toErrorText(snapshotQuery.error) : "";

  const updatedAtText = useMemo(() => {
    if (!snapshot.generated_at) {
      return "--";
    }
    return new Date(snapshot.generated_at).toLocaleString();
  }, [snapshot.generated_at]);

  const upCount = useMemo(
    () => indices.filter((item) => (item.change_percent ?? 0) > 0).length,
    [indices]
  );
  const downCount = useMemo(
    () => indices.filter((item) => (item.change_percent ?? 0) < 0).length,
    [indices]
  );

  const indicesByMarket = useMemo(() => {
    const grouped: Record<string, DashboardIndexMetric[]> = {};
    for (const item of indices) {
      const market = item.market || "OTHER";
      if (!grouped[market]) grouped[market] = [];
      grouped[market].push(item);
    }
    return grouped;
  }, [indices]);

  useEffect(() => {
    if (pagination.total_pages === 0 && page !== 1) {
      setPage(1);
      return;
    }
    if (pagination.total_pages > 0 && page > pagination.total_pages) {
      setPage(pagination.total_pages);
    }
  }, [page, pagination.total_pages]);

  const toggleAutoRefreshMutation = useMutation({
    mutationFn: async (enabled: boolean) => api.updateDashboardAutoRefresh(enabled),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["config"] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard-snapshot"] });
    },
    onError: (error) => {
      notifier.error("更新自动刷新失败", toErrorText(error));
    },
  });

  const onToggleAutoRefresh = () => {
    void toggleAutoRefreshMutation.mutateAsync(!snapshot.auto_refresh_enabled);
  };

  return (
    <div className="space-y-6">
      {/* Hero header */}
      <section className="relative overflow-hidden rounded-3xl border border-sky-300/50 bg-gradient-to-br from-sky-500/15 via-emerald-500/10 to-amber-400/15 p-6">
        <div className="pointer-events-none absolute -left-12 -top-14 h-44 w-44 rounded-full bg-sky-400/20 blur-3xl" />
        <div className="pointer-events-none absolute right-0 top-10 h-32 w-32 rounded-full bg-emerald-400/20 blur-2xl" />
        <div className="pointer-events-none absolute -bottom-12 right-10 h-44 w-44 rounded-full bg-amber-400/20 blur-3xl" />

        <div className="relative flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
              <Activity className="h-5 w-5 text-sky-600" />
              Dashboard 监控总览
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              更新时间 {updatedAtText} | 自动刷新 {snapshot.auto_refresh_enabled ? `开启(${snapshot.auto_refresh_seconds}s)` : "关闭"}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 rounded-full border border-slate-300/60 bg-white/70 px-3 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-900/40">
              <span className="text-muted-foreground">自动刷新</span>
              <button
                type="button"
                role="switch"
                aria-checked={snapshot.auto_refresh_enabled}
                aria-label="切换自动刷新"
                onClick={onToggleAutoRefresh}
                disabled={toggleAutoRefreshMutation.isPending}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                  snapshot.auto_refresh_enabled ? "bg-emerald-500" : "bg-slate-400"
                } ${toggleAutoRefreshMutation.isPending ? "cursor-not-allowed opacity-60" : ""}`}
              >
                <span
                  className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${
                    snapshot.auto_refresh_enabled ? "translate-x-5" : "translate-x-0.5"
                  }`}
                />
              </button>
              <span className="tabular-nums text-muted-foreground">
                {snapshot.auto_refresh_enabled ? `${snapshot.auto_refresh_seconds}s` : "已关闭"}
              </span>
            </div>
            <Button variant="outline" onClick={() => void snapshotQuery.refetch()} disabled={snapshotQuery.isFetching}>
              <RefreshCw className={`mr-2 h-4 w-4 ${snapshotQuery.isFetching ? "animate-spin" : ""}`} />
              刷新数据
            </Button>
          </div>
        </div>
      </section>

      {/* Summary stat cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card className="border-sky-300/60 bg-gradient-to-br from-sky-100/80 to-cyan-100/60 dark:from-sky-950/40 dark:to-cyan-950/20">
          <CardHeader className="pb-2">
            <CardDescription>监控指数</CardDescription>
            <CardTitle className="text-2xl">{indices.length}</CardTitle>
          </CardHeader>
          <CardContent className="text-xs text-muted-foreground">
            CN {indicesByMarket["CN"]?.length ?? 0} / HK {indicesByMarket["HK"]?.length ?? 0} / US {indicesByMarket["US"]?.length ?? 0}
          </CardContent>
        </Card>
        <Card className="border-emerald-300/60 bg-gradient-to-br from-emerald-100/80 to-emerald-200/60 dark:from-emerald-950/40 dark:to-emerald-900/20">
          <CardHeader className="pb-2">
            <CardDescription>上涨指数</CardDescription>
            <CardTitle className="flex items-center gap-2 text-2xl">
              {upCount}
              <TrendingUp className="h-5 w-5 text-emerald-500" />
            </CardTitle>
          </CardHeader>
        </Card>
        <Card className="border-rose-300/60 bg-gradient-to-br from-rose-100/80 to-amber-100/60 dark:from-rose-950/40 dark:to-amber-950/20">
          <CardHeader className="pb-2">
            <CardDescription>下跌指数</CardDescription>
            <CardTitle className="flex items-center gap-2 text-2xl">
              {downCount}
              <TrendingDown className="h-5 w-5 text-rose-500" />
            </CardTitle>
          </CardHeader>
        </Card>
        <Card className="border-violet-300/60 bg-gradient-to-br from-violet-100/80 to-fuchsia-100/60 dark:from-violet-950/40 dark:to-fuchsia-950/20">
          <CardHeader className="pb-2">
            <CardDescription>Watchlist 总数</CardDescription>
            <CardTitle className="text-2xl">{pagination.total}</CardTitle>
          </CardHeader>
        </Card>
      </div>

      {/* Market index panels grouped by market */}
      {MARKET_META.map((meta) => {
        const items = indicesByMarket[meta.key];
        if (!items?.length) return null;
        const MarketIcon = meta.icon;
        return (
          <Card key={meta.key} className={meta.sectionClass}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <MarketIcon className="h-4 w-4" />
                {meta.label}
                <Badge variant="outline" className="ml-1 text-[10px]">
                  {meta.labelEn}
                </Badge>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {items.map((item) => (
                  <IndexCard key={`${item.symbol}-${item.market}`} item={item} />
                ))}
              </div>
            </CardContent>
          </Card>
        );
      })}

      {/* Fallback for indices with unknown market */}
      {Object.entries(indicesByMarket)
        .filter(([key]) => !MARKET_META.some((m) => m.key === key))
        .map(([key, items]) => (
          <Card key={key} className="border-slate-200/60 bg-gradient-to-br from-white to-slate-50/40 dark:from-slate-900 dark:to-slate-950/20">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Gauge className="h-4 w-4" />
                {key} 市场
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                {items.map((item) => (
                  <IndexCard key={`${item.symbol}-${item.market}`} item={item} />
                ))}
              </div>
            </CardContent>
          </Card>
        ))}

      {!indices.length ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            暂无指数配置，请前往 Config 页面配置 `dashboard.indices`。
          </CardContent>
        </Card>
      ) : null}

      {/* Watchlist intraday */}
      <WatchlistIntradayCards
        rows={watchlistRows}
        pagination={pagination}
        page={page}
        pageSize={pageSize}
        setPage={setPage}
        setPageSize={setPageSize}
        isFetching={snapshotQuery.isFetching}
        errorText={errorText}
      />
    </div>
  );
}
