import { z } from "zod";

const apiBase = import.meta.env.VITE_API_BASE_URL ?? "/api";

const newsSourceSchema = z.object({
  source_id: z.string(),
  name: z.string(),
  category: z.string(),
  url: z.string(),
  enabled: z.boolean(),
});

const analysisProviderConfigSchema = z.object({
  provider_id: z.string(),
  type: z.string(),
  base_url: z.string(),
  models: z.array(z.string()),
  timeout: z.number(),
  enabled: z.boolean(),
  auth_mode: z.string().optional(),
  login_callback_url: z.string().nullable().optional(),
  login_timeout_seconds: z.number().optional(),
});

export const appConfigSchema = z.object({
  output_root: z.string(),
  config_file: z.string(),
  timezone: z.string(),
  news_limit: z.number(),
  flow_periods: z.number(),
  request_timeout_seconds: z.number(),
  user_agent: z.string(),
  modules: z.object({
    news: z.object({ default_provider: z.string() }),
    fund_flow: z.object({ providers: z.array(z.string()) }),
    market_data: z.object({ default_provider: z.string(), poll_seconds: z.number() }),
    news_listener: z.object({ default_provider: z.string() }),
    symbol_search: z.object({ default_provider: z.string() }),
  }),
  analysis: z.object({
    default_provider: z.string(),
    default_model: z.string(),
    providers: z.array(analysisProviderConfigSchema),
  }),
  watchlist: z.object({ default_market_scope: z.array(z.string()) }),
  news_listener: z.object({
    enabled: z.boolean(),
    interval_minutes: z.number(),
    move_window_minutes: z.number(),
    move_threshold_percent: z.number(),
    max_news_per_cycle: z.number(),
    analysis_provider: z.string().nullable().optional(),
    analysis_model: z.string().nullable().optional(),
  }),
  symbol_search: z.object({
    default_provider: z.string(),
    max_results: z.number(),
  }),
  database: z.object({ url: z.string() }),
  news_sources: z.array(newsSourceSchema),
});

export const watchlistItemSchema = z.object({
  id: z.number(),
  symbol: z.string(),
  market: z.string(),
  alias: z.string().nullable().optional(),
  display_name: z.string().nullable().optional(),
  keywords: z.array(z.string()).optional(),
  enabled: z.boolean(),
  created_at: z.string(),
  updated_at: z.string(),
});

export const stockSearchResultSchema = z.object({
  symbol: z.string(),
  market: z.string(),
  name: z.string(),
  exchange: z.string(),
  source: z.string(),
  score: z.number(),
});

export const newsListenerRunSchema = z.object({
  id: z.number(),
  started_at: z.string(),
  finished_at: z.string(),
  status: z.string(),
  scanned_news_count: z.number(),
  matched_news_count: z.number(),
  alerts_count: z.number(),
  error_message: z.string().nullable().optional(),
});

export const newsAlertSchema = z.object({
  id: z.number(),
  run_id: z.number(),
  symbol: z.string(),
  market: z.string(),
  news_title: z.string(),
  news_link: z.string(),
  news_source: z.string(),
  published_at: z.string(),
  move_window_minutes: z.number(),
  price_change_percent: z.number(),
  threshold_percent: z.number(),
  severity: z.string(),
  analysis_summary: z.string(),
  analysis_markdown: z.string(),
  analysis_json: z.record(z.any()),
  status: z.string(),
  created_at: z.string(),
});

export const uiOptionsSchema = z.object({
  markets: z.array(z.string()),
  intervals: z.array(z.string()),
  timezones: z.array(z.string()),
  news_providers: z.array(z.string()),
  fund_flow_providers: z.array(z.string()),
  market_data_providers: z.array(z.string()),
  analysis_providers: z.array(z.string()),
  analysis_models_by_provider: z.record(z.array(z.string())),
  listener_threshold_presets: z.array(z.number()),
  listener_intervals: z.array(z.number()),
});

export const newsFeedSourceOptionSchema = z.object({
  source_id: z.string(),
  name: z.string(),
  enabled: z.boolean(),
});

export const newsFeedItemSchema = z.object({
  source_id: z.string(),
  source_name: z.string(),
  category: z.string(),
  title: z.string(),
  link: z.string(),
  published: z.string(),
  fetched_at: z.string(),
});

export const newsFeedResponseSchema = z.object({
  items: z.array(newsFeedItemSchema),
  warnings: z.array(z.string()),
  selected_source_id: z.string(),
});

export const quoteSchema = z.object({
  symbol: z.string(),
  market: z.string(),
  ts: z.string(),
  price: z.number(),
  change: z.number().nullable().optional(),
  change_percent: z.number().nullable().optional(),
  volume: z.number().nullable().optional(),
  currency: z.string(),
  source: z.string(),
});

export const klineSchema = z.object({
  symbol: z.string(),
  market: z.string(),
  interval: z.string(),
  ts: z.string(),
  open: z.number(),
  high: z.number(),
  low: z.number(),
  close: z.number(),
  volume: z.number().nullable().optional(),
  source: z.string(),
});

