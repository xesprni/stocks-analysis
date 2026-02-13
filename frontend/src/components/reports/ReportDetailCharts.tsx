import { Component, type ReactNode, useEffect, useMemo, useState } from "react";
import ReactECharts from "echarts-for-react";
import type { EChartsOption } from "echarts";
import { BarChart3, Newspaper, TrendingUp } from "lucide-react";

import type { ReportDetail } from "@/api/client";
import { buildReportIndicatorChartOption, buildReportNewsChartOption, buildReportPriceChartOption } from "@/lib/reportCharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type Props = {
  detail: ReportDetail;
};

type ChartCardProps = {
  title: string;
  description: string;
  icon: typeof BarChart3;
  option: EChartsOption | null;
  emptyText: string;
};

class ChartErrorBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { hasError: boolean }> {
  constructor(props: { fallback: ReactNode; children: ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(): { hasError: boolean } {
    return { hasError: true };
  }

  componentDidUpdate(prevProps: { children: ReactNode }): void {
    if (this.state.hasError && prevProps.children !== this.props.children) {
      this.setState({ hasError: false });
    }
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback;
    }
    return this.props.children;
  }
}

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

function ChartCard({ title, description, icon: Icon, option, emptyText }: ChartCardProps) {
  const fallback = <div className="rounded-lg border border-dashed border-border p-6 text-sm text-muted-foreground">图表渲染失败，已降级为文本展示。</div>;

  return (
    <Card className="border-cyan-200/50 bg-gradient-to-br from-white to-cyan-50/30 dark:from-slate-900 dark:to-cyan-950/20">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Icon className="h-4 w-4 text-cyan-600" />
          {title}
        </CardTitle>
        <p className="text-xs text-muted-foreground">{description}</p>
      </CardHeader>
      <CardContent>
        {!option ? (
          <div className="rounded-lg border border-dashed border-border p-6 text-sm text-muted-foreground">{emptyText}</div>
        ) : (
          <ChartErrorBoundary fallback={fallback}>
            <ReactECharts option={option} style={{ height: 280, width: "100%" }} notMerge lazyUpdate />
          </ChartErrorBoundary>
        )}
      </CardContent>
    </Card>
  );
}

export function ReportDetailCharts({ detail }: Props) {
  const isDark = useDarkMode();

  const { priceOption, indicatorOption, newsOption } = useMemo(() => {
    try {
      return {
        priceOption: buildReportPriceChartOption(detail, isDark),
        indicatorOption: buildReportIndicatorChartOption(detail, isDark),
        newsOption: buildReportNewsChartOption(detail, isDark),
      };
    } catch {
      return {
        priceOption: null,
        indicatorOption: null,
        newsOption: null,
      };
    }
  }, [detail, isDark]);

  return (
    <div className="grid gap-4 xl:grid-cols-3">
      <ChartCard
        title="价格走势"
        description="优先展示 K 线，无 OHLC 时自动降级为收盘价折线。"
        icon={TrendingUp}
        option={priceOption}
        emptyText="本报告无可用价格历史数据。"
      />
      <ChartCard
        title="指标快照"
        description="基于 compute_indicators.values 的数值型指标柱状图。"
        icon={BarChart3}
        option={indicatorOption}
        emptyText="本报告无可用指标数据。"
      />
      <ChartCard
        title="新闻结构"
        description="媒体来源占比 + 新闻总条数。"
        icon={Newspaper}
        option={newsOption}
        emptyText="本报告无可用新闻数据。"
      />
    </div>
  );
}
