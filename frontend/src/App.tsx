import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  BellRing,
  ChartCandlestick,
  ClipboardList,
  LayoutDashboard,
  ListChecks,
  Moon,
  Newspaper,
  Rocket,
  Settings2,
  Sun,
} from "lucide-react";

import { api, type AppConfig } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useNotifier } from "@/components/ui/notifier";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { toErrorMessage, useAppQueries } from "@/hooks/useAppQueries";
import { useAppMutations } from "@/hooks/useAppMutations";
import { useProviderActions } from "@/hooks/useProviderActions";
import { AlertCenterPage } from "@/pages/AlertCenter";
import { ConfigPage } from "@/pages/Config";
import { DashboardPage } from "@/pages/Dashboard";
import { NewsFeedPage } from "@/pages/NewsFeed";
import { ReportRunnerPage } from "@/pages/ReportRunner";
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
  dashboard: {
    indices: [
      { symbol: "000001", market: "CN", alias: "\u4E0A\u8BC1\u6307\u6570" },
      { symbol: "399001", market: "CN", alias: "\u6DF1\u8BC1\u6210\u6307" },
      { symbol: "399006", market: "CN", alias: "\u521B\u4E1A\u677F\u6307" },
      { symbol: "000300", market: "CN", alias: "\u6CAA\u6DF1300" },
      { symbol: "^HSI", market: "HK", alias: "\u6052\u751F\u6307\u6570" },
      { symbol: "^HSCE", market: "HK", alias: "\u56FD\u4F01\u6307\u6570" },
      { symbol: "^HSTECH", market: "HK", alias: "\u6052\u751F\u79D1\u6280" },
      { symbol: "^GSPC", market: "US", alias: "S&P 500" },
      { symbol: "^IXIC", market: "US", alias: "NASDAQ" },
      { symbol: "^DJI", market: "US", alias: "Dow Jones" },
    ],
    auto_refresh_enabled: true,
    auto_refresh_seconds: 15,
  },
  agent: {
    enabled: true,
    max_steps: 8,
    max_tool_calls: 12,
    consistency_tolerance: 0.05,
    default_news_window_days: 30,
    default_filing_window_days: 365,
    default_price_window_days: 365,
  },
  database: { url: "sqlite:///data/market_reporter.db" },
};