export const curvePointSchema = z.object({
  symbol: z.string(),
  market: z.string(),
  ts: z.string(),
  price: z.number(),
  volume: z.number().nullable().optional(),
  source: z.string(),
});

export const analysisProviderViewSchema = z.object({
  provider_id: z.string(),
  type: z.string(),
  base_url: z.string(),
  models: z.array(z.string()),
  timeout: z.number(),
  enabled: z.boolean(),
  has_secret: z.boolean(),
  secret_required: z.boolean(),
  ready: z.boolean(),
  status: z.string(),
  status_message: z.string(),
  is_default: z.boolean(),
  auth_mode: z.string().optional(),
  connected: z.boolean().optional(),
  credential_expires_at: z.string().nullable().optional(),
});

export const providerAuthStartSchema = z.object({
  provider_id: z.string(),
  auth_url: z.string(),
  state: z.string(),
  expires_at: z.string(),
});

export const providerAuthStatusSchema = z.object({
  provider_id: z.string(),
  auth_mode: z.string(),
  connected: z.boolean(),
  status: z.string(),
  message: z.string(),
  expires_at: z.string().nullable().optional(),
});

export const providerModelsSchema = z.object({
  provider_id: z.string(),
  models: z.array(z.string()),
  source: z.string(),
});

export const reportSummarySchema = z.object({
  run_id: z.string(),
  generated_at: z.string(),
  report_path: z.string(),
  raw_data_path: z.string(),
  warnings_count: z.number(),
  news_total: z.number(),
  provider_id: z.string(),
  model: z.string(),
});

export const reportDetailSchema = z.object({
  summary: reportSummarySchema,
  report_markdown: z.string(),
  raw_data: z.record(z.any()),
});

export const stockAnalysisRunSchema = z.object({
  id: z.number(),
  symbol: z.string(),
  market: z.string(),
  provider_id: z.string(),
  model: z.string(),
  status: z.string(),
  output: z.object({
    summary: z.string(),
    sentiment: z.string(),
    key_levels: z.array(z.string()),
    risks: z.array(z.string()),
    action_items: z.array(z.string()),
    confidence: z.number(),
    markdown: z.string(),
    raw: z.record(z.any()),
  }),
  markdown: z.string(),
  created_at: z.string(),
});

export type AppConfig = z.infer<typeof appConfigSchema>;
export type AnalysisProviderConfig = z.infer<typeof analysisProviderConfigSchema>;
export type NewsSource = z.infer<typeof newsSourceSchema>;
export type WatchlistItem = z.infer<typeof watchlistItemSchema>;
export type Quote = z.infer<typeof quoteSchema>;
export type KLineBar = z.infer<typeof klineSchema>;
export type CurvePoint = z.infer<typeof curvePointSchema>;
export type AnalysisProviderView = z.infer<typeof analysisProviderViewSchema>;
export type ReportSummary = z.infer<typeof reportSummarySchema>;
export type ReportDetail = z.infer<typeof reportDetailSchema>;
export type StockAnalysisRun = z.infer<typeof stockAnalysisRunSchema>;
export type StockSearchResult = z.infer<typeof stockSearchResultSchema>;
export type NewsListenerRun = z.infer<typeof newsListenerRunSchema>;
export type NewsAlert = z.infer<typeof newsAlertSchema>;
export type UIOptions = z.infer<typeof uiOptionsSchema>;
export type NewsFeedSourceOption = z.infer<typeof newsFeedSourceOptionSchema>;
export type NewsFeedItem = z.infer<typeof newsFeedItemSchema>;
export type NewsFeedResponse = z.infer<typeof newsFeedResponseSchema>;
export type ProviderAuthStart = z.infer<typeof providerAuthStartSchema>;
export type ProviderAuthStatus = z.infer<typeof providerAuthStatusSchema>;
export type ProviderModels = z.infer<typeof providerModelsSchema>;

async function request<T>(path: string, schema: z.ZodSchema<T>, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBase}${path}`, init);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${await response.text()}`);
  }
  const payload = await response.json();
  return schema.parse(payload);
}

