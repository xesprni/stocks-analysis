import { useEffect, useMemo, useState } from "react";
import { Plus, RefreshCw, Save, Settings2, Trash2 } from "lucide-react";

import type { AnalysisProviderConfig, AnalysisProviderView, AppConfig, NewsSource, UIOptions } from "@/api/client";
import { ProvidersPage } from "@/pages/Providers";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

type Props = {
  config: AppConfig;
  options: UIOptions;
  analysisProviders: AnalysisProviderView[];
  providerConfigs: AnalysisProviderConfig[];
  newsSources: NewsSource[];
  onCreateNewsSource: (payload: { name: string; category: string; url: string; enabled: boolean }) => Promise<void>;
  onUpdateNewsSource: (
    sourceId: string,
    payload: Partial<{ name: string; category: string; url: string; enabled: boolean }>
  ) => Promise<void>;
  onDeleteNewsSource: (sourceId: string) => Promise<void>;
  onSetDefault: (providerId: string, model: string) => Promise<void>;
  onSaveSecret: (providerId: string, apiKey: string) => Promise<void>;
  onConnectAuth: (providerId: string) => Promise<void>;
  onDisconnectAuth: (providerId: string) => Promise<void>;
  onLoadModels: (providerId: string) => Promise<string[]>;
  onDeleteProvider: (providerId: string) => Promise<void>;
  onSaveProviderConfig: (
    providerId: string,
    patch: Partial<{
      enabled: boolean;
      base_url: string;
      timeout: number;
      models: string[];
      login_callback_url: string | null;
      login_timeout_seconds: number;
    }>
  ) => Promise<void>;
  setConfig: (value: AppConfig) => void;
  onSaveBasic: () => void;
  onSaveModuleDefaults: () => void;
  onSaveDashboard: () => void;
  onSaveLongbridgeToken: (payload: { app_key: string; app_secret: string; access_token: string }) => Promise<void>;
  onDeleteLongbridgeToken: () => Promise<void>;
  onReload: () => void;
  savingSection: "basic" | "module_defaults" | "dashboard" | null;
};

type SourceRow = {
  source_id: string;
  name: string;
  category: string;
  url: string;
  enabled: boolean;
};

type DashboardIndex = AppConfig["dashboard"]["indices"][number];

