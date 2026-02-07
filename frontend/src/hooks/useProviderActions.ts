import { useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { api } from "@/api/client";
import { useNotifier } from "@/components/ui/notifier";

export function useProviderActions() {
  const queryClient = useQueryClient();
  const notifier = useNotifier();

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

  return { loadAnalysisModels, connectProviderAuth, disconnectProviderAuth };
}
