import { useEffect, useMemo, useState } from "react";
import { KeyRound, Save } from "lucide-react";

import type { AnalysisProviderView } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

type Props = {
  providers: AnalysisProviderView[];
  defaultProvider: string;
  defaultModel: string;
  onSetDefault: (providerId: string, model: string) => Promise<void>;
  onSaveSecret: (providerId: string, apiKey: string) => Promise<void>;
};

export function ProvidersPage({
  providers,
  defaultProvider,
  defaultModel,
  onSetDefault,
  onSaveSecret,
}: Props) {
  const [providerId, setProviderId] = useState(defaultProvider || "");
  const [model, setModel] = useState(defaultModel || "");
  const [apiKey, setApiKey] = useState("");

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
  const selectedStatusVariant = selected?.ready ? "default" : selected?.status === "disabled" ? "outline" : "destructive";
  const canSetDefault = Boolean(selected?.ready && model);
  const canSaveSecret = Boolean(selected?.secret_required);

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
            <Select value={model} onValueChange={(next: string) => setModel(next)} disabled={!selected?.models.length}>
              <SelectTrigger id="model">
                <SelectValue placeholder="Model" />
              </SelectTrigger>
              <SelectContent>
                {(selected?.models ?? []).map((entry) => (
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
              <div className="flex items-center gap-2">
                <span>状态:</span>
                <Badge variant={selectedStatusVariant}>{selected.status}</Badge>
              </div>
              <div className="mt-2">{selected.status_message}</div>
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
              disabled={!canSaveSecret}
            />
          </div>
          <Button
            className="w-full"
            variant="secondary"
            disabled={!canSaveSecret || !apiKey.trim()}
            onClick={async () => {
              if (!canSaveSecret) {
                return;
              }
              await onSaveSecret(providerId, apiKey);
              setApiKey("");
            }}
          >
            <KeyRound className="mr-2 h-4 w-4" />
            保存 API Key
          </Button>
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
