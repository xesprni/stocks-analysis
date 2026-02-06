import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BellRing,
  ChartCandlestick,
  ClipboardList,
  LayoutDashboard,
  ListChecks,
  Settings2,
} from "lucide-react";

import { api, type AppConfig, type ReportSummary, type UIOptions } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AlertCenterPage } from "@/pages/AlertCenter";
import { DashboardPage } from "@/pages/Dashboard";
import { ProvidersPage } from "@/pages/Providers";
import { ReportsPage } from "@/pages/Reports";
import { StockTerminalPage } from "@/pages/StockTerminal";
import { WatchlistPage } from "@/pages/Watchlist";

const emptyConfig: AppConfig = {
  output_root: "output",
  config_file: "config/settings.yaml",
  timezone: "Asia/Shanghai",
  news_limit: 20,
  flow_periods: 12,
  request_timeout_seconds: 20,
  user_agent: "",
  modules: {
    news: { default_provider: "rss" },
    fund_flow: { providers: ["eastmoney", "fred"] },
    market_data: { default_provider: "composite", poll_seconds: 5 },
    news_listener: { default_provider: "watchlist_listener" },
    symbol_search: { default_provider: "composite" },
  },
  analysis: {
    default_provider: "mock",
    default_model: "market-default",
    providers: [],
  },
  watchlist: {
    default_market_scope: ["CN", "HK", "US"],
  },
  news_listener: {
    enabled: true,
    interval_minutes: 15,
    move_window_minutes: 15,
    move_threshold_percent: 2.0,
    max_news_per_cycle: 120,
    analysis_provider: null,
    analysis_model: null,
  },
  symbol_search: {
    default_provider: "composite",
    max_results: 20,
  },
  database: { url: "sqlite:///data/market_reporter.db" },
  news_sources: [],
};

const emptyOptions: UIOptions = {
  markets: ["ALL", "CN", "HK", "US"],
  intervals: ["1m", "5m", "1d"],
  timezones: ["Asia/Shanghai", "UTC"],
  news_providers: ["rss"],
  fund_flow_providers: ["eastmoney", "fred"],
  market_data_providers: ["composite", "akshare", "yfinance"],
  analysis_providers: ["mock", "openai_compatible"],
  analysis_models_by_provider: {
    mock: ["market-default"],
    openai_compatible: ["gpt-4o-mini"],
  },
  listener_threshold_presets: [1, 1.5, 2, 3],
  listener_intervals: [5, 10, 15, 30],
};

