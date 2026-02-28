import { z } from "zod";

import {
  appConfigSchema,
  analysisProviderViewSchema,
  dashboardAutoRefreshSchema,
  dashboardIndicesSnapshotSchema,
  dashboardSnapshotSchema,
  dashboardWatchlistSnapshotSchema,
  klineSchema,
  curvePointSchema,
  newsFeedResponseSchema,
  newsFeedSourceOptionSchema,
  newsSourceSchema,
  providerAuthStartSchema,
  providerAuthStatusSchema,
  providerModelsSchema,
  quoteSchema,
  reportDetailSchema,
  reportSummarySchema,
  reportTaskSchema,
  stockSearchResultSchema,
  telegramConfigSchema,
  uiOptionsSchema,
  watchlistItemSchema,
  loginRequestSchema,
  loginResponseSchema,
  refreshRequestSchema,
  currentUserSchema,
  userViewSchema,
  createUserRequestSchema,
  updateUserRequestSchema,
  changePasswordRequestSchema,
  resetPasswordRequestSchema,
} from "./schemas";

// Re-export all types and schemas so existing `import { ... } from "@/api/client"`
// statements continue to work without changes.
export * from "./schemas";

// ---------------------------------------------------------------------------
// Auth token management
// ---------------------------------------------------------------------------

const TOKEN_KEY = "market_reporter_token";
const REFRESH_TOKEN_KEY = "market_reporter_refresh_token";

export function getStoredToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function getStoredRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setTokens(accessToken: string, refreshToken: string): void {
  localStorage.setItem(TOKEN_KEY, accessToken);
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
}

export function clearTokens(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

export function isAuthenticated(): boolean {
  return !!getStoredToken();
}

// ---------------------------------------------------------------------------
// HTTP helpers
// ---------------------------------------------------------------------------

const apiBase = import.meta.env.VITE_API_BASE_URL ?? "/api";

async function request<S extends z.ZodTypeAny>(path: string, schema: S, init?: RequestInit): Promise<z.output<S>> {
  const token = getStoredToken();
  const headers: HeadersInit = {
    ...init?.headers,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    headers,
  });

  if (response.status === 401) {
    const refreshToken = getStoredRefreshToken();
    if (refreshToken && path !== "/auth/refresh") {
      try {
        const refreshResponse = await fetch(`${apiBase}/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (refreshResponse.ok) {
          const data = await refreshResponse.json();
          setTokens(data.access_token, data.refresh_token);
          const retryResponse = await fetch(`${apiBase}${path}`, {
            ...init,
            headers: {
              ...init?.headers,
              Authorization: `Bearer ${data.access_token}`,
            },
          });
          if (!retryResponse.ok) {
            throw new Error(`HTTP ${retryResponse.status}: ${await retryResponse.text()}`);
          }
          const payload = await retryResponse.json();
          return schema.parse(payload);
        }
      } catch {
        clearTokens();
        window.location.href = "/";
      }
    }
    clearTokens();
    window.location.href = "/";
  }

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${await response.text()}`);
  }
  const payload = await response.json();
  return schema.parse(payload);
}

async function requestVoid(path: string, init?: RequestInit): Promise<void> {
  const token = getStoredToken();
  const response = await fetch(`${apiBase}${path}`, {
    ...init,
    headers: {
      ...init?.headers,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${await response.text()}`);
  }
}

// ---------------------------------------------------------------------------
// API functions
// ---------------------------------------------------------------------------

export const api = {
  // ---- auth ----
  login: async (username: string, password: string) => {
    const response = await fetch(`${apiBase}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${await response.text()}`);
    }
    const payload = await response.json();
    const data = loginResponseSchema.parse(payload);
    setTokens(data.access_token, data.refresh_token);
    return data;
  },
  logout: () => {
    clearTokens();
    return Promise.resolve();
  },
  getMe: () => request("/auth/me", userViewSchema),
  refreshToken: () => {
    const refreshToken = getStoredRefreshToken();
    if (!refreshToken) return Promise.reject("No refresh token");
    return request("/auth/refresh", loginResponseSchema, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
  },

  // ---- users ----
  listUsers: () => request("/users", z.array(userViewSchema)),
  createUser: (payload: z.infer<typeof createUserRequestSchema>) =>
    request("/users", userViewSchema, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  getUser: (userId: number) => request(`/users/${userId}`, userViewSchema),
  updateUser: (userId: number, payload: z.infer<typeof updateUserRequestSchema>) =>
    request(`/users/${userId}`, userViewSchema, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  deleteUser: (userId: number) =>
    request(`/users/${userId}`, z.object({ deleted: z.boolean() }), { method: "DELETE" }),
  changePassword: (payload: z.infer<typeof changePasswordRequestSchema>) =>
    request("/users/me/password", z.object({ message: z.string() }), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  resetPassword: (userId: number, payload: z.infer<typeof resetPasswordRequestSchema>) =>
    request(`/users/${userId}/reset-password`, z.object({ message: z.string() }), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  // ---- config ----
  getConfig: () => request("/config", appConfigSchema),
  updateConfig: (payload: Record<string, unknown>) =>
    request("/config", appConfigSchema, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  getUiOptions: () => request("/options/ui", uiOptionsSchema),

  // ---- longbridge ----
  updateLongbridgeToken: (payload: { app_key: string; app_secret: string; access_token: string }) =>
    request("/longbridge/token", z.object({ ok: z.boolean() }), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  deleteLongbridgeToken: () =>
    request("/longbridge/token", z.object({ ok: z.boolean() }), {
      method: "DELETE",
    }),
  getTelegramConfig: () => request("/telegram", telegramConfigSchema),
  updateTelegramConfig: (payload: {
    enabled: boolean;
    chat_id: string;
    bot_token: string;
    timeout_seconds: number;
  }) =>
    request("/telegram", z.object({ ok: z.boolean() }), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  deleteTelegramConfig: () =>
    request("/telegram", z.object({ ok: z.boolean() }), {
      method: "DELETE",
    }),

  getDashboardSnapshot: (page = 1, pageSize = 10, enabledOnly = true) =>
    request(
      `/dashboard/snapshot?page=${page}&page_size=${pageSize}&enabled_only=${enabledOnly ? "true" : "false"}`,
      dashboardSnapshotSchema
    ),
  getDashboardIndicesSnapshot: (enabledOnly = true) =>
    request(
      `/dashboard/indices?enabled_only=${enabledOnly ? "true" : "false"}`,
      dashboardIndicesSnapshotSchema
    ),
  getDashboardWatchlistSnapshot: (page = 1, pageSize = 10, enabledOnly = true) =>
    request(
      `/dashboard/watchlist?page=${page}&page_size=${pageSize}&enabled_only=${enabledOnly ? "true" : "false"}`,
      dashboardWatchlistSnapshotSchema
    ),
  updateDashboardAutoRefresh: (enabled: boolean) =>
    request("/dashboard/auto-refresh", dashboardAutoRefreshSchema, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ auto_refresh_enabled: enabled }),
    }),

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
  getQuotesBatch: (items: Array<{ symbol: string; market: "CN" | "HK" | "US" }>) =>
    request("/stocks/quotes", z.array(quoteSchema), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items }),
    }),
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