async function requestVoid(path: string, init?: RequestInit): Promise<void> {
  const response = await fetch(`${apiBase}${path}`, init);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${await response.text()}`);
  }
}

export const api = {
  getConfig: () => request("/config", appConfigSchema),
  updateConfig: (payload: Record<string, unknown>) =>
    request("/config", appConfigSchema, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  listReports: () => request("/reports", z.array(reportSummarySchema)),
  getReport: (runId: string) => request(`/reports/${runId}`, reportDetailSchema),
  runReport: (payload: Record<string, unknown>) =>
    request(
      "/reports/run",
      z.object({ summary: reportSummarySchema, warnings: z.array(z.string()) }),
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }
    ),
  listWatchlist: () => request("/watchlist", z.array(watchlistItemSchema)),
  createWatchlistItem: (payload: Record<string, unknown>) =>
    request("/watchlist", watchlistItemSchema, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  updateWatchlistItem: (id: number, payload: Record<string, unknown>) =>
    request(`/watchlist/${id}`, watchlistItemSchema, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  deleteWatchlistItem: (id: number) => requestVoid(`/watchlist/${id}`, { method: "DELETE" }),
  getQuote: (symbol: string, market: string) =>
    request(`/stocks/${encodeURIComponent(symbol)}/quote?market=${market}`, quoteSchema),
  getKline: (symbol: string, market: string, interval: string, limit = 300) =>
    request(
      `/stocks/${encodeURIComponent(symbol)}/kline?market=${market}&interval=${interval}&limit=${limit}`,
      z.array(klineSchema)
    ),
  getCurve: (symbol: string, market: string, window = "1d") =>
    request(`/stocks/${encodeURIComponent(symbol)}/curve?market=${market}&window=${window}`, z.array(curvePointSchema)),
  searchStocks: (q: string, market = "ALL", limit = 20) =>
    request(
      `/stocks/search?q=${encodeURIComponent(q)}&market=${market}&limit=${limit}`,
      z.array(stockSearchResultSchema)
    ),
  listAnalysisProviders: () => request("/providers/analysis", z.array(analysisProviderViewSchema)),
  updateDefaultAnalysis: (payload: Record<string, unknown>) =>
    request("/providers/analysis/default", appConfigSchema, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  putAnalysisSecret: (providerId: string, payload: Record<string, unknown>) =>
    request(`/providers/analysis/${providerId}/secret`, z.object({ ok: z.boolean() }), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  deleteAnalysisSecret: (providerId: string) =>
    request(`/providers/analysis/${providerId}/secret`, z.object({ deleted: z.boolean() }), {
      method: "DELETE",
    }),
  startAnalysisProviderAuth: (providerId: string, payload?: Record<string, unknown>) =>
    request(`/providers/analysis/${providerId}/auth/start`, providerAuthStartSchema, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload ?? {}),
    }),
  getAnalysisProviderAuthStatus: (providerId: string) =>
    request(`/providers/analysis/${providerId}/auth/status`, providerAuthStatusSchema),
  logoutAnalysisProviderAuth: (providerId: string) =>
    request(`/providers/analysis/${providerId}/auth/logout`, z.object({ deleted: z.boolean() }), {
      method: "POST",
    }),
  listAnalysisProviderModels: (providerId: string) =>
    request(`/providers/analysis/${providerId}/models`, providerModelsSchema),
  runStockAnalysis: (symbol: string, payload: Record<string, unknown>) =>
    request(`/analysis/stocks/${encodeURIComponent(symbol)}/run`, stockAnalysisRunSchema, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  listStockAnalysisHistory: (symbol: string, market: string, limit = 20) =>
    request(
      `/analysis/stocks/${encodeURIComponent(symbol)}/history?market=${market}&limit=${limit}`,
      z.array(
        z.object({
          id: z.number(),
          symbol: z.string(),
          market: z.string(),
          provider_id: z.string(),
          model: z.string(),
          status: z.string(),
          created_at: z.string(),
          markdown: z.string(),
          output_json: z.record(z.any()),
        })
      )
    ),
  runNewsListener: () => request("/news-listener/run", newsListenerRunSchema, { method: "POST" }),
  listNewsListenerRuns: (limit = 50) =>
    request(`/news-listener/runs?limit=${limit}`, z.array(newsListenerRunSchema)),
  listNewsAlerts: (params: { status?: string; symbol?: string; market?: string; limit?: number }) => {
    const search = new URLSearchParams({
      status: params.status ?? "UNREAD",
      symbol: params.symbol ?? "",
      market: params.market ?? "",
      limit: String(params.limit ?? 50),
    });
    return request(`/news-alerts?${search.toString()}`, z.array(newsAlertSchema));
  },
  updateNewsAlert: (alertId: number, status: "READ" | "DISMISSED") =>
    request(`/news-alerts/${alertId}`, newsAlertSchema, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    }),
  markAllNewsAlertsRead: () =>
    request("/news-alerts/mark-all-read", z.object({ updated: z.number() }), {
      method: "POST",
    }),
  listNewsSources: () => request("/news-sources", z.array(newsSourceSchema)),
  createNewsSource: (payload: Record<string, unknown>) =>
    request("/news-sources", newsSourceSchema, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  updateNewsSource: (sourceId: string, payload: Record<string, unknown>) =>
    request(`/news-sources/${encodeURIComponent(sourceId)}`, newsSourceSchema, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  deleteNewsSource: (sourceId: string) =>
    request(`/news-sources/${encodeURIComponent(sourceId)}`, z.object({ deleted: z.boolean() }), {
      method: "DELETE",
    }),
  listNewsFeedOptions: () => request("/news-feed/options", z.array(newsFeedSourceOptionSchema)),
  listNewsFeed: (sourceId = "ALL", limit = 50) =>
    request(`/news-feed?source_id=${encodeURIComponent(sourceId)}&limit=${limit}`, newsFeedResponseSchema),
  getUiOptions: () => request("/options/ui", uiOptionsSchema),
};
