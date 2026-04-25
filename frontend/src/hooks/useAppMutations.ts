import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api, type AppConfig, type ReportTask } from "@/api/client";
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

      return task;
    },
    onMutate: () => {
      notifier.info("报告任务已提交", "后台正在生成，请稍候。");
      void queryClient.invalidateQueries({ queryKey: ["report-tasks"] });
    },
    onSuccess: async (task) => {
      queryClient.setQueryData<ReportTask[]>(["report-tasks"], (current = []) => {
        const withoutTask = current.filter((item) => item.task_id !== task.task_id);
        return [task, ...withoutTask];
      });
      await queryClient.invalidateQueries({ queryKey: ["report-tasks"] });
      setSelectedRunId("");
      setWarningMessage("");
      setErrorMessage("");
      notifier.success("报告任务已开始", `任务 ${task.task_id.slice(0, 12)}...`);
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
