import { useEffect, useMemo, useState } from "react";
import { KeyRound, LogIn, LogOut, Save, Trash2 } from "lucide-react";

import type { AnalysisProviderConfig, AnalysisProviderView } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

type Props = {
  providers: AnalysisProviderView[];
  providerConfigs: AnalysisProviderConfig[];
  defaultProvider: string;
  defaultModel: string;
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
};

export function ProvidersPage({
  providers,
  providerConfigs,
  defaultProvider,
  defaultModel,
  onSetDefault,
  onSaveSecret,
  onConnectAuth,
  onDisconnectAuth,
  onLoadModels,
  onDeleteProvider,
  onSaveProviderConfig,
}: Props) {
  const [providerId, setProviderId] = useState(defaultProvider || "");
  const [model, setModel] = useState(defaultModel || "");
  const [apiKey, setApiKey] = useState("");
  const [modelOptions, setModelOptions] = useState<string[]>([]);
  const [configEnabled, setConfigEnabled] = useState(true);
  const [configBaseUrl, setConfigBaseUrl] = useState("");
  const [configTimeout, setConfigTimeout] = useState("30");
  const [configModelsText, setConfigModelsText] = useState("");
  const [configCallbackUrl, setConfigCallbackUrl] = useState("");
  const [configLoginTimeout, setConfigLoginTimeout] = useState("600");

  const orderedProviders = useMemo(
    () => [...providers].sort((a, b) => a.provider_id.localeCompare(b.provider_id)),
    [providers]
  );

  useEffect(() => {
    if (!orderedProviders.length) {
      setProviderId("");
      setModel("");
      return;
    }
    const preferredProviderId = defaultProvider || orderedProviders[0].provider_id;
    const nextProvider = orderedProviders.find((item) => item.provider_id === preferredProviderId) ?? orderedProviders[0];
    setProviderId(nextProvider.provider_id);
    if (defaultModel && nextProvider.models.includes(defaultModel)) {
      setModel(defaultModel);
      return;
    }
    setModel(nextProvider.models[0] ?? "");
  }, [defaultProvider, defaultModel, orderedProviders]);

  const selected = useMemo(
    () => providers.find((item) => item.provider_id === providerId),
    [providers, providerId]
  );
  const selectedProviderConfig = useMemo(
    () => providerConfigs.find((item) => item.provider_id === providerId) ?? null,
    [providerConfigs, providerId]
  );
  const selectedProviderId = selected?.provider_id ?? "";
  const selectedModels = selected?.models ?? [];
  const selectedModelsKey = selectedModels.join("|");
  const selectedAuthModeValue = selected?.auth_mode ?? "";
  const selectedConnected = Boolean(selected?.connected);
  const selectedAuthMode = selected?.auth_mode ?? (selected?.secret_required ? "api_key" : "none");
  const isOauthProvider = selectedAuthMode === "chatgpt_oauth";
  const isOauthConnected = Boolean(selected?.connected);
  const canConnectOauth = Boolean(selected);
  const showBaseUrlField = selectedProviderConfig?.type !== "mock" && selectedProviderConfig?.type !== "codex_app_server";
  const selectedStatusVariant = selected?.ready ? "default" : selected?.status === "disabled" ? "outline" : "destructive";
  const canSetDefault = Boolean(selected?.ready && model);
  const canSaveSecret = Boolean(selected?.secret_required && selectedAuthMode === "api_key");

  useEffect(() => {
    let cancelled = false;
    if (!selectedProviderId) {
      setModelOptions([]);
      return () => {
        cancelled = true;
      };
    }

    const fallback = selectedModels;
    if (selectedAuthModeValue !== "chatgpt_oauth" || !selectedConnected) {
      setModelOptions(fallback);
      return () => {
        cancelled = true;
      };
    }

    setModelOptions(fallback);
    void onLoadModels(selectedProviderId)
      .then((models) => {
        if (cancelled) {
          return;
        }
        if (models.length) {
          setModelOptions(models);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setModelOptions(fallback);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [onLoadModels, selectedProviderId, selectedModelsKey, selectedAuthModeValue, selectedConnected]);

  useEffect(() => {
    if (!modelOptions.length) {
      return;
    }
    if (!model || !modelOptions.includes(model)) {
      setModel(modelOptions[0]);
    }
  }, [model, modelOptions]);

  useEffect(() => {
    const cfg = selectedProviderConfig;
    if (!cfg) {
      setConfigEnabled(true);
      setConfigBaseUrl("");
      setConfigTimeout("30");
      setConfigModelsText("");
      setConfigCallbackUrl("");
      setConfigLoginTimeout("600");
      return;
    }
    setConfigEnabled(cfg.enabled);
    setConfigBaseUrl(cfg.base_url ?? "");
    setConfigTimeout(String(cfg.timeout ?? 30));
    setConfigModelsText((cfg.models ?? []).join("\n"));
    setConfigCallbackUrl(cfg.login_callback_url ?? "");
    setConfigLoginTimeout(String(cfg.login_timeout_seconds ?? 600));
  }, [selectedProviderConfig]);

  return (
    <div className="grid gap-6 lg:grid-cols-5">
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle>默认分析模型</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="space-y-2">
            <Label htmlFor="provider">Provider ID</Label>
            <Select
              value={providerId}
              onValueChange={(next: string) => {
                setProviderId(next);
                const nextProvider = providers.find((item) => item.provider_id === next);
                if (nextProvider?.models?.length) {
                  setModel(nextProvider.models[0]);
                } else {
                  setModel("");
                }
              }}
            >
              <SelectTrigger id="provider">
                <SelectValue placeholder="Provider" />
              </SelectTrigger>
              <SelectContent>
                {orderedProviders.map((provider) => (
                  <SelectItem key={provider.provider_id} value={provider.provider_id}>
                    {provider.provider_id} {!provider.ready ? `(${provider.status})` : ""}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="model">Model</Label>
            <Select value={model} onValueChange={(next: string) => setModel(next)} disabled={!modelOptions.length}>
              <SelectTrigger id="model">
                <SelectValue placeholder="Model" />
              </SelectTrigger>
              <SelectContent>
                {modelOptions.map((entry) => (
                  <SelectItem key={entry} value={entry}>
                    {entry}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button className="w-full" disabled={!canSetDefault} onClick={() => void onSetDefault(providerId, model)}>
            <Save className="mr-2 h-4 w-4" />
            更新默认 Provider/Model
          </Button>
          {selected ? (
            <div className="rounded-md border border-border bg-muted/30 p-3 text-xs text-muted-foreground">
              <div className="flex flex-wrap items-center gap-2">
                <span>状态:</span>
                <Badge variant={selectedStatusVariant}>{selected.status}</Badge>
                <Badge variant="outline">{selectedAuthMode}</Badge>
                {selectedAuthMode === "chatgpt_oauth" ? (
                  <Badge variant={isOauthConnected ? "secondary" : "outline"}>
                    {isOauthConnected ? "connected" : "disconnected"}
                  </Badge>
                ) : null}
              </div>
              <div className="mt-2">{selected.status_message}</div>
            </div>
          ) : null}

          {isOauthProvider ? (
            <div className="grid grid-cols-2 gap-2">
              <Button
                variant="secondary"
                disabled={!selected || !canConnectOauth}
                onClick={async () => {
                  if (!selected) {
                    return;
                  }
                  await onConnectAuth(selected.provider_id);
                }}
              >
                <LogIn className="mr-2 h-4 w-4" />
                Connect
              </Button>
              <Button
                variant="outline"
                disabled={!selected || !isOauthConnected}
                onClick={async () => {
                  if (!selected) {
                    return;
                  }
                  await onDisconnectAuth(selected.provider_id);
                }}
              >
                <LogOut className="mr-2 h-4 w-4" />
                Disconnect
              </Button>
            </div>
          ) : null}
          <div className="space-y-2">
            <Label htmlFor="secret">API Key</Label>
            <Input
              id="secret"
              type="password"
              placeholder={canSaveSecret ? "输入后仅写入后端加密存储" : "当前 Provider 不需要 API Key"}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              disabled={!canSaveSecret || isOauthProvider}
            />
          </div>
          <Button
            className="w-full"
            variant="secondary"
            disabled={!canSaveSecret || !apiKey.trim() || isOauthProvider}
            onClick={async () => {
              if (!canSaveSecret || !selected) {
                return;
              }
              await onSaveSecret(selected.provider_id, apiKey);
              setApiKey("");
            }}
          >
            <KeyRound className="mr-2 h-4 w-4" />
            保存 API Key
          </Button>

          {selectedProviderConfig ? (
            <div className="space-y-3 rounded-md border border-border bg-muted/30 p-3">
              <div className="text-sm font-medium">Provider 配置</div>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="provider_enabled">启用状态</Label>
                  <Select
                    value={configEnabled ? "enabled" : "disabled"}
                    onValueChange={(value: string) => setConfigEnabled(value === "enabled")}
                  >
                    <SelectTrigger id="provider_enabled">
                      <SelectValue placeholder="状态" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="enabled">enabled</SelectItem>
                      <SelectItem value="disabled">disabled</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="provider_timeout">Timeout(秒)</Label>
                  <Input
                    id="provider_timeout"
                    type="number"
                    min={3}
                    max={120}
                    value={configTimeout}
                    onChange={(event) => setConfigTimeout(event.target.value)}
                  />
                </div>
              </div>
              {showBaseUrlField ? (
                <div className="space-y-2">
                  <Label htmlFor="provider_base_url">Base URL</Label>
                  <Input
                    id="provider_base_url"
                    placeholder="https://api.openai.com/v1"
                    value={configBaseUrl}
                    onChange={(event) => setConfigBaseUrl(event.target.value)}
                  />
                </div>
              ) : null}
              {selectedProviderConfig?.type === "codex_app_server" ? (
                <div className="rounded-md border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
                  codex_app_server 使用本机官方 Codex app-server，无需配置 Base URL。
                </div>
              ) : null}
              <div className="space-y-2">
                <Label htmlFor="provider_models">Models（每行一个）</Label>
                <Textarea
                  id="provider_models"
                  className="min-h-[96px] font-mono text-xs"
                  value={configModelsText}
                  onChange={(event) => setConfigModelsText(event.target.value)}
                />
              </div>
              {selectedAuthMode === "chatgpt_oauth" ? (
                <div className="grid gap-3 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="provider_callback_url">Login Callback URL（可选）</Label>
                    <Input
                      id="provider_callback_url"
                      placeholder="留空则使用后端默认回调"
                      value={configCallbackUrl}
                      onChange={(event) => setConfigCallbackUrl(event.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="provider_login_timeout">Login Timeout(秒)</Label>
                    <Input
                      id="provider_login_timeout"
                      type="number"
                      min={60}
                      max={3600}
                      value={configLoginTimeout}
                      onChange={(event) => setConfigLoginTimeout(event.target.value)}
                    />
                  </div>
                </div>
              ) : null}
              <Button
                className="w-full"
                variant="outline"
                onClick={async () => {
                  if (!selectedProviderConfig) {
                    return;
                  }
                  const timeout = Number(configTimeout);
                  const loginTimeout = Number(configLoginTimeout);
                  const parsedModels = Array.from(
                    new Set(
                      configModelsText
                        .split(/\r?\n|,/)
                        .map((item) => item.trim())
                        .filter(Boolean)
                    )
                  );
                  await onSaveProviderConfig(selectedProviderConfig.provider_id, {
                    enabled: configEnabled,
                    base_url: configBaseUrl.trim(),
                    timeout: Number.isFinite(timeout) ? timeout : selectedProviderConfig.timeout,
                    models: parsedModels.length ? parsedModels : selectedProviderConfig.models,
                    login_callback_url: selectedAuthMode === "chatgpt_oauth" ? (configCallbackUrl.trim() || null) : null,
                    login_timeout_seconds:
                      selectedAuthMode === "chatgpt_oauth" && Number.isFinite(loginTimeout)
                        ? loginTimeout
                        : selectedProviderConfig.login_timeout_seconds,
                  });
                }}
              >
                <Save className="mr-2 h-4 w-4" />
                保存 Provider 配置
              </Button>
              <Button
                className="w-full"
                variant="destructive"
                disabled={!selectedProviderConfig}
                onClick={async () => {
                  if (!selectedProviderConfig) {
                    return;
                  }
                  await onDeleteProvider(selectedProviderConfig.provider_id);
                }}
              >
                <Trash2 className="mr-2 h-4 w-4" />
                删除 Provider
              </Button>
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card className="lg:col-span-3">
        <CardHeader>
          <CardTitle>Provider 列表</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Provider</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Models</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {orderedProviders.map((provider) => (
                <TableRow key={provider.provider_id}>
                  <TableCell>{provider.provider_id}</TableCell>
                  <TableCell>{provider.type}</TableCell>
                  <TableCell>{provider.models.join(", ")}</TableCell>
                  <TableCell className="space-x-1">
                    <Badge variant={provider.enabled ? "default" : "outline"}>
                      {provider.enabled ? "enabled" : "disabled"}
                    </Badge>
                    <Badge
                      variant={provider.ready ? "secondary" : provider.status === "disabled" ? "outline" : "destructive"}
                    >
                      {provider.status}
                    </Badge>
                    <Badge variant={provider.secret_required ? (provider.has_secret ? "secondary" : "outline") : "outline"}>
                      {provider.secret_required ? (provider.has_secret ? "secret-ready" : "missing-secret") : "not-required"}
                    </Badge>
                    {provider.auth_mode === "chatgpt_oauth" ? (
                      <Badge variant={provider.connected ? "secondary" : "outline"}>
                        {provider.connected ? "connected" : "disconnected"}
                      </Badge>
                    ) : null}
                    {provider.is_default ? <Badge variant="default">default</Badge> : null}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {selected ? (
            <div className="mt-4 text-sm text-muted-foreground">
              当前选中：{selected.provider_id} ({selected.type})
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