export function ConfigPage({
  config,
  options,
  analysisProviders,
  providerConfigs,
  newsSources,
  onCreateNewsSource,
  onUpdateNewsSource,
  onDeleteNewsSource,
  onSetDefault,
  onSaveSecret,
  onConnectAuth,
  onDisconnectAuth,
  onLoadModels,
  onDeleteProvider,
  onSaveProviderConfig,
  setConfig,
  onSaveBasic,
  onSaveModuleDefaults,
  onSaveDashboard,
  onSaveLongbridgeToken,
  onDeleteLongbridgeToken,
  onReload,
  savingSection,
}: Props) {
  const [sourceRows, setSourceRows] = useState<SourceRow[]>([]);
  const [creatingSource, setCreatingSource] = useState(false);
  const [newSourceName, setNewSourceName] = useState("");
  const [newSourceCategory, setNewSourceCategory] = useState("finance");
  const [newSourceUrl, setNewSourceUrl] = useState("");
  const [newSourceEnabled, setNewSourceEnabled] = useState(true);

  const [lbAppKey, setLbAppKey] = useState("");
  const [lbAppSecret, setLbAppSecret] = useState("");
  const [lbAccessToken, setLbAccessToken] = useState("");
  const [lbSaving, setLbSaving] = useState(false);

  useEffect(() => {
    setLbAppKey(config.longbridge.app_key ?? "");
    setLbAppSecret(config.longbridge.app_secret === "***" ? "" : (config.longbridge.app_secret ?? ""));
    setLbAccessToken(config.longbridge.access_token === "***" ? "" : (config.longbridge.access_token ?? ""));
  }, [config.longbridge.app_key, config.longbridge.app_secret, config.longbridge.access_token]);

  useEffect(() => {
    setSourceRows(
      [...newsSources]
        .sort((a, b) => a.source_id.localeCompare(b.source_id))
        .map((item) => ({
          source_id: item.source_id,
          name: item.name,
          category: item.category,
          url: item.url,
          enabled: item.enabled,
        }))
    );
  }, [newsSources]);

  const dashboardIndices = useMemo(() => config.dashboard.indices ?? [], [config.dashboard.indices]);

  const updateDashboard = (patch: Partial<AppConfig["dashboard"]>) => {
    setConfig({
      ...config,
      dashboard: {
        ...config.dashboard,
        ...patch,
      },
    });
  };

  const updateIndexRow = (index: number, patch: Partial<DashboardIndex>) => {
    const nextIndices = dashboardIndices.map((row, idx) => (idx === index ? { ...row, ...patch } : row));
    updateDashboard({ indices: nextIndices });
  };

  const removeIndexRow = (index: number) => {
    const nextIndices = dashboardIndices.filter((_, idx) => idx !== index);
    updateDashboard({ indices: nextIndices });
  };

  const addIndexRow = () => {
    updateDashboard({
      indices: [...dashboardIndices, { symbol: "", market: "US", alias: "", enabled: true }],
    });
  };

  return (
    <div className="space-y-6">
      {/* Hero section */}
      <section className="relative overflow-hidden rounded-3xl border border-violet-300/50 bg-gradient-to-br from-violet-500/15 via-fuchsia-500/10 to-sky-400/15 p-6">
        <div className="pointer-events-none absolute -left-10 -top-14 h-40 w-40 rounded-full bg-violet-400/20 blur-3xl" />
        <div className="pointer-events-none absolute right-0 top-8 h-32 w-32 rounded-full bg-fuchsia-400/20 blur-2xl" />
        <div className="pointer-events-none absolute -bottom-10 right-8 h-40 w-40 rounded-full bg-sky-400/20 blur-3xl" />
        <div className="relative flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
              <Settings2 className="h-5 w-5 text-violet-600" />
              Config 系统配置
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              集中管理系统配置、指数配置、新闻源与分析 Provider 配置。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={onReload}>
              <RefreshCw className="mr-2 h-4 w-4" />
              重载
            </Button>
          </div>
        </div>
      </section>

      {/* Basic settings */}
      <Card className="border-sky-200/60 bg-gradient-to-br from-white to-sky-50/40 dark:from-slate-900 dark:to-sky-950/20">
        <CardHeader className="flex flex-row items-start justify-between gap-3">
          <div>
            <CardTitle className="text-base">基础配置</CardTitle>
            <CardDescription>输出目录、时区、超时、数据库等全局参数。</CardDescription>
          </div>
          <Button onClick={onSaveBasic} disabled={savingSection !== null && savingSection !== "basic"}>
            <Save className="mr-2 h-4 w-4" />
            {savingSection === "basic" ? "保存中..." : "保存基础配置"}
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="output_root">输出目录</Label>
              <Input
                id="output_root"
                value={config.output_root}
                onChange={(event) => setConfig({ ...config, output_root: event.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="timezone">时区</Label>
              <Select value={config.timezone} onValueChange={(value: string) => setConfig({ ...config, timezone: value })}>
                <SelectTrigger id="timezone">
                  <SelectValue placeholder="时区" />
                </SelectTrigger>
                <SelectContent>
                  {options.timezones.map((entry) => (
                    <SelectItem key={entry} value={entry}>
                      {entry}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="news_limit">新闻条数</Label>
              <Input
                id="news_limit"
                type="number"
                value={config.news_limit}
                onChange={(event) => setConfig({ ...config, news_limit: Number(event.target.value) })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="flow_periods">资金流周期</Label>
              <Input
                id="flow_periods"
                type="number"
                value={config.flow_periods}
                onChange={(event) => setConfig({ ...config, flow_periods: Number(event.target.value) })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="timeout">请求超时(秒)</Label>
              <Input
                id="timeout"
                type="number"
                value={config.request_timeout_seconds}
                onChange={(event) =>
                  setConfig({
                    ...config,
                    request_timeout_seconds: Number(event.target.value),
                  })
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="database_url">数据库 URL</Label>
              <Input
                id="database_url"
                value={config.database.url}
                onChange={(event) =>
                  setConfig({
                    ...config,
                    database: {
                      ...config.database,
                      url: event.target.value,
                    },
                  })
                }
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Provider defaults */}
      <Card className="border-emerald-200/60 bg-gradient-to-br from-white to-emerald-50/40 dark:from-slate-900 dark:to-emerald-950/20">
        <CardHeader className="flex flex-row items-start justify-between gap-3">
          <div>
            <CardTitle className="text-base">模块默认 Provider</CardTitle>
            <CardDescription>新闻、行情、搜索、监听等模块的默认服务提供方。</CardDescription>
          </div>
          <Button onClick={onSaveModuleDefaults} disabled={savingSection !== null && savingSection !== "module_defaults"}>
            <Save className="mr-2 h-4 w-4" />
            {savingSection === "module_defaults" ? "保存中..." : "保存模块默认配置"}
          </Button>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="news_provider">新闻默认 Provider</Label>
              <Select
                value={config.modules.news.default_provider}
                onValueChange={(value: string) =>
                  setConfig({
                    ...config,
                    modules: {
                      ...config.modules,
                      news: {
                        ...config.modules.news,
                        default_provider: value,
                      },
                    },
                  })
                }
              >
                <SelectTrigger id="news_provider">
                  <SelectValue placeholder="新闻 Provider" />
                </SelectTrigger>
                <SelectContent>
                  {options.news_providers.map((entry) => (
                    <SelectItem key={entry} value={entry}>
                      {entry}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="default_provider">行情默认 Provider</Label>
              <Select
                value={config.modules.market_data.default_provider}
                onValueChange={(value: string) =>
                  setConfig({
                    ...config,
                    modules: {
                      ...config.modules,
                      market_data: {
                        ...config.modules.market_data,
                        default_provider: value,
                      },
                    },
                  })
                }
              >
                <SelectTrigger id="default_provider">
                  <SelectValue placeholder="行情 Provider" />
                </SelectTrigger>
                <SelectContent>
                  {options.market_data_providers.map((entry) => (
                    <SelectItem key={entry} value={entry}>
                      {entry}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="symbol_search_provider">搜索默认 Provider</Label>
              <Select
                value={config.symbol_search.default_provider}
                onValueChange={(value: string) =>
                  setConfig({
                    ...config,
                    symbol_search: {
                      ...config.symbol_search,
                      default_provider: value,
                    },
                    modules: {
                      ...config.modules,
                      symbol_search: {
                        ...config.modules.symbol_search,
                        default_provider: value,
                      },
                    },
                  })
                }
              >
                <SelectTrigger id="symbol_search_provider">
                  <SelectValue placeholder="搜索 Provider" />
                </SelectTrigger>
                <SelectContent>
                  {["composite", "finnhub", "yfinance", "akshare", "longbridge"].map((entry) => (
                    <SelectItem key={entry} value={entry}>
                      {entry}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="symbol_search_max_results">搜索条数上限</Label>
              <Input
                id="symbol_search_max_results"
                type="number"
                min={5}
                max={100}
                value={config.symbol_search.max_results}
                onChange={(event) =>
                  setConfig({
                    ...config,
                    symbol_search: {
                      ...config.symbol_search,
                      max_results: Math.min(100, Math.max(5, Number(event.target.value || 20))),
                    },
                  })
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="listener_interval">监听频率(分钟)</Label>
              <Select
                value={String(config.news_listener.interval_minutes)}
                onValueChange={(value: string) =>
                  setConfig({
                    ...config,
                    news_listener: {
                      ...config.news_listener,
                      interval_minutes: Number(value),
                    },
                  })
                }
              >
                <SelectTrigger id="listener_interval">
                  <SelectValue placeholder="监听频率" />
                </SelectTrigger>
                <SelectContent>
                  {options.listener_intervals.map((entry) => (
                    <SelectItem key={entry} value={String(entry)}>
                      {entry}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="listener_threshold">异动阈值(%)</Label>
              <Select
                value={String(config.news_listener.move_threshold_percent)}
                onValueChange={(value: string) =>
                  setConfig({
                    ...config,
                    news_listener: {
                      ...config.news_listener,
                      move_threshold_percent: Number(value),
                    },
                  })
                }
              >
                <SelectTrigger id="listener_threshold">
                  <SelectValue placeholder="异动阈值" />
                </SelectTrigger>
                <SelectContent>
                  {options.listener_threshold_presets.map((entry) => (
                    <SelectItem key={entry} value={String(entry)}>
                      {entry}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Longbridge OpenAPI */}
      <Card className="border-indigo-200/60 bg-gradient-to-br from-white to-indigo-50/40 dark:from-slate-900 dark:to-indigo-950/20">
        <CardHeader className="flex flex-row items-start justify-between gap-3">
          <div>
            <CardTitle className="text-base">
              Longbridge OpenAPI
              {config.longbridge.enabled ? (
                <Badge className="ml-2 bg-emerald-100 text-emerald-700" variant="secondary">已启用</Badge>
              ) : (
                <Badge className="ml-2" variant="secondary">未启用</Badge>
              )}
            </CardTitle>
            <CardDescription>
              配置 Longbridge 行情数据源凭证。保存后自动启用，用于行情、K 线、分时、基本面等数据获取。
            </CardDescription>
          </div>
          <div className="flex gap-2">
            <Button
              variant="destructive"
              size="sm"
              disabled={!config.longbridge.enabled}
              onClick={async () => {
                setLbSaving(true);
                try {
                  await onDeleteLongbridgeToken();
                } finally {
                  setLbSaving(false);
                }
              }}
            >
              <Trash2 className="mr-1 h-3.5 w-3.5" />
              清除凭证
            </Button>
            <Button
              disabled={lbSaving || !lbAppKey.trim() || !lbAppSecret.trim() || !lbAccessToken.trim()}
              onClick={async () => {
                setLbSaving(true);
                try {
                  await onSaveLongbridgeToken({
                    app_key: lbAppKey.trim(),
                    app_secret: lbAppSecret.trim(),
                    access_token: lbAccessToken.trim(),
                  });
                } finally {
                  setLbSaving(false);
                }
              }}
            >
              <Save className="mr-2 h-4 w-4" />
              {lbSaving ? "保存中..." : "保存凭证"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="lb_app_key">App Key</Label>
              <Input
                id="lb_app_key"
                value={lbAppKey}
                placeholder="Longbridge App Key"
                onChange={(e) => setLbAppKey(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="lb_app_secret">App Secret</Label>
              <Input
                id="lb_app_secret"
                type="password"
                value={lbAppSecret}
                placeholder={config.longbridge.app_secret === "***" ? "已配置（留空不修改）" : "Longbridge App Secret"}
                onChange={(e) => setLbAppSecret(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="lb_access_token">Access Token</Label>
              <Input
                id="lb_access_token"
                type="password"
                value={lbAccessToken}
                placeholder={config.longbridge.access_token === "***" ? "已配置（留空不修改）" : "Longbridge Access Token"}
                onChange={(e) => setLbAccessToken(e.target.value)}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Dashboard index settings */}
      <Card className="border-amber-200/60 bg-gradient-to-br from-white to-amber-50/40 dark:from-slate-900 dark:to-amber-950/20">
        <CardHeader className="flex flex-row items-start justify-between gap-3">
          <div>
            <CardTitle className="text-base">Dashboard 指数配置</CardTitle>
            <CardDescription>配置监控页面的指数列表与自动刷新间隔（开关在 Dashboard 页面）。</CardDescription>
          </div>
          <Button onClick={onSaveDashboard} disabled={savingSection !== null && savingSection !== "dashboard"}>
            <Save className="mr-2 h-4 w-4" />
            {savingSection === "dashboard" ? "保存中..." : "保存 Dashboard 配置"}
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="dashboard_auto_refresh_seconds">自动刷新间隔(秒)</Label>
              <Input
                id="dashboard_auto_refresh_seconds"
                type="number"
                min={3}
                max={300}
                value={config.dashboard.auto_refresh_seconds}
                onChange={(event) =>
                  updateDashboard({
                    auto_refresh_seconds: Math.min(
                      300,
                      Math.max(3, Number(event.target.value || 15))
                    ),
                  })
                }
              />
            </div>
          </div>

          <div className="overflow-x-auto rounded-xl border border-border/60">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/30">
                  <TableHead>Alias</TableHead>
                  <TableHead>Symbol</TableHead>
                  <TableHead>Market</TableHead>
                  <TableHead>启用</TableHead>
                  <TableHead>操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {dashboardIndices.map((item, index) => (
                  <TableRow key={`${item.symbol}-${item.market}-${index}`}>
                    <TableCell>
                      <Input
                        value={item.alias ?? ""}
                        placeholder="指数名称"
                        onChange={(event) =>
                          updateIndexRow(index, { alias: event.target.value })
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        value={item.symbol}
                        placeholder="如 ^GSPC"
                        onChange={(event) =>
                          updateIndexRow(index, {
                            symbol: event.target.value.trim().toUpperCase(),
                          })
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <Select
                        value={item.market}
                        onValueChange={(value: string) =>
                          updateIndexRow(index, {
                            market: value as "CN" | "HK" | "US",
                          })
                        }
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Market" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="CN">CN</SelectItem>
                          <SelectItem value="HK">HK</SelectItem>
                          <SelectItem value="US">US</SelectItem>
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={item.enabled !== false}
                        aria-label={`${item.enabled !== false ? "禁用" : "启用"} ${item.alias || item.symbol}`}
                        onClick={() =>
                          updateIndexRow(index, { enabled: !(item.enabled !== false) })
                        }
                        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                          item.enabled !== false ? "bg-emerald-500" : "bg-slate-400"
                        }`}
                      >
                        <span
                          className={`inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform ${
                            item.enabled !== false ? "translate-x-5" : "translate-x-0.5"
                          }`}
                        />
                      </button>
                    </TableCell>
                    <TableCell>
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => removeIndexRow(index)}
                      >
                        <Trash2 className="mr-1 h-3.5 w-3.5" />
                        删除
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <div>
            <Button size="sm" variant="outline" onClick={addIndexRow}>
              <Plus className="mr-2 h-4 w-4" />
              新增指数
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* News sources */}
      <Card className="border-rose-200/60 bg-gradient-to-br from-white to-rose-50/40 dark:from-slate-900 dark:to-rose-950/20">
        <CardHeader>
          <CardTitle className="text-base">新闻来源配置</CardTitle>
          <CardDescription>每条来源可单独编辑、启用/禁用、删除；新增后立即生效。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="overflow-x-auto rounded-xl border border-border/60">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/30">
                  <TableHead>Source ID</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Category</TableHead>
                  <TableHead>URL</TableHead>
                  <TableHead>Enabled</TableHead>
                  <TableHead>操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sourceRows.map((row) => (
                  <TableRow key={row.source_id}>
                    <TableCell className="font-mono text-xs">{row.source_id}</TableCell>
                    <TableCell>
                      <Input
                        value={row.name}
                        onChange={(event) =>
                          setSourceRows((prev) =>
                            prev.map((item) =>
                              item.source_id === row.source_id ? { ...item, name: event.target.value } : item
                            )
                          )
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        value={row.category}
                        onChange={(event) =>
                          setSourceRows((prev) =>
                            prev.map((item) =>
                              item.source_id === row.source_id ? { ...item, category: event.target.value } : item
                            )
                          )
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        value={row.url}
                        onChange={(event) =>
                          setSourceRows((prev) =>
                            prev.map((item) =>
                              item.source_id === row.source_id ? { ...item, url: event.target.value } : item
                            )
                          )
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <Select
                        value={row.enabled ? "true" : "false"}
                        onValueChange={(value: string) =>
                          setSourceRows((prev) =>
                            prev.map((item) =>
                              item.source_id === row.source_id ? { ...item, enabled: value === "true" } : item
                            )
                          )
                        }
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="启用状态" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="true">enabled</SelectItem>
                          <SelectItem value="false">disabled</SelectItem>
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell className="space-x-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() =>
                          void onUpdateNewsSource(row.source_id, {
                            name: row.name,
                            category: row.category,
                            url: row.url,
                            enabled: row.enabled,
                          })
                        }
                      >
                        <Save className="mr-1 h-3.5 w-3.5" />
                        保存
                      </Button>
                      <Button size="sm" variant="destructive" onClick={() => void onDeleteNewsSource(row.source_id)}>
                        <Trash2 className="mr-1 h-3.5 w-3.5" />
                        删除
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <div className="grid gap-3 rounded-xl border border-border/80 bg-muted/20 p-4 md:grid-cols-[1fr_160px_2fr_120px_auto]">
            <Input placeholder="来源名称" value={newSourceName} onChange={(event) => setNewSourceName(event.target.value)} />
            <Input
              placeholder="分类（finance/policy）"
              value={newSourceCategory}
              onChange={(event) => setNewSourceCategory(event.target.value)}
            />
            <Input placeholder="https://..." value={newSourceUrl} onChange={(event) => setNewSourceUrl(event.target.value)} />
            <Select value={newSourceEnabled ? "true" : "false"} onValueChange={(value) => setNewSourceEnabled(value === "true")}>
              <SelectTrigger>
                <SelectValue placeholder="启用状态" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="true">enabled</SelectItem>
                <SelectItem value="false">disabled</SelectItem>
              </SelectContent>
            </Select>
            <Button
              disabled={creatingSource || !newSourceName.trim() || !newSourceCategory.trim() || !newSourceUrl.trim()}
              onClick={async () => {
                setCreatingSource(true);
                try {
                  await onCreateNewsSource({
                    name: newSourceName.trim(),
                    category: newSourceCategory.trim(),
                    url: newSourceUrl.trim(),
                    enabled: newSourceEnabled,
                  });
                  setNewSourceName("");
                  setNewSourceCategory("finance");
                  setNewSourceUrl("");
                  setNewSourceEnabled(true);
                } finally {
                  setCreatingSource(false);
                }
              }}
            >
              <Plus className="mr-2 h-4 w-4" />
              新增来源
            </Button>
          </div>
        </CardContent>
      </Card>

      <ProvidersPage
        providers={analysisProviders}
        providerConfigs={providerConfigs}
        defaultProvider={config.analysis.default_provider}
        defaultModel={config.analysis.default_model}
        onSetDefault={onSetDefault}
        onSaveSecret={onSaveSecret}
        onConnectAuth={onConnectAuth}
        onDisconnectAuth={onDisconnectAuth}
        onLoadModels={onLoadModels}
        onDeleteProvider={onDeleteProvider}
        onSaveProviderConfig={onSaveProviderConfig}
      />
    </div>
  );
}
