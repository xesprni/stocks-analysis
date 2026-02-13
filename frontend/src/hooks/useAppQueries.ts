import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api, type AppConfig, type ReportSummary, type UIOptions } from "@/api/client";
import { useNotifier } from "@/components/ui/notifier";

const emptyOptions: UIOptions = {
  markets: ["ALL", "CN", "HK", "US"],
  intervals: ["1m", "5m", "1d"],
  timezones: ["Asia/Shanghai", "UTC"],
  news_providers: ["rss"],
  fund_flow_providers: ["eastmoney", "fred"],
  market_data_providers: ["composite", "akshare", "yfinance"],
  analysis_providers: ["mock", "openai_compatible", "codex_app_server"],
  analysis_models_by_provider: {},
  listener_threshold_presets: [1, 1.5, 2, 3],
  listener_intervals: [5, 10, 15, 30],
};

function toErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  return String(error ?? "Unknown error");
}

export { toErrorMessage };

export function useAppQueries(
  configDraft: AppConfig,
  setConfigDraft: React.Dispatch<React.SetStateAction<AppConfig>>,
  selectedRunId: string,
  setSelectedRunId: React.Dispatch<React.SetStateAction<string>>,
  setErrorMessage: React.Dispatch<React.SetStateAction<string>>,
  alertStatus: string,
  alertMarket: string,
  alertSymbol: string,
  activeTab: string = "dashboard",
) {
  const notifier = useNotifier();
  const queryErrorCache = useRef<Record<string, string>>({});

  // ---- queries ----
  const configQuery = useQuery({ queryKey: ["config"], queryFn: api.getConfig });
  const uiOptionsQuery = useQuery({ queryKey: ["ui-options"], queryFn: api.getUiOptions });
  const reportsQuery = useQuery({ queryKey: ["reports"], queryFn: api.listReports });
  const reportTasksQuery = useQuery({
    queryKey: ["report-tasks"],
    queryFn: api.listReportTasks,
    refetchInterval: (query) => {
      // Only poll when reports or report-runner tab is active
      if (activeTab !== "reports" && activeTab !== "report-runner") return false;
      const data = query.state.data;
      if (data?.some((t) => t.status === "PENDING" || t.status === "RUNNING")) {
        return 2000;
      }
      return 30000;
    },
  });
  const watchlistQuery = useQuery({ queryKey: ["watchlist"], queryFn: api.listWatchlist });
  const newsSourcesQuery = useQuery({ queryKey: ["news-sources"], queryFn: api.listNewsSources });
  const providersQuery = useQuery({ queryKey: ["providers"], queryFn: api.listAnalysisProviders });
  const listenerRunsQuery = useQuery({
    queryKey: ["news-listener-runs"],
    queryFn: () => api.listNewsListenerRuns(50),
    refetchInterval: activeTab === "alerts" ? 15000 : false,
  });
  const alertsQuery = useQuery({
    queryKey: ["news-alerts", alertStatus, alertMarket, alertSymbol],
    queryFn: () =>
      api.listNewsAlerts({
        status: alertStatus,
        market: alertMarket === "ALL" ? "" : alertMarket,
        symbol: alertSymbol,
        limit: 50,
      }),
    refetchInterval: activeTab === "alerts" ? 15000 : false,
  });
  const detailQuery = useQuery({
    queryKey: ["report-detail", selectedRunId],
    queryFn: () => api.getReport(selectedRunId),
    enabled: Boolean(selectedRunId),
  });

  // ---- error notification helper ----
  const notifyQueryError = useCallback(
    (key: string, title: string, error: unknown) => {
      if (!error) {
        delete queryErrorCache.current[key];
        return;
      }
      const message = toErrorMessage(error);
      if (queryErrorCache.current[key] === message) {
        return;
      }
      queryErrorCache.current[key] = message;
      setErrorMessage(message);
      notifier.error(title, message, { dedupeKey: `query-${key}` });
    },
    [notifier, setErrorMessage]
  );

  // ---- error notification effects ----
  useEffect(() => {
    notifyQueryError("config", "加载配置失败", configQuery.error);
  }, [configQuery.error, notifyQueryError]);

  useEffect(() => {
    notifyQueryError("ui-options", "加载下拉配置失败", uiOptionsQuery.error);
  }, [uiOptionsQuery.error, notifyQueryError]);

  useEffect(() => {
    notifyQueryError("reports", "加载报告列表失败", reportsQuery.error);
  }, [reportsQuery.error, notifyQueryError]);

  useEffect(() => {
    notifyQueryError("report-tasks", "加载报告任务失败", reportTasksQuery.error);
  }, [reportTasksQuery.error, notifyQueryError]);

  useEffect(() => {
    notifyQueryError("report-detail", "加载报告详情失败", detailQuery.error);
  }, [detailQuery.error, notifyQueryError]);

  useEffect(() => {
    notifyQueryError("watchlist", "加载 Watchlist 失败", watchlistQuery.error);
  }, [watchlistQuery.error, notifyQueryError]);

  useEffect(() => {
    notifyQueryError("news-sources", "加载新闻来源失败", newsSourcesQuery.error);
  }, [newsSourcesQuery.error, notifyQueryError]);

  useEffect(() => {
    notifyQueryError("providers", "加载 Provider 列表失败", providersQuery.error);
  }, [providersQuery.error, notifyQueryError]);

  useEffect(() => {
    notifyQueryError("listener-runs", "加载监听运行记录失败", listenerRunsQuery.error);
  }, [listenerRunsQuery.error, notifyQueryError]);

  useEffect(() => {
    notifyQueryError("alerts", "加载告警列表失败", alertsQuery.error);
  }, [alertsQuery.error, notifyQueryError]);

  // ---- sync config from server into draft ----
  useEffect(() => {
    if (configQuery.data) {
      setConfigDraft(configQuery.data);
    }
  }, [configQuery.data, setConfigDraft]);

  // ---- derived data ----
  const sortedReports = useMemo(
    () => [...(reportsQuery.data ?? [])].sort((a: ReportSummary, b: ReportSummary) => b.run_id.localeCompare(a.run_id)),
    [reportsQuery.data]
  );
  const options = uiOptionsQuery.data ?? emptyOptions;

  // ---- auto-select first report ----
  useEffect(() => {
    if (!sortedReports.length) {
      if (selectedRunId) {
        setSelectedRunId("");
      }
      return;
    }
    const exists = sortedReports.some((item) => item.run_id === selectedRunId);
    if (!exists) {
      setSelectedRunId(sortedReports[0].run_id);
    }
  }, [sortedReports, selectedRunId, setSelectedRunId]);

  return {
    configQuery,
    uiOptionsQuery,
    reportsQuery,
    reportTasksQuery,
    watchlistQuery,
    newsSourcesQuery,
    providersQuery,
    listenerRunsQuery,
    alertsQuery,
    detailQuery,
    sortedReports,
    options,
  };
}
