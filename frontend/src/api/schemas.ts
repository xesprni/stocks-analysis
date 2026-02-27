import { z } from "zod";

// ---------------------------------------------------------------------------
// Zod schemas
// ---------------------------------------------------------------------------

export const newsSourceSchema = z.object({
  source_id: z.string(),
  name: z.string(),
  category: z.string(),
  url: z.string(),
  enabled: z.boolean(),
});

export const analysisProviderConfigSchema = z.object({
  provider_id: z.string(),
  type: z.string(),
  base_url: z.string(),
  models: z.array(z.string()),
  timeout: z.number(),
  enabled: z.boolean(),
  auth_mode: z.string().nullable().optional(),
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
  dashboard: z.object({
    indices: z.array(
      z.object({
        symbol: z.string(),
        market: z.string(),
        alias: z.string().nullable().optional(),
        enabled: z.boolean().default(true),
      })
    ),
    auto_refresh_enabled: z.boolean(),
    auto_refresh_seconds: z.number(),
  }),
  agent: z.object({
    enabled: z.boolean(),
    max_steps: z.number(),
    max_tool_calls: z.number(),
    consistency_tolerance: z.number(),
    default_news_window_days: z.number(),
    default_filing_window_days: z.number(),
    default_price_window_days: z.number(),
  }),
  longbridge: z.object({
    enabled: z.boolean(),
    app_key: z.string(),
    app_secret: z.string(),
    access_token: z.string(),
  }),
  telegram: z.object({
    enabled: z.boolean(),
    chat_id: z.string(),
    bot_token: z.string(),
    timeout_seconds: z.number(),
  }),
  database: z.object({ url: z.string() }),
});

export const telegramConfigSchema = z.object({
  enabled: z.boolean(),
  chat_id: z.string(),
  bot_token: z.string(),
  timeout_seconds: z.number(),
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

export const paginationSchema = z.object({
  page: z.number(),
  page_size: z.number(),
  total: z.number(),
  total_pages: z.number(),
});

export const dashboardIndexMetricSchema = z.object({
  symbol: z.string(),
  market: z.string(),
  alias: z.string().nullable().optional(),
  ts: z.string(),
  price: z.number(),
  change: z.number().nullable().optional(),
  change_percent: z.number().nullable().optional(),
  volume: z.number().nullable().optional(),
  currency: z.string(),
  source: z.string(),
});

export const dashboardWatchlistMetricSchema = z.object({
  id: z.number(),
  symbol: z.string(),
  market: z.string(),
  alias: z.string().nullable().optional(),
  display_name: z.string().nullable().optional(),
  enabled: z.boolean(),
  ts: z.string(),
  price: z.number(),
  change: z.number().nullable().optional(),
  change_percent: z.number().nullable().optional(),
  volume: z.number().nullable().optional(),
  currency: z.string(),
  source: z.string(),
});

export const dashboardSnapshotSchema = z.object({
  generated_at: z.string(),
  auto_refresh_enabled: z.boolean(),
  auto_refresh_seconds: z.number(),
  indices: z.array(dashboardIndexMetricSchema),
  watchlist: z.array(dashboardWatchlistMetricSchema),
  pagination: paginationSchema,
});

export const dashboardIndicesSnapshotSchema = z.object({
  generated_at: z.string(),
  auto_refresh_enabled: z.boolean(),
  auto_refresh_seconds: z.number(),
  indices: z.array(dashboardIndexMetricSchema),
});

export const dashboardWatchlistSnapshotSchema = z.object({
  generated_at: z.string(),
  auto_refresh_enabled: z.boolean(),
  auto_refresh_seconds: z.number(),
  watchlist: z.array(dashboardWatchlistMetricSchema),
  pagination: paginationSchema,
});

export const dashboardAutoRefreshSchema = z.object({
  auto_refresh_enabled: z.boolean(),
  auto_refresh_seconds: z.number(),
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
  confidence: z.number().nullable().optional(),
  sentiment: z.string().nullable().optional(),
  mode: z.string().nullable().optional(),
});

export const reportDetailSchema = z.object({
  summary: reportSummarySchema,
  report_markdown: z.string(),
  raw_data: z.record(z.any()),
});

export const reportTaskSchema = z.object({
  task_id: z.string(),
  status: z.enum(["PENDING", "RUNNING", "SUCCEEDED", "FAILED"]),
  created_at: z.string(),
  started_at: z.string().nullable().optional(),
  finished_at: z.string().nullable().optional(),
  error_message: z.string().nullable().optional(),
  result: z
    .object({
      summary: reportSummarySchema,
      warnings: z.array(z.string()),
    })
    .nullable()
    .optional(),
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

export const stockAnalysisTaskSchema = z.object({
  task_id: z.string(),
  symbol: z.string(),
  market: z.string(),
  status: z.enum(["PENDING", "RUNNING", "SUCCEEDED", "FAILED"]),
  created_at: z.string(),
  started_at: z.string().nullable().optional(),
  finished_at: z.string().nullable().optional(),
  error_message: z.string().nullable().optional(),
  result: stockAnalysisRunSchema.nullable().optional(),
});

export const stockAnalysisHistoryItemSchema = z.object({
  id: z.number(),
  symbol: z.string(),
  market: z.string(),
  provider_id: z.string(),
  model: z.string(),
  status: z.string(),
  created_at: z.string(),
  markdown: z.string(),
  output_json: z.record(z.any()),
});

// ---------------------------------------------------------------------------
// Inferred TypeScript types
// ---------------------------------------------------------------------------

export type AppConfig = z.infer<typeof appConfigSchema>;
export type AnalysisProviderConfig = z.infer<typeof analysisProviderConfigSchema>;
export type NewsSource = z.infer<typeof newsSourceSchema>;
export type WatchlistItem = z.infer<typeof watchlistItemSchema>;
export type Quote = z.infer<typeof quoteSchema>;
export type KLineBar = z.infer<typeof klineSchema>;
export type CurvePoint = z.infer<typeof curvePointSchema>;
export type Pagination = z.infer<typeof paginationSchema>;
export type DashboardIndexMetric = z.infer<typeof dashboardIndexMetricSchema>;
export type DashboardWatchlistMetric = z.infer<typeof dashboardWatchlistMetricSchema>;
export type DashboardSnapshot = z.infer<typeof dashboardSnapshotSchema>;
export type DashboardIndicesSnapshot = z.infer<typeof dashboardIndicesSnapshotSchema>;
export type DashboardWatchlistSnapshot = z.infer<typeof dashboardWatchlistSnapshotSchema>;
export type DashboardAutoRefresh = z.infer<typeof dashboardAutoRefreshSchema>;
export type AnalysisProviderView = z.infer<typeof analysisProviderViewSchema>;
export type ReportSummary = z.infer<typeof reportSummarySchema>;
export type ReportDetail = z.infer<typeof reportDetailSchema>;
export type ReportTask = z.infer<typeof reportTaskSchema>;
export type StockAnalysisRun = z.infer<typeof stockAnalysisRunSchema>;
export type StockAnalysisTask = z.infer<typeof stockAnalysisTaskSchema>;
export type StockAnalysisHistoryItem = z.infer<typeof stockAnalysisHistoryItemSchema>;
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
export type TelegramConfig = z.infer<typeof telegramConfigSchema>;
