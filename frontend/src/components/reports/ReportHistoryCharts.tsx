import { useEffect, useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import { Activity } from "lucide-react";

import type { ReportSummary } from "@/api/client";
import { buildReportHistoryChartOption } from "@/lib/reportCharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type Props = {
  reports: ReportSummary[];
};

function useDarkMode(): boolean {
  const [isDark, setIsDark] = useState<boolean>(() => {
    if (typeof document === "undefined") {
      return false;
    }
    return document.documentElement.classList.contains("dark");
  });

  useEffect(() => {
    if (typeof document === "undefined") {
      return;
    }
    const root = document.documentElement;
    const observer = new MutationObserver(() => {
      setIsDark(root.classList.contains("dark"));
    });
    observer.observe(root, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  return isDark;
}

export function ReportHistoryCharts({ reports }: Props) {
  const isDark = useDarkMode();

  const option = useMemo(() => {
    try {
      return buildReportHistoryChartOption(reports, isDark);
    } catch {
      return null;
    }
  }, [reports, isDark]);

  return (
    <Card className="border-indigo-200/60 bg-gradient-to-br from-white to-indigo-50/30 dark:from-slate-900 dark:to-indigo-950/20">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Activity className="h-4 w-4 text-indigo-500" />
          历史趋势
        </CardTitle>
        <p className="text-xs text-muted-foreground">confidence（折线）+ warnings_count（柱状），最多展示最近 100 条。</p>
      </CardHeader>
      <CardContent>
        {!option ? (
          <div className="rounded-lg border border-dashed border-border p-6 text-sm text-muted-foreground">
            暂无历史趋势数据。
          </div>
        ) : (
          <ReactECharts option={option} style={{ height: 280, width: "100%" }} notMerge lazyUpdate />
        )}
      </CardContent>
    </Card>
  );
}
