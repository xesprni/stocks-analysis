import { useEffect, useMemo, useState } from "react";
import { Newspaper, RefreshCw } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useNotifier } from "@/components/ui/notifier";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

function toErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error ?? "Unknown error");
}

export function NewsFeedPage() {
  const notifier = useNotifier();
  const [selectedSourceId, setSelectedSourceId] = useState("ALL");
  const [errorCache, setErrorCache] = useState<Record<string, string>>({});

  const optionsQuery = useQuery({
    queryKey: ["news-feed-options"],
    queryFn: api.listNewsFeedOptions,
    refetchInterval: 60_000,
  });

  const feedQuery = useQuery({
    queryKey: ["news-feed", selectedSourceId],
    queryFn: () => api.listNewsFeed(selectedSourceId, 50),
    refetchInterval: 30_000,
  });

  useEffect(() => {
    const error = optionsQuery.error;
    if (!error) {
      return;
    }
    const message = toErrorMessage(error);
    if (errorCache["options"] === message) {
      return;
    }
    setErrorCache((prev) => ({ ...prev, options: message }));
    notifier.error("加载新闻来源失败", message, { dedupeKey: "news-feed-options" });
  }, [errorCache, notifier, optionsQuery.error]);

  useEffect(() => {
    const error = feedQuery.error;
    if (!error) {
      return;
    }
    const message = toErrorMessage(error);
    if (errorCache["feed"] === message) {
      return;
    }
    setErrorCache((prev) => ({ ...prev, feed: message }));
    notifier.error("加载新闻聚合失败", message, { dedupeKey: "news-feed-list" });
  }, [errorCache, feedQuery.error, notifier]);

  const sourceTabs = useMemo(() => {
    const enabled = (optionsQuery.data ?? []).filter((item) => item.enabled);
    return [{ source_id: "ALL", name: "All", enabled: true }, ...enabled];
  }, [optionsQuery.data]);

  const warnings = feedQuery.data?.warnings ?? [];
  const items = feedQuery.data?.items ?? [];

  return (
    <div className="space-y-6">
      {/* Hero header */}
      <section className="relative overflow-hidden rounded-3xl border border-amber-300/50 bg-gradient-to-br from-amber-500/15 via-orange-500/10 to-rose-400/15 p-6">
        <div className="pointer-events-none absolute -left-12 -top-14 h-44 w-44 rounded-full bg-amber-400/20 blur-3xl" />
        <div className="pointer-events-none absolute right-0 top-10 h-32 w-32 rounded-full bg-orange-400/20 blur-2xl" />
        <div className="pointer-events-none absolute -bottom-12 right-10 h-44 w-44 rounded-full bg-rose-400/20 blur-3xl" />
        <div className="relative flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
              <Newspaper className="h-5 w-5 text-amber-600" />
              新闻聚合
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              实时汇聚多来源财经新闻，当前 {items.length} 条资讯。
            </p>
          </div>
          <Button variant="outline" onClick={() => void feedQuery.refetch()} disabled={feedQuery.isFetching}>
            <RefreshCw className={`mr-2 h-4 w-4 ${feedQuery.isFetching ? "animate-spin" : ""}`} />
            刷新
          </Button>
        </div>
      </section>

      {/* Source tabs */}
      <Card className="border-amber-200/60 bg-gradient-to-br from-white to-amber-50/40 dark:from-slate-900 dark:to-amber-950/20">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Newspaper className="h-4 w-4 text-amber-600" />
            新闻来源
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex min-w-0 flex-1 flex-wrap gap-2">
            {sourceTabs.map((item) => (
              <Button
                key={item.source_id}
                variant={selectedSourceId === item.source_id ? "default" : "outline"}
                size="sm"
                className={
                  selectedSourceId === item.source_id
                    ? "bg-gradient-to-r from-amber-600 to-orange-600 text-white hover:from-amber-700 hover:to-orange-700"
                    : ""
                }
                onClick={() => setSelectedSourceId(item.source_id)}
              >
                {item.name}
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>

      {warnings.length ? (
        <div className="space-y-2 rounded-xl border border-amber-300/70 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-700/70 dark:bg-amber-950/50 dark:text-amber-200">
          {warnings.map((warning) => (
            <div key={warning}>{warning}</div>
          ))}
        </div>
      ) : null}

      {/* News table */}
      <Card className="border-orange-200/60 bg-gradient-to-br from-white to-orange-50/40 dark:from-slate-900 dark:to-orange-950/20">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            新闻列表
            <Badge variant="outline" className="ml-1 text-xs">
              {items.length} 条
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto rounded-lg border border-orange-200/40 dark:border-orange-800/30">
            <Table>
              <TableHeader>
                <TableRow className="bg-orange-50/50 dark:bg-orange-950/20">
                  <TableHead>时间</TableHead>
                  <TableHead>来源</TableHead>
                  <TableHead>分类</TableHead>
                  <TableHead>标题</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => (
                  <TableRow key={`${item.source_id}:${item.title}:${item.link}`} className="hover:bg-orange-50/30 dark:hover:bg-orange-950/10">
                    <TableCell className="whitespace-nowrap text-xs">
                      {item.published ? new Date(item.published).toLocaleString() : "--"}
                    </TableCell>
                    <TableCell>
                      <div className="space-y-1">
                        <div className="font-medium">{item.source_name}</div>
                        <div className="font-mono text-xs text-muted-foreground">{item.source_id}</div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{item.category || "-"}</Badge>
                    </TableCell>
                    <TableCell>
                      {item.link ? (
                        <a className="text-sm underline-offset-4 hover:text-amber-700 hover:underline dark:hover:text-amber-300" href={item.link} target="_blank" rel="noreferrer">
                          {item.title}
                        </a>
                      ) : (
                        <span>{item.title}</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
                {!items.length ? (
                  <TableRow>
                    <TableCell colSpan={4} className="py-8 text-center text-sm text-muted-foreground">
                      当前来源暂无新闻
                    </TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