export default function App() {
  const queryClient = useQueryClient();

  const [configDraft, setConfigDraft] = useState<AppConfig>(emptyConfig);
  const [sourcesText, setSourcesText] = useState("[]");
  const [selectedRunId, setSelectedRunId] = useState<string>("");
  const [errorMessage, setErrorMessage] = useState("");
  const [warningMessage, setWarningMessage] = useState("");
  const [alertStatus, setAlertStatus] = useState("UNREAD");
  const [alertMarket, setAlertMarket] = useState("ALL");
  const [alertSymbol, setAlertSymbol] = useState("");

  const configQuery = useQuery({ queryKey: ["config"], queryFn: api.getConfig });
  const uiOptionsQuery = useQuery({ queryKey: ["ui-options"], queryFn: api.getUiOptions });
  const reportsQuery = useQuery({ queryKey: ["reports"], queryFn: api.listReports });
  const watchlistQuery = useQuery({ queryKey: ["watchlist"], queryFn: api.listWatchlist });
  const providersQuery = useQuery({ queryKey: ["providers"], queryFn: api.listAnalysisProviders });
  const listenerRunsQuery = useQuery({
    queryKey: ["news-listener-runs"],
    queryFn: () => api.listNewsListenerRuns(50),
    refetchInterval: 15000,
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
    refetchInterval: 15000,
  });
  const detailQuery = useQuery({
    queryKey: ["report-detail", selectedRunId],
    queryFn: () => api.getReport(selectedRunId),
    enabled: Boolean(selectedRunId),
  });

  useEffect(() => {
    if (configQuery.data) {
      setConfigDraft(configQuery.data);
      setSourcesText(JSON.stringify(configQuery.data.news_sources, null, 2));
    }
  }, [configQuery.data]);

  const saveConfigMutation = useMutation({
    mutationFn: async () => {
      const newsSources = JSON.parse(sourcesText);
      return api.updateConfig({
        ...configDraft,
        news_sources: newsSources,
      });
    },
    onSuccess: async (nextConfig) => {
      setConfigDraft(nextConfig);
      setSourcesText(JSON.stringify(nextConfig.news_sources, null, 2));
      await queryClient.invalidateQueries({ queryKey: ["config"] });
      setErrorMessage("");
    },
    onError: (error) => setErrorMessage((error as Error).message),
  });

  const runReportMutation = useMutation({
    mutationFn: () =>
      api.runReport({
        news_limit: configDraft.news_limit,
        flow_periods: configDraft.flow_periods,
        timezone: configDraft.timezone,
        provider_id: configDraft.analysis.default_provider,
        model: configDraft.analysis.default_model,
      }),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ["reports"] });
      setSelectedRunId(result.summary.run_id);
      setWarningMessage(result.warnings[0] || "");
      setErrorMessage("");
    },
    onError: (error) => {
      setWarningMessage("");
      setErrorMessage((error as Error).message);
    },
  });

  const sortedReports = useMemo(
    () => [...(reportsQuery.data ?? [])].sort((a: ReportSummary, b: ReportSummary) => b.run_id.localeCompare(a.run_id)),
    [reportsQuery.data]
  );
  const options = uiOptionsQuery.data ?? emptyOptions;

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
  }, [sortedReports, selectedRunId]);

  const navItems = [
    { key: "dashboard", label: "Dashboard", icon: LayoutDashboard },
    { key: "watchlist", label: "Watchlist", icon: ListChecks },
    { key: "terminal", label: "Stock Terminal", icon: ChartCandlestick },
    { key: "alerts", label: "Alert Center", icon: BellRing },
    { key: "providers", label: "Providers", icon: Settings2 },
    { key: "reports", label: "Reports", icon: ClipboardList },
  ];

  return (
    <main className="container py-10">
      <section className="mb-8 rounded-2xl border border-border/80 bg-white/70 p-6 shadow-[0_20px_60px_rgba(0,0,0,0.08)] backdrop-blur">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-tight text-foreground">Market Reporter Pro Console</h1>
            <p className="mt-2 text-sm text-muted-foreground">模块化多实现、watchlist、实时曲线、K线与多模型分析。</p>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="secondary">FastAPI</Badge>
            <Badge>shadcn/ui</Badge>
            <Badge variant="outline">react-query</Badge>
            <Badge variant="outline">lightweight-charts</Badge>
          </div>
        </div>
      </section>

      {errorMessage ? (
        <Card className="mb-6 border-destructive/40 bg-destructive/10">
          <CardContent className="py-4 text-sm text-destructive">{errorMessage}</CardContent>
        </Card>
      ) : null}
      {warningMessage ? (
        <Card className="mb-6 border-amber-300/70 bg-amber-50">
          <CardContent className="py-4 text-sm text-amber-800">{warningMessage}</CardContent>
        </Card>
      ) : null}

      <Tabs
        defaultValue="dashboard"
        orientation="vertical"
        className="grid items-start gap-5 lg:grid-cols-[220px_minmax(0,1fr)]"
      >
        <TabsList className="h-auto w-full flex-col items-stretch rounded-2xl border border-border/80 bg-white/80 p-2 lg:sticky lg:top-6">
          {navItems.map((item) => (
            <TabsTrigger
              key={item.key}
              value={item.key}
              className="relative w-full justify-start gap-3 px-4 py-2 text-sm data-[state=active]:bg-white data-[state=active]:shadow-sm before:absolute before:left-1 before:top-2 before:bottom-2 before:w-1 before:rounded-full before:bg-foreground before:opacity-0 before:transition-opacity data-[state=active]:before:opacity-100"
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="dashboard" className="mt-0">
          <DashboardPage
            config={configDraft}
            options={options}
            setConfig={setConfigDraft}
            sourcesText={sourcesText}
            setSourcesText={setSourcesText}
            onSave={() => saveConfigMutation.mutate()}
            onReload={() => {
              void configQuery.refetch();
              setErrorMessage("");
            }}
            onRunReport={() => runReportMutation.mutate()}
            saving={saveConfigMutation.isPending}
            running={runReportMutation.isPending}
          />
        </TabsContent>

        <TabsContent value="watchlist" className="mt-0">
          <WatchlistPage
            items={watchlistQuery.data ?? []}
            markets={options.markets}
            onSearch={(query, market) => api.searchStocks(query, market, configDraft.symbol_search.max_results)}
            onAdd={async (payload) => {
              await api.createWatchlistItem(payload);
              await queryClient.invalidateQueries({ queryKey: ["watchlist"] });
            }}
            onDelete={async (id) => {
              await api.deleteWatchlistItem(id);
              await queryClient.invalidateQueries({ queryKey: ["watchlist"] });
            }}
          />
        </TabsContent>

        <TabsContent value="terminal" className="mt-0">
          <StockTerminalPage
            defaultProvider={configDraft.analysis.default_provider}
            defaultModel={configDraft.analysis.default_model}
            markets={options.markets}
            intervals={options.intervals}
            onSearch={(query, market) => api.searchStocks(query, market, configDraft.symbol_search.max_results)}
          />
        </TabsContent>

        <TabsContent value="alerts" className="mt-0">
          <AlertCenterPage
            alerts={alertsQuery.data ?? []}
            runs={listenerRunsQuery.data ?? []}
            status={alertStatus}
            setStatus={setAlertStatus}
            market={alertMarket}
            setMarket={setAlertMarket}
            symbol={alertSymbol}
            setSymbol={setAlertSymbol}
            onRunNow={async () => {
              await api.runNewsListener();
              await queryClient.invalidateQueries({ queryKey: ["news-alerts"] });
              await queryClient.invalidateQueries({ queryKey: ["news-listener-runs"] });
            }}
            onMarkAllRead={async () => {
              await api.markAllNewsAlertsRead();
              await queryClient.invalidateQueries({ queryKey: ["news-alerts"] });
            }}
            onMarkAlert={async (id, status) => {
              await api.updateNewsAlert(id, status);
              await queryClient.invalidateQueries({ queryKey: ["news-alerts"] });
            }}
            onRefresh={async () => {
              await alertsQuery.refetch();
              await listenerRunsQuery.refetch();
            }}
          />
        </TabsContent>

        <TabsContent value="providers" className="mt-0">
          <ProvidersPage
            providers={providersQuery.data ?? []}
            defaultProvider={configDraft.analysis.default_provider}
            defaultModel={configDraft.analysis.default_model}
            onSetDefault={async (providerId, model) => {
              const next = await api.updateDefaultAnalysis({ provider_id: providerId, model });
              setConfigDraft(next);
              await queryClient.invalidateQueries({ queryKey: ["config"] });
            }}
            onSaveSecret={async (providerId, apiKey) => {
              await api.putAnalysisSecret(providerId, { api_key: apiKey });
              await queryClient.invalidateQueries({ queryKey: ["providers"] });
            }}
          />
        </TabsContent>

        <TabsContent value="reports" className="mt-0">
          <ReportsPage
            reports={sortedReports}
            selectedRunId={selectedRunId}
            detail={detailQuery.data ?? null}
            onSelect={(runId) => setSelectedRunId(runId)}
          />
        </TabsContent>
      </Tabs>
    </main>
  );
}
