import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BellRing,
  ChartCandlestick,
  ClipboardList,
  LayoutDashboard,
  ListChecks,
  Newspaper,
  Settings2,
} from "lucide-react";

import { api, type AppConfig, type ReportSummary, type UIOptions } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { useNotifier } from "@/components/ui/notifier";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { AlertCenterPage } from "@/pages/AlertCenter";
import { DashboardPage } from "@/pages/Dashboard";
import { NewsFeedPage } from "@/pages/NewsFeed";
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
  const queryErrorCache = useRef<Record<string, string>>({});

  const configQuery = useQuery({ queryKey: ["config"], queryFn: api.getConfig });
  const uiOptionsQuery = useQuery({ queryKey: ["ui-options"], queryFn: api.getUiOptions });
  const reportsQuery = useQuery({ queryKey: ["reports"], queryFn: api.listReports });
  const watchlistQuery = useQuery({ queryKey: ["watchlist"], queryFn: api.listWatchlist });
  const newsSourcesQuery = useQuery({ queryKey: ["news-sources"], queryFn: api.listNewsSources });
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
    [notifier]
  );

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

  useEffect(() => {
    if (configQuery.data) {
      setConfigDraft(configQuery.data);
    }
  }, [configQuery.data]);

  const saveConfigMutation = useMutation({
    mutationFn: async () =>
      api.updateConfig({
        ...configDraft,
        news_sources: newsSourcesQuery.data ?? configDraft.news_sources,
      }),
    onSuccess: async (nextConfig) => {
      setConfigDraft(nextConfig);
      await queryClient.invalidateQueries({ queryKey: ["config"] });
      setErrorMessage("");
      notifier.success("配置已保存");
    },
    onError: (error) => {
      const message = toErrorMessage(error);
      setErrorMessage(message);
      notifier.error("保存配置失败", message);
    },
  });

  const runReportMutation = useMutation({
    mutationFn: async () => {
      const task = await api.runReportAsync({
        news_limit: configDraft.news_limit,
        flow_periods: configDraft.flow_periods,
        timezone: configDraft.timezone,
        provider_id: configDraft.analysis.default_provider,
        model: configDraft.analysis.default_model,
      });

      const deadline = Date.now() + 15 * 60 * 1000;
      while (Date.now() < deadline) {
        const snapshot = await api.getReportTask(task.task_id);
        if (snapshot.status === "SUCCEEDED") {
          if (snapshot.result) {
            return snapshot.result;
          }
          throw new Error("报告任务已完成，但结果为空。");
        }
        if (snapshot.status === "FAILED") {
          throw new Error(snapshot.error_message || "报告任务失败。");
        }
        await new Promise<void>((resolve) => window.setTimeout(resolve, 2000));
      }
      throw new Error("报告任务执行超时，请稍后在 Reports 页面检查结果。");
    },
    onMutate: () => {
      notifier.info("报告任务已提交", "后台正在生成，请稍候。");
    },
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ["reports"] });
      setSelectedRunId(result.summary.run_id);
      setWarningMessage(result.warnings[0] || "");
      setErrorMessage("");
      if (result.warnings[0]) {
        notifier.warning("报告已生成（存在告警）", result.warnings[0]);
      } else {
        notifier.success("报告已生成");
      }
    },
    onError: (error) => {
      setWarningMessage("");
      const message = toErrorMessage(error);
      setErrorMessage(message);
      notifier.error("生成报告失败", message);
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
    { key: "news-feed", label: "News Feed", icon: Newspaper },
    { key: "watchlist", label: "Watchlist", icon: ListChecks },
    { key: "terminal", label: "Stock Terminal", icon: ChartCandlestick },
    { key: "alerts", label: "Alert Center", icon: BellRing },
    { key: "providers", label: "Providers", icon: Settings2 },
    { key: "reports", label: "Reports", icon: ClipboardList },
  ];

  const sleep = useCallback((ms: number) => new Promise<void>((resolve) => window.setTimeout(resolve, ms)), []);
  const loadAnalysisModels = useCallback(async (providerId: string) => {
    const payload = await api.listAnalysisProviderModels(providerId);
    return payload.models;
  }, []);

  const connectProviderAuth = useCallback(
    async (providerId: string) => {
      const preStatus = await api.getAnalysisProviderAuthStatus(providerId).catch(() => null);
      if (preStatus?.connected) {
        await queryClient.invalidateQueries({ queryKey: ["providers"] });
        notifier.success("Provider 已连接", providerId);
        return;
      }

      const started = await api.startAnalysisProviderAuth(providerId, {
        redirect_to: window.location.href,
      });
      const popup = window.open(started.auth_url, "_blank", "noopener,noreferrer,width=520,height=780");
      if (!popup) {
        notifier.warning("登录窗口被拦截", "请允许浏览器弹窗后重试。");
      } else {
        notifier.info("已打开登录窗口", "完成登录后会自动刷新状态。");
      }

      const deadline = Date.now() + 90_000;
      let connected = false;
      while (Date.now() < deadline) {
        await sleep(2000);
        const status = await api.getAnalysisProviderAuthStatus(providerId);
        if (status.connected) {
          connected = true;
          break;
        }
      }

      await queryClient.invalidateQueries({ queryKey: ["providers"] });
      if (connected) {
        const modelPayload = await api.listAnalysisProviderModels(providerId).catch(() => null);
        const modelHint =
          modelPayload && modelPayload.models.length
            ? `可用模型: ${modelPayload.models.slice(0, 3).join(", ")}`
            : "Provider 已连接";
        notifier.success("登录成功", modelHint);
      } else {
        notifier.warning("登录状态未确认", "请完成授权后点击 Connect 再次刷新。");
      }
    },
    [notifier, queryClient, sleep]
  );

  const disconnectProviderAuth = useCallback(
    async (providerId: string) => {
      await api.logoutAnalysisProviderAuth(providerId);
      await queryClient.invalidateQueries({ queryKey: ["providers"] });
      notifier.success("已断开 Provider 登录", providerId);
    },
    [notifier, queryClient]
  );

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
            analysisProviders={providersQuery.data ?? []}
            newsSources={newsSourcesQuery.data ?? configDraft.news_sources}
            onLoadProviderModels={loadAnalysisModels}
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
            setConfig={setConfigDraft}
            onSave={() => saveConfigMutation.mutate()}
            onReload={() => {
              void configQuery.refetch();
              void newsSourcesQuery.refetch();
              setErrorMessage("");
            }}
            onRunReport={() => runReportMutation.mutate()}
            saving={saveConfigMutation.isPending}
            running={runReportMutation.isPending}
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

        <TabsContent value="providers" className="mt-0">
          <ProvidersPage
            providers={providersQuery.data ?? []}
            providerConfigs={configDraft.analysis.providers}
            defaultProvider={configDraft.analysis.default_provider}
            defaultModel={configDraft.analysis.default_model}
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
          />
        </TabsContent>

        <TabsContent value="reports" className="mt-0">
          <ReportsPage
            reports={sortedReports}
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
