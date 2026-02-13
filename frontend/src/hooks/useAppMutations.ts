import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api, type AppConfig } from "@/api/client";
import { useNotifier } from "@/components/ui/notifier";
import { toErrorMessage } from "@/hooks/useAppQueries";

export function useAppMutations(
  configDraft: AppConfig,
  setConfigDraft: React.Dispatch<React.SetStateAction<AppConfig>>,
  setSelectedRunId: React.Dispatch<React.SetStateAction<string>>,
  setErrorMessage: React.Dispatch<React.SetStateAction<string>>,
  setWarningMessage: React.Dispatch<React.SetStateAction<string>>,
) {
  const queryClient = useQueryClient();
  const notifier = useNotifier();

  const saveConfigMutation = useMutation({
    mutationFn: async () => api.updateConfig(configDraft),
    onSuccess: async (nextConfig) => {
      setConfigDraft(nextConfig);
      await queryClient.invalidateQueries({ queryKey: ["config"] });
      await queryClient.invalidateQueries({ queryKey: ["dashboard-snapshot"] });
      setErrorMessage("");
      notifier.success("配置已保存");
    },
    onError: (error) => {
      const message = toErrorMessage(error);
      setErrorMessage(message);
      notifier.error("保存配置失败", message);
    },
  });

  const runReportMutation = useMutation({
    mutationFn: async (reportPayload: Record<string, unknown>) => {
      const task = await api.runReportAsync({
        news_limit: configDraft.news_limit,
        flow_periods: configDraft.flow_periods,
        timezone: configDraft.timezone,
        provider_id: configDraft.analysis.default_provider,
        model: configDraft.analysis.default_model,
        ...reportPayload,
      });

      const deadline = Date.now() + 15 * 60 * 1000;
      while (Date.now() < deadline) {
        const snapshot = await api.getReportTask(task.task_id);
        if (snapshot.status === "SUCCEEDED") {
          if (snapshot.result) {
            return snapshot.result;
          }
          throw new Error("报告任务已完成，但结果为空。");
        }
        if (snapshot.status === "FAILED") {
          throw new Error(snapshot.error_message || "报告任务失败。");
        }
        await new Promise<void>((resolve) => window.setTimeout(resolve, 2000));
      }
      throw new Error("报告任务执行超时，请稍后在 Reports 页面检查结果。");
    },
    onMutate: () => {
      notifier.info("报告任务已提交", "后台正在生成，请稍候。");
      void queryClient.invalidateQueries({ queryKey: ["report-tasks"] });
    },
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ["reports"] });
      await queryClient.invalidateQueries({ queryKey: ["report-tasks"] });
      setSelectedRunId(result.summary.run_id);
      setWarningMessage(result.warnings[0] || "");
      setErrorMessage("");
      if (result.warnings[0]) {
        notifier.warning("报告已生成（存在告警）", result.warnings[0]);
      } else {
        notifier.success("报告已生成");
      }
    },
    onError: (error) => {
      setWarningMessage("");
      const message = toErrorMessage(error);
      setErrorMessage(message);
      notifier.error("生成报告失败", message);
    },
  });

  return { saveConfigMutation, runReportMutation };
}
