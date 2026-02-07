import { useEffect, useMemo, useState } from "react";
import { Plus, RefreshCw, Rocket, Save, Trash2 } from "lucide-react";

import type { AnalysisProviderView, AppConfig, NewsSource, UIOptions } from "@/api/client";
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
  newsSources: NewsSource[];
  onLoadProviderModels: (providerId: string) => Promise<string[]>;
  onCreateNewsSource: (payload: { name: string; category: string; url: string; enabled: boolean }) => Promise<void>;
  onUpdateNewsSource: (
    sourceId: string,
    payload: Partial<{ name: string; category: string; url: string; enabled: boolean }>
  ) => Promise<void>;
  onDeleteNewsSource: (sourceId: string) => Promise<void>;
  setConfig: (value: AppConfig) => void;
  onSave: () => void;
  onReload: () => void;
  onRunReport: () => void;
  saving: boolean;
  running: boolean;
};

type SourceRow = {
  source_id: string;
  name: string;
  category: string;
  url: string;
  enabled: boolean;
};

export function DashboardPage({
  config,
  options,
  analysisProviders,
  newsSources,
  onLoadProviderModels,
  onCreateNewsSource,
  onUpdateNewsSource,
  onDeleteNewsSource,
  setConfig,
  onSave,
  onReload,
  onRunReport,
  saving,
  running,
}: Props) {
  const [analysisModelOptions, setAnalysisModelOptions] = useState<string[]>([]);
  const [sourceRows, setSourceRows] = useState<SourceRow[]>([]);
  const [creatingSource, setCreatingSource] = useState(false);
  const [newSourceName, setNewSourceName] = useState("");
  const [newSourceCategory, setNewSourceCategory] = useState("finance");
  const [newSourceUrl, setNewSourceUrl] = useState("");
  const [newSourceEnabled, setNewSourceEnabled] = useState(true);

  const selectedProviderId = config.analysis.default_provider;
  const selectedProvider = useMemo(
    () => analysisProviders.find((item) => item.provider_id === selectedProviderId) ?? null,
    [analysisProviders, selectedProviderId]
  );
  const selectedProviderModelsKey = selectedProvider?.models.join("|") ?? "";

  useEffect(() => {
    let cancelled = false;
    const providerId = selectedProvider?.provider_id ?? "";
    if (!providerId) {
      setAnalysisModelOptions([]);
      return () => {
        cancelled = true;
      };
    }

    const fallback = selectedProvider?.models ?? [];
    setAnalysisModelOptions(fallback);
    void onLoadProviderModels(providerId)
      .then((models) => {
        if (cancelled) {
          return;
        }
        if (models.length) {
          setAnalysisModelOptions(models);
          return;
        }
        setAnalysisModelOptions(fallback);
      })
      .catch(() => {
        if (!cancelled) {
          setAnalysisModelOptions(fallback);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [onLoadProviderModels, selectedProviderId, selectedProviderModelsKey]);

  useEffect(() => {
    if (!analysisModelOptions.length) {
      return;
    }
    if (!analysisModelOptions.includes(config.analysis.default_model)) {
      setConfig({
        ...config,
        analysis: {
          ...config.analysis,
          default_model: analysisModelOptions[0],
        },
      });
    }
  }, [analysisModelOptions, config, setConfig]);

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

  const analysisProviderOptions = useMemo(() => analysisProviders, [analysisProviders]);

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>系统配置</CardTitle>
            <CardDescription>模块默认 provider 与采集参数。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
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
                <Label htmlFor="analysis_default_provider">分析默认 Provider</Label>
                <Select
                  value={config.analysis.default_provider}
                  onValueChange={(value: string) => {
                    const nextProviders = config.analysis.providers.map((provider) =>
                      provider.provider_id === value ? { ...provider, enabled: true } : provider
                    );
                    setConfig({
                      ...config,
                      analysis: {
                        ...config.analysis,
                        default_provider: value,
                        providers: nextProviders,
                      },
                    });
                  }}
                >
                  <SelectTrigger id="analysis_default_provider">
                    <SelectValue placeholder="分析 Provider" />
                  </SelectTrigger>
                  <SelectContent>
                    {analysisProviderOptions.map((entry) => (
                      <SelectItem key={entry.provider_id} value={entry.provider_id}>
                        {entry.provider_id} {!entry.enabled ? "(disabled)" : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="analysis_default_model">分析默认 Model（动态）</Label>
                <Select
                  value={config.analysis.default_model}
                  onValueChange={(value: string) =>
                    setConfig({
                      ...config,
                      analysis: {
                        ...config.analysis,
                        default_model: value,
                      },
                    })
                  }
                  disabled={!analysisModelOptions.length}
                >
                  <SelectTrigger id="analysis_default_model">
                    <SelectValue placeholder="分析 Model" />
                  </SelectTrigger>
                  <SelectContent>
                    {analysisModelOptions.map((entry) => (
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
                    {["composite", "finnhub", "yfinance", "akshare"].map((entry) => (
                      <SelectItem key={entry} value={entry}>
                        {entry}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
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
            <div className="flex flex-wrap gap-2">
              <Button onClick={onSave} disabled={saving}>
                <Save className="mr-2 h-4 w-4" />
                {saving ? "保存中..." : "保存配置"}
              </Button>
              <Button variant="outline" onClick={onReload}>
                <RefreshCw className="mr-2 h-4 w-4" />
                重载
              </Button>
            </div>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>报告任务</CardTitle>
            <CardDescription>触发全局新闻/资金流采集并生成模型分析报告。</CardDescription>
          </CardHeader>
          <CardContent>
            <Button size="lg" className="w-full" onClick={onRunReport} disabled={running}>
              <Rocket className="mr-2 h-4 w-4" />
              {running ? "执行中..." : "立即生成报告"}
            </Button>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>新闻来源配置（单条管理）</CardTitle>
          <CardDescription>每条来源可单独编辑、启用/禁用、删除；新增后立即生效。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Table>
            <TableHeader>
              <TableRow>
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
    </div>
  );
}