export default function App() {
  const queryClient = useQueryClient();
  const notifier = useNotifier();

  const [configDraft, setConfigDraft] = useState<AppConfig>(emptyConfig);
  const [selectedRunId, setSelectedRunId] = useState<string>("");
  const [errorMessage, setErrorMessage] = useState("");
  const [warningMessage, setWarningMessage] = useState("");
  const [alertStatus, setAlertStatus] = useState("UNREAD");
  const [alertMarket, setAlertMarket] = useState("ALL");
  const [alertSymbol, setAlertSymbol] = useState("");
  const [dark, setDark] = useState(() => {
    if (typeof window !== "undefined") {
      const stored = localStorage.getItem("theme");
      if (stored === "dark") return true;
      if (stored === "light") return false;
      return window.matchMedia("(prefers-color-scheme: dark)").matches;
    }
    return false;
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);

  const {
    configQuery,
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
  } = useAppQueries(
    configDraft,
    setConfigDraft,
    selectedRunId,
    setSelectedRunId,
    setErrorMessage,
    alertStatus,
    alertMarket,
    alertSymbol,
  );

  const { saveConfigMutation, runReportMutation } = useAppMutations(
    configDraft,
    setConfigDraft,
    setSelectedRunId,
    setErrorMessage,
    setWarningMessage,
  );

  const { loadAnalysisModels, connectProviderAuth, disconnectProviderAuth } = useProviderActions();

  const navItems = [
    { key: "dashboard", label: "Dashboard", icon: LayoutDashboard },
    { key: "report-runner", label: "Run Reports", icon: Rocket },
    { key: "config", label: "Config", icon: Settings2 },
    { key: "news-feed", label: "News Feed", icon: Newspaper },
    { key: "watchlist", label: "Watchlist", icon: ListChecks },
    { key: "terminal", label: "Stock Terminal", icon: ChartCandlestick },
    { key: "alerts", label: "Alert Center", icon: BellRing },
    { key: "reports", label: "Reports", icon: ClipboardList },
  ];

  return (
    <main className="mx-auto w-full max-w-[1920px] px-4 py-6 sm:px-6 lg:px-8 xl:px-10">
      <section className="mb-6 rounded-2xl border border-border/80 bg-card p-4 shadow-[0_20px_60px_rgba(0,0,0,0.08)] sm:p-6 dark:shadow-[0_20px_60px_rgba(0,0,0,0.25)]">
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
            <Button variant="ghost" size="sm" onClick={() => setDark((prev) => !prev)} aria-label="Toggle dark mode">
              {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      </section>

      {errorMessage ? (
        <Card className="mb-6 border-destructive/40 bg-destructive/10">
          <CardContent className="py-4 text-sm text-destructive">{errorMessage}</CardContent>
        </Card>
      ) : null}
      {warningMessage ? (
        <Card className="mb-6 border-amber-300/70 bg-amber-50 dark:border-amber-700/70 dark:bg-amber-950/50">
          <CardContent className="py-4 text-sm text-amber-800 dark:text-amber-200">{warningMessage}</CardContent>
        </Card>
      ) : null}

      <Tabs
        defaultValue="dashboard"
        orientation="vertical"
        className="grid items-start gap-4 lg:grid-cols-[200px_minmax(0,1fr)] xl:grid-cols-[220px_minmax(0,1fr)]"
      >
        <TabsList className="h-auto w-full flex-col items-stretch rounded-2xl border border-border/80 bg-card p-2 lg:sticky lg:top-6">
          {navItems.map((item) => (
            <TabsTrigger
              key={item.key}
              value={item.key}
              className="relative w-full justify-start gap-3 px-4 py-2 text-sm data-[state=active]:bg-accent data-[state=active]:shadow-sm before:absolute before:left-1 before:top-2 before:bottom-2 before:w-1 before:rounded-full before:bg-foreground before:opacity-0 before:transition-opacity data-[state=active]:before:opacity-100"
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </TabsTrigger>
          ))}
        </TabsList>

        <TabsContent value="dashboard" className="mt-0">
          <DashboardPage />
        </TabsContent>

        <TabsContent value="report-runner" className="mt-0">
          <ReportRunnerPage onRunReport={(payload) => runReportMutation.mutate(payload)} running={runReportMutation.isPending} />
        </TabsContent>

        <TabsContent value="config" className="mt-0">
          <ConfigPage
            config={configDraft}
            options={options}
            analysisProviders={providersQuery.data ?? []}
            providerConfigs={configDraft.analysis.providers}
            newsSources={newsSourcesQuery.data ?? []}
            onCreateNewsSource={async (payload) => {
              try {
                await api.createNewsSource(payload);
                await queryClient.invalidateQueries({ queryKey: ["news-sources"] });
                await queryClient.invalidateQueries({ queryKey: ["config"] });
                notifier.success("新闻来源已新增", payload.name);
              } catch (error) {
                const message = toErrorMessage(error);
                setErrorMessage(message);
                notifier.error("新增新闻来源失败", message);
              }
            }}
            onUpdateNewsSource={async (sourceId, payload) => {
              try {
                await api.updateNewsSource(sourceId, payload);
                await queryClient.invalidateQueries({ queryKey: ["news-sources"] });
                await queryClient.invalidateQueries({ queryKey: ["config"] });
                notifier.success("新闻来源已更新", sourceId);
              } catch (error) {
                const message = toErrorMessage(error);
                setErrorMessage(message);
                notifier.error("更新新闻来源失败", message);
              }
            }}
            onDeleteNewsSource={async (sourceId) => {
              try {
                await api.deleteNewsSource(sourceId);
                await queryClient.invalidateQueries({ queryKey: ["news-sources"] });
                await queryClient.invalidateQueries({ queryKey: ["config"] });
                notifier.success("新闻来源已删除", sourceId);
              } catch (error) {
                const message = toErrorMessage(error);
                setErrorMessage(message);
                notifier.error("删除新闻来源失败", message);
              }
            }}
            onSetDefault={async (providerId, model) => {
              try {
                const next = await api.updateDefaultAnalysis({ provider_id: providerId, model });
                setConfigDraft(next);
                await queryClient.invalidateQueries({ queryKey: ["config"] });
                await queryClient.invalidateQueries({ queryKey: ["providers"] });
                notifier.success("默认分析模型已更新", `${providerId} / ${model}`);
              } catch (error) {
                const message = toErrorMessage(error);
                setErrorMessage(message);
                notifier.error("更新默认 Provider/Model 失败", message);
              }
            }}
            onSaveSecret={async (providerId, apiKey) => {
              try {
                await api.putAnalysisSecret(providerId, { api_key: apiKey });
                await queryClient.invalidateQueries({ queryKey: ["providers"] });
                notifier.success("API Key 已保存", providerId);
              } catch (error) {
                const message = toErrorMessage(error);
                setErrorMessage(message);
                notifier.error("保存 API Key 失败", message);
              }
            }}
            onConnectAuth={async (providerId) => {
              try {
                await connectProviderAuth(providerId);
              } catch (error) {
                const message = toErrorMessage(error);
                setErrorMessage(message);
                notifier.error("打开登录失败", message);
              }
            }}
            onDisconnectAuth={async (providerId) => {
              try {
                await disconnectProviderAuth(providerId);
              } catch (error) {
                const message = toErrorMessage(error);
                setErrorMessage(message);
                notifier.error("断开登录失败", message);
              }
            }}
            onLoadModels={loadAnalysisModels}
            onDeleteProvider={async (providerId) => {
              try {
                if (!window.confirm(`确认删除 Provider: ${providerId} ?`)) {
                  return;
                }
                const next = await api.deleteAnalysisProvider(providerId);
                setConfigDraft(next);
                await queryClient.invalidateQueries({ queryKey: ["config"] });
                await queryClient.invalidateQueries({ queryKey: ["providers"] });
                await queryClient.invalidateQueries({ queryKey: ["ui-options"] });
                notifier.success("Provider 已删除", providerId);
              } catch (error) {
                const message = toErrorMessage(error);
                setErrorMessage(message);
                notifier.error("删除 Provider 失败", message);
              }
            }}
            onSaveProviderConfig={async (providerId, patch) => {
              try {
                const nextProviders = configDraft.analysis.providers.map((provider) => {
                  if (provider.provider_id !== providerId) {
                    return provider;
                  }
                  return {
                    ...provider,
                    ...patch,
                  };
                });
                const nextConfig = {
                  ...configDraft,
                  analysis: {
                    ...configDraft.analysis,
                    providers: nextProviders,
                  },
                };
                const saved = await api.updateConfig(nextConfig);
                setConfigDraft(saved);
                await queryClient.invalidateQueries({ queryKey: ["config"] });
                await queryClient.invalidateQueries({ queryKey: ["providers"] });
                await queryClient.invalidateQueries({ queryKey: ["ui-options"] });
                notifier.success("Provider 配置已保存", providerId);
              } catch (error) {
                const message = toErrorMessage(error);
                setErrorMessage(message);
                notifier.error("保存 Provider 配置失败", message);
              }
            }}
            setConfig={setConfigDraft}
            onSave={() => saveConfigMutation.mutate()}
            onReload={() => {
              void configQuery.refetch();
              void newsSourcesQuery.refetch();
              setErrorMessage("");
            }}
            saving={saveConfigMutation.isPending}
          />
        </TabsContent>

        <TabsContent value="news-feed" className="mt-0">
          <NewsFeedPage />
        </TabsContent>

        <TabsContent value="watchlist" className="mt-0">
          <WatchlistPage
            items={watchlistQuery.data ?? []}
            markets={options.markets}
            onSearch={(query, market) => api.searchStocks(query, market, configDraft.symbol_search.max_results)}
            onAdd={async (payload) => {
              try {
                await api.createWatchlistItem(payload);
                await queryClient.invalidateQueries({ queryKey: ["watchlist"] });
                await queryClient.invalidateQueries({ queryKey: ["dashboard-snapshot"] });
                notifier.success("Watchlist 已添加", `${payload.symbol} (${payload.market})`);
              } catch (error) {
                const message = toErrorMessage(error);
                setErrorMessage(message);
                notifier.error("添加 Watchlist 失败", message);
              }
            }}
            onDelete={async (id) => {
              try {
                await api.deleteWatchlistItem(id);
                await queryClient.invalidateQueries({ queryKey: ["watchlist"] });
                await queryClient.invalidateQueries({ queryKey: ["dashboard-snapshot"] });
                notifier.success("Watchlist 已删除");
              } catch (error) {
                const message = toErrorMessage(error);
                setErrorMessage(message);
                notifier.error("删除 Watchlist 失败", message);
              }
            }}
          />
        </TabsContent>

        <TabsContent value="terminal" className="mt-0">
          <StockTerminalPage
            defaultProvider={configDraft.analysis.default_provider}
            defaultModel={configDraft.analysis.default_model}
            intervals={options.intervals}
            watchlistItems={watchlistQuery.data ?? []}
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
              try {
                await api.runNewsListener();
                await queryClient.invalidateQueries({ queryKey: ["news-alerts"] });
                await queryClient.invalidateQueries({ queryKey: ["news-listener-runs"] });
                notifier.success("监听任务已执行");
              } catch (error) {
                const message = toErrorMessage(error);
                setErrorMessage(message);
                notifier.error("执行新闻监听失败", message);
              }
            }}
            onMarkAllRead={async () => {
              try {
                await api.markAllNewsAlertsRead();
                await queryClient.invalidateQueries({ queryKey: ["news-alerts"] });
                notifier.success("已全部标记为已读");
              } catch (error) {
                const message = toErrorMessage(error);
                setErrorMessage(message);
                notifier.error("批量已读失败", message);
              }
            }}
            onMarkAlert={async (id, status) => {
              try {
                await api.updateNewsAlert(id, status);
                await queryClient.invalidateQueries({ queryKey: ["news-alerts"] });
              } catch (error) {
                const message = toErrorMessage(error);
                setErrorMessage(message);
                notifier.error("更新告警状态失败", message);
              }
            }}
            onRefresh={async () => {
              try {
                await alertsQuery.refetch();
                await listenerRunsQuery.refetch();
              } catch (error) {
                const message = toErrorMessage(error);
                setErrorMessage(message);
                notifier.error("刷新告警失败", message);
              }
            }}
          />
        </TabsContent>

        <TabsContent value="reports" className="mt-0">
          <ReportsPage
            reports={sortedReports}
            tasks={reportTasksQuery.data ?? []}
            selectedRunId={selectedRunId}
            detail={detailQuery.data ?? null}
            onSelect={(runId) => setSelectedRunId(runId)}
            onDelete={async (runId) => {
              try {
                if (!window.confirm(`确认删除报告 ${runId} ?`)) {
                  return;
                }
                const payload = await api.deleteReport(runId);
                if (!payload.deleted) {
                  notifier.warning("报告不存在或已删除", runId);
                  return;
                }
                await queryClient.invalidateQueries({ queryKey: ["reports"] });
                if (selectedRunId === runId) {
                  setSelectedRunId("");
                }
                notifier.success("报告已删除", runId);
              } catch (error) {
                const message = toErrorMessage(error);
                setErrorMessage(message);
                notifier.error("删除报告失败", message);
              }
            }}
          />
        </TabsContent>
      </Tabs>
    </main>
  );
}
