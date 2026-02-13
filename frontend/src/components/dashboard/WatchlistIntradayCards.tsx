import { memo } from "react";
import type { Dispatch, SetStateAction } from "react";

import type { DashboardWatchlistMetric, Pagination } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { buildWatchlistCards, type WatchlistCardViewModel } from "@/lib/watchlistSignal";

type Props = {
  rows: DashboardWatchlistMetric[];
  pagination: Pagination;
  page: number;
  pageSize: number;
  setPage: Dispatch<SetStateAction<number>>;
  setPageSize: Dispatch<SetStateAction<number>>;
  isFetching: boolean;
  errorText?: string;
};

function toneClassBySignal(level: WatchlistCardViewModel["signalLevel"]): string {
  if (level === "strong") {
    return "watchlist-chip watchlist-chip-positive";
  }
  if (level === "weak") {
    return "watchlist-chip watchlist-chip-negative";
  }
  if (level === "neutral") {
    return "watchlist-chip watchlist-chip-neutral";
  }
  return "watchlist-chip watchlist-chip-muted";
}

function toneClassByRecommendation(tag: WatchlistCardViewModel["recommendationTag"]): string {
  if (tag === "持有") {
    return "watchlist-rec watchlist-rec-hold";
  }
  if (tag === "减仓") {
    return "watchlist-rec watchlist-rec-reduce";
  }
  if (tag === "观察") {
    return "watchlist-rec watchlist-rec-watch";
  }
  return "watchlist-rec watchlist-rec-pending";
}

function toneClassByMove(card: WatchlistCardViewModel): string {
  if (card.unavailable) {
    return "watchlist-move watchlist-move-muted";
  }
  if (card.changePercent != null) {
    if (card.changePercent > 0) {
      return "watchlist-move watchlist-move-up";
    }
    if (card.changePercent < 0) {
      return "watchlist-move watchlist-move-down";
    }
  }
  return "watchlist-move watchlist-move-flat";
}

function displayTs(ts: string): string {
  const parsed = new Date(ts);
  if (Number.isNaN(parsed.getTime())) {
    return "--";
  }
  return parsed.toLocaleString();
}

export const WatchlistIntradayCards = memo(function WatchlistIntradayCards({
  rows,
  pagination,
  page,
  pageSize,
  setPage,
  setPageSize,
  isFetching,
  errorText,
}: Props) {
  const cards = buildWatchlistCards(rows);
  const pageLabel = pagination.total_pages > 0 ? `${pagination.page} / ${pagination.total_pages}` : "0 / 0";

  return (
    <div className="watchlist-panel space-y-4">
      <div className="watchlist-panel-header">
        <div className="flex items-center gap-2">
          <span className="watchlist-panel-title">盘中监控</span>
          <Badge variant="secondary" className="h-5 px-2 text-[10px]">
            {pagination.total} 只
          </Badge>
        </div>
        <div className="text-xs text-muted-foreground">可用: ¥--</div>
      </div>

      {errorText ? (
        <Card className="watchlist-error-card">
          <CardContent className="py-3 text-sm">Dashboard 数据加载失败：{errorText}</CardContent>
        </Card>
      ) : null}

      <div className="space-y-3">
        {cards.map((card) => (
          <Card key={`${card.id}-${card.symbol}-${card.market}`} className={card.unavailable ? "watchlist-card watchlist-card-unavailable" : "watchlist-card"}>
            <CardContent className="space-y-4 p-4">
              <div className="watchlist-card-top">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="watchlist-symbol">{card.symbol}</span>
                    <span className="watchlist-name">{card.name}</span>
                    <Badge variant="outline" className="h-5 px-2 text-[10px]">
                      {card.market}
                    </Badge>
                  </div>
                  <div className="text-xs text-muted-foreground">{displayTs(card.ts)}</div>
                </div>
                <div className="text-right">
                  <div className="watchlist-price">{card.priceText}</div>
                  <div className={toneClassByMove(card)}>{card.changeText}</div>
                  <div className={toneClassByMove(card)}>{card.pctText}</div>
                </div>
              </div>

              <div className="watchlist-tags-row">
                <span className={toneClassBySignal(card.signalLevel)}>{card.signalLabel}</span>
                <span className="watchlist-chip watchlist-chip-muted">{card.volumeLabel}</span>
                <span className="watchlist-chip watchlist-chip-support">支撑 {card.supportText}</span>
                <span className="watchlist-chip watchlist-chip-pressure">压力 {card.resistanceText}</span>
              </div>

              <div className="watchlist-recommend-row">
                <span className={toneClassByRecommendation(card.recommendationTag)}>{card.recommendationTag}</span>
                <div className="watchlist-reason">{card.unavailable ? "行情暂不可用，建议等待后续刷新。" : card.recommendationReason}</div>
              </div>
            </CardContent>
          </Card>
        ))}

        {!cards.length ? (
          <Card>
            <CardContent className="py-8 text-center text-sm text-muted-foreground">当前页无启用标的</CardContent>
          </Card>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
        <div className="text-sm text-muted-foreground">
          分页 {pageLabel}，共 {pagination.total} 条{isFetching ? " · 刷新中..." : ""}
        </div>
        <div className="flex items-center gap-2">
          <Select
            value={String(pageSize)}
            onValueChange={(value: string) => {
              setPageSize(Number(value));
              setPage(1);
            }}
          >
            <SelectTrigger className="w-[120px]">
              <SelectValue placeholder="每页" />
            </SelectTrigger>
            <SelectContent>
              {[10, 20, 50].map((entry) => (
                <SelectItem key={entry} value={String(entry)}>
                  {entry} / 页
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Button variant="outline" onClick={() => setPage((prev) => Math.max(1, prev - 1))} disabled={page <= 1}>
            上一页
          </Button>
          <Button
            variant="outline"
            onClick={() => setPage((prev) => prev + 1)}
            disabled={pagination.total_pages === 0 || page >= pagination.total_pages}
          >
            下一页
          </Button>
        </div>
      </div>
    </div>
  );
});
