import { useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
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
      <Card>
        <CardHeader>
          <CardTitle>新闻聚合</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between gap-3">
            <div className="flex min-w-0 flex-1 gap-2 overflow-x-auto pb-1">
              {sourceTabs.map((item) => (
                <Button
                  key={item.source_id}
                  variant={selectedSourceId === item.source_id ? "default" : "outline"}
                  className="whitespace-nowrap"
                  onClick={() => setSelectedSourceId(item.source_id)}
                >
                  {item.name}
                </Button>
              ))}
            </div>
            <Button variant="outline" onClick={() => void feedQuery.refetch()}>
              <RefreshCw className="mr-2 h-4 w-4" />
              刷新
            </Button>
          </div>

          {warnings.length ? (
            <div className="space-y-2 rounded-md border border-amber-300/70 bg-amber-50 p-3 text-sm text-amber-800">
              {warnings.map((warning) => (
                <div key={warning}>{warning}</div>
              ))}
            </div>
          ) : null}

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>时间</TableHead>
                <TableHead>来源</TableHead>
                <TableHead>分类</TableHead>
                <TableHead>标题</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.map((item) => (
                <TableRow key={`${item.source_id}:${item.title}:${item.link}`}>
                  <TableCell className="text-xs">
                    {item.published ? new Date(item.published).toLocaleString() : "--"}
                  </TableCell>
                  <TableCell>
                    <div className="space-y-1">
                      <div>{item.source_name}</div>
                      <div className="font-mono text-xs text-muted-foreground">{item.source_id}</div>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{item.category || "-"}</Badge>
                  </TableCell>
                  <TableCell>
                    {item.link ? (
                      <a className="text-sm underline-offset-4 hover:underline" href={item.link} target="_blank" rel="noreferrer">
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
        </CardContent>
      </Card>
    </div>
  );
}
