import { z } from "zod";

import {
  appConfigSchema,
  analysisProviderViewSchema,
  klineSchema,
  curvePointSchema,
  newsAlertSchema,
  newsFeedResponseSchema,
  newsFeedSourceOptionSchema,
  newsListenerRunSchema,
  newsSourceSchema,
  providerAuthStartSchema,
  providerAuthStatusSchema,
  providerModelsSchema,
  quoteSchema,
  reportDetailSchema,
  reportSummarySchema,
  reportTaskSchema,
  stockAnalysisRunSchema,
  stockAnalysisTaskSchema,
  stockSearchResultSchema,
  uiOptionsSchema,
  watchlistItemSchema,
} from "./schemas";

// Re-export all types and schemas so existing `import { ... } from "@/api/client"`
// statements continue to work without changes.
export * from "./schemas";

// ---------------------------------------------------------------------------
// HTTP helpers
// ---------------------------------------------------------------------------

const apiBase = import.meta.env.VITE_API_BASE_URL ?? "/api";

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

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export const api = {
  // ---- config ----
  getConfig: () => request("/config", appConfigSchema),
  updateConfig: (payload: Record<string, unknown>) =>
    request("/config", appConfigSchema, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  getUiOptions: () => request("/options/ui", uiOptionsSchema),

  // ---- reports ----
  listReports: () => request("/reports", z.array(reportSummarySchema)),
  getReport: (runId: string) => request(`/reports/${runId}`, reportDetailSchema),
  deleteReport: (runId: string) =>
    request(`/reports/${encodeURIComponent(runId)}`, z.object({ deleted: z.boolean() }), {
      method: "DELETE",
    }),
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
  runReportAsync: (payload: Record<string, unknown>) =>
    request("/reports/run/async", reportTaskSchema, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  getReportTask: (taskId: string) =>
    request(`/reports/tasks/${encodeURIComponent(taskId)}`, reportTaskSchema),
  listReportTasks: () => request("/reports/tasks", z.array(reportTaskSchema)),

  // ---- watchlist ----
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

  // ---- stocks ----
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

  // ---- providers ----
  listAnalysisProviders: () => request("/providers/analysis", z.array(analysisProviderViewSchema)),
  deleteAnalysisProvider: (providerId: string) =>
    request(`/providers/analysis/${encodeURIComponent(providerId)}`, appConfigSchema, {
      method: "DELETE",
    }),
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

  // ---- stock analysis ----
  runStockAnalysis: (symbol: string, payload: Record<string, unknown>) =>
    request(`/analysis/stocks/${encodeURIComponent(symbol)}/run`, stockAnalysisRunSchema, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  runStockAnalysisAsync: (symbol: string, payload: Record<string, unknown>) =>
    request(`/analysis/stocks/${encodeURIComponent(symbol)}/run/async`, stockAnalysisTaskSchema, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  getStockAnalysisTask: (taskId: string) =>
    request(`/analysis/stocks/tasks/${encodeURIComponent(taskId)}`, stockAnalysisTaskSchema),
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

  // ---- news listener ----
  runNewsListener: () => request("/news-listener/run", newsListenerRunSchema, { method: "POST" }),
  listNewsListenerRuns: (limit = 50) =>
    request(`/news-listener/runs?limit=${limit}`, z.array(newsListenerRunSchema)),

  // ---- news alerts ----
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

  // ---- news sources ----
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

  // ---- news feed ----
  listNewsFeedOptions: () => request("/news-feed/options", z.array(newsFeedSourceOptionSchema)),
  listNewsFeed: (sourceId = "ALL", limit = 50) =>
    request(`/news-feed?source_id=${encodeURIComponent(sourceId)}&limit=${limit}`, newsFeedResponseSchema),
};
