import { RefreshCw, Rocket, Save } from "lucide-react";

import type { AppConfig, UIOptions } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

type Props = {
  config: AppConfig;
  options: UIOptions;
  setConfig: (value: AppConfig) => void;
  sourcesText: string;
  setSourcesText: (value: string) => void;
  onSave: () => void;
  onReload: () => void;
  onRunReport: () => void;
  saving: boolean;
  running: boolean;
};

export function DashboardPage({
  config,
  options,
  setConfig,
  sourcesText,
  setSourcesText,
  onSave,
  onReload,
  onRunReport,
  saving,
  running,
}: Props) {
  return (
    <div className="grid gap-6 lg:grid-cols-5">
      <Card className="lg:col-span-3">
        <CardHeader>
          <CardTitle>系统配置</CardTitle>
          <CardDescription>模块默认 provider、采集参数、数据源都可在此编辑。</CardDescription>
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
                  {["composite", "yfinance", "akshare"].map((entry) => (
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
          <div className="space-y-2">
            <Label htmlFor="sources">新闻源 JSON</Label>
            <Textarea
              id="sources"
              className="min-h-[220px] font-mono"
              value={sourcesText}
              onChange={(event) => setSourcesText(event.target.value)}
            />
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
  );
}
