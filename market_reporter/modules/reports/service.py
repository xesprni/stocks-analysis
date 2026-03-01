from __future__ import annotations

import asyncio
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4
from zoneinfo import ZoneInfo

from market_reporter.config import AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.infra.http.client import HttpClient
from market_reporter.modules.analysis.agent.service import AgentService
from market_reporter.modules.analysis.service import AnalysisService
from market_reporter.modules.fund_flow.service import FundFlowService
from market_reporter.modules.news.service import NewsService
from market_reporter.modules.reports.skills import (
    MarketReportSkill,
    ReportSkillContext,
    ReportSkillRegistry,
    StockReportSkill,
    WatchlistReportSkill,
)
from market_reporter.schemas import (
    ReportRunDetail,
    ReportRunSummary,
    ReportRunTaskView,
    ReportTaskStatus,
    RunRequest,
    RunResult,
)
from market_reporter.services.config_store import ConfigStore
from market_reporter.services.user_config_store import UserConfigStore
from market_reporter.services.telegram_notifier import TelegramNotifier

logger = logging.getLogger(__name__)


class ReportService:
    def __init__(
        self,
        config_store: ConfigStore,
        telegram_notifier: Optional[TelegramNotifier] = None,
    ) -> None:
        self.config_store = config_store
        self.telegram_notifier = telegram_notifier
        self._task_lock = asyncio.Lock()
        self._tasks: Dict[str, ReportRunTaskView] = {}
        self._task_user_ids: Dict[str, Optional[int]] = {}
        self._task_handles: Dict[str, asyncio.Task[None]] = {}
        self.skill_registry = ReportSkillRegistry(
            skills=[
                MarketReportSkill(),
                StockReportSkill(),
                WatchlistReportSkill(),
            ]
        )

    async def start_report_async(
        self,
        overrides: Optional[RunRequest] = None,
        user_id: Optional[int] = None,
    ) -> ReportRunTaskView:
        task_id = uuid4().hex
        task_view = ReportRunTaskView(
            task_id=task_id,
            status=ReportTaskStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
        async with self._task_lock:
            self._tasks[task_id] = task_view
            self._task_user_ids[task_id] = user_id
        # Detached background task keeps HTTP request latency low.
        task = asyncio.create_task(
            self._run_background_task(
                task_id=task_id,
                overrides=overrides,
                user_id=user_id,
            )
        )
        self._task_handles[task_id] = task
        task.add_done_callback(lambda _: self._task_handles.pop(task_id, None))
        return task_view

    async def get_report_task(
        self,
        task_id: str,
        user_id: Optional[int] = None,
    ) -> ReportRunTaskView:
        async with self._task_lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise FileNotFoundError(f"Report task not found: {task_id}")
            owner = self._task_user_ids.get(task_id)
            if owner != user_id:
                raise FileNotFoundError(f"Report task not found: {task_id}")
            return task

    async def list_report_tasks(
        self,
        user_id: Optional[int] = None,
    ) -> List[ReportRunTaskView]:
        """Return all tracked report tasks, sorted by creation time (newest first)."""
        async with self._task_lock:
            tasks = [
                task
                for task_id, task in self._tasks.items()
                if self._task_user_ids.get(task_id) == user_id
            ]
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks

    async def _run_background_task(
        self,
        task_id: str,
        overrides: Optional[RunRequest],
        user_id: Optional[int] = None,
    ) -> None:
        await self._update_task(
            task_id=task_id,
            status=ReportTaskStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
            error_message=None,
        )
        try:
            result = await self.run_report(overrides=overrides, user_id=user_id)
            await self._update_task(
                task_id=task_id,
                status=ReportTaskStatus.SUCCEEDED,
                finished_at=datetime.now(timezone.utc),
                result=result,
                error_message=None,
            )
        except Exception as exc:
            await self._update_task(
                task_id=task_id,
                status=ReportTaskStatus.FAILED,
                finished_at=datetime.now(timezone.utc),
                error_message=str(exc),
            )

    async def _update_task(
        self,
        task_id: str,
        status: ReportTaskStatus,
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None,
        result: Optional[RunResult] = None,
        error_message: Optional[str] = None,
    ) -> None:
        async with self._task_lock:
            task = self._tasks.get(task_id)
            if task is None:
                return
            # Copy-update keeps Pydantic model immutable semantics explicit.
            update_payload = {
                "status": status,
                "error_message": error_message
                if error_message is not None
                else task.error_message,
            }
            if started_at is not None:
                update_payload["started_at"] = started_at
            if finished_at is not None:
                update_payload["finished_at"] = finished_at
            if result is not None:
                update_payload["result"] = result
            self._tasks[task_id] = task.model_copy(update=update_payload)

    def _resolve_telegram_notifier(
        self,
        user_id: Optional[int] = None,
    ) -> Optional[TelegramNotifier]:
        if self.telegram_notifier is not None:
            return self.telegram_notifier
        try:
            config = self._load_config(user_id=user_id)
            return TelegramNotifier.from_config(config.telegram)
        except Exception as exc:
            logger.warning("resolve telegram notifier failed: %s", exc)
            return None

    async def _notify_report_succeeded(
        self,
        result: RunResult,
        user_id: Optional[int] = None,
    ) -> None:
        notifier = self._resolve_telegram_notifier(user_id=user_id)
        if notifier is None:
            return
        try:
            await notifier.notify_report_succeeded(result=result)
        except Exception as exc:
            logger.warning("telegram success notify failed: %s", exc)

    async def _notify_report_failed(
        self,
        *,
        error: str,
        mode: str,
        skill_id: Optional[str],
        user_id: Optional[int] = None,
    ) -> None:
        notifier = self._resolve_telegram_notifier(user_id=user_id)
        if notifier is None:
            return
        try:
            await notifier.notify_report_failed(
                error=error,
                mode=mode,
                skill_id=skill_id,
            )
        except Exception as exc:
            logger.warning("telegram failure notify failed: %s", exc)

    async def run_report(
        self,
        overrides: Optional[RunRequest] = None,
        user_id: Optional[int] = None,
    ) -> RunResult:
        requested_mode = (
            (overrides.mode if overrides else "market") or "market"
        ).lower()
        requested_skill_id = overrides.skill_id if overrides else None

        try:
            config = self._build_runtime_config(overrides=overrides, user_id=user_id)
            config.ensure_output_root()
            config.ensure_data_root()
            generated_at = self._now_iso8601(config.timezone)

            warnings: List[str] = []
            resolved_skill = self.skill_registry.resolve(
                skill_id=requested_skill_id,
                mode=requested_mode,
            )
            agent_mode = resolved_skill.mode
            report_skill_id = resolved_skill.skill_id
            news_total = 0
            provider_id = ""
            model = ""
            analysis_payload: Dict[str, object] = {}
            markdown = ""
            async with HttpClient(
                timeout_seconds=config.request_timeout_seconds,
                user_agent=config.user_agent,
            ) as client:
                registry = ProviderRegistry()
                news_service = NewsService(
                    config=config, client=client, registry=registry
                )
                fund_flow_service = FundFlowService(
                    config=config, client=client, registry=registry
                )
                analysis_service = AnalysisService(
                    config=config,
                    registry=registry,
                    user_id=user_id,
                    news_service=news_service,
                    fund_flow_service=fund_flow_service,
                )
                try:
                    provider_cfg, selected_model, api_key, access_token = (
                        analysis_service.resolve_credentials(
                            provider_id=None,
                            model=None,
                        )
                    )
                    provider_id = provider_cfg.provider_id
                    model = selected_model

                    agent_service = AgentService(
                        config=config,
                        registry=registry,
                        news_service=news_service,
                        fund_flow_service=fund_flow_service,
                    )
                    skill_result = await resolved_skill.run(
                        ReportSkillContext(
                            config=config,
                            overrides=overrides,
                            generated_at=generated_at,
                            agent_service=agent_service,
                            provider_cfg=provider_cfg,
                            selected_model=selected_model,
                            api_key=api_key,
                            access_token=access_token,
                        )
                    )
                    markdown = skill_result.markdown
                    analysis_payload = skill_result.analysis_payload
                    news_total = skill_result.news_total
                    warnings.extend(skill_result.warnings)
                    agent_mode = skill_result.mode
                    report_skill_id = skill_result.skill_id
                except Exception as exc:
                    provider_id = provider_id or "fallback-local"
                    model = model or "n/a"
                    warnings.append(f"agent_report_fallback: {exc}")
                    markdown = (
                        "# Agent 分析报告\n\n"
                        "- 模式: fallback\n"
                        f"- 生成时间: {generated_at}\n\n"
                        "模型执行失败，已生成降级占位报告。\n"
                    )
                    analysis_payload = {
                        "summary": "模型执行失败，报告已降级。",
                        "sentiment": "neutral",
                        "key_levels": [],
                        "risks": ["agent runtime unavailable"],
                        "action_items": ["检查 provider 配置和鉴权状态"],
                        "confidence": 0.2,
                        "markdown": markdown,
                        "raw": {"error": str(exc)},
                    }
                    report_skill_id = report_skill_id or "fallback"

            run_output_root = self._resolve_output_root(config=config, user_id=user_id)
            run_dir = self._build_run_dir(output_root=run_output_root)
            report_path = run_dir / "report.md"
            raw_path = run_dir / "raw_data.json"
            meta_path = run_dir / "meta.json"

            report_path.write_text(markdown, encoding="utf-8")

            raw_payload = {
                "generated_at": generated_at,
                "mode": agent_mode,
                "skill_id": report_skill_id,
                "provider_id": provider_id,
                "model": model,
                "analysis": analysis_payload,
                "warnings": warnings,
            }
            summary_fields = self._extract_summary_fields(raw_payload)
            raw_path.write_text(
                json.dumps(raw_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            summary = ReportRunSummary(
                run_id=run_dir.name,
                generated_at=generated_at,
                report_path=report_path.resolve(),
                raw_data_path=raw_path.resolve(),
                warnings_count=len(warnings),
                news_total=news_total,
                provider_id=provider_id,
                model=model,
                confidence=summary_fields["confidence"],
                sentiment=summary_fields["sentiment"],
                mode=summary_fields["mode"],
            )
            meta_path.write_text(
                json.dumps(
                    {
                        "summary": summary.model_dump(mode="json"),
                        "warnings": warnings,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            result = RunResult(summary=summary, warnings=warnings)
            await self._notify_report_succeeded(result=result, user_id=user_id)
            return result
        except Exception as exc:
            await self._notify_report_failed(
                error=str(exc),
                mode=requested_mode,
                skill_id=requested_skill_id,
                user_id=user_id,
            )
            raise

    def list_reports(self, user_id: Optional[int] = None) -> List[ReportRunSummary]:
        config = self._load_config(user_id=user_id)
        root = self._resolve_output_root(config=config, user_id=user_id)
        root.mkdir(parents=True, exist_ok=True)
        if not root.exists():
            return []

        summaries: List[ReportRunSummary] = []
        run_dirs = sorted(
            [item for item in root.iterdir() if item.is_dir()],
            key=lambda item: item.name,
            reverse=True,
        )
        for run_dir in run_dirs:
            summary = self._read_summary(run_dir)
            if summary is not None:
                summaries.append(summary)
        return summaries

    def get_report(
        self,
        run_id: str,
        user_id: Optional[int] = None,
    ) -> ReportRunDetail:
        config = self._load_config(user_id=user_id)
        root = self._resolve_output_root(config=config, user_id=user_id)
        run_dir = root / run_id
        report_path = run_dir / "report.md"
        raw_path = run_dir / "raw_data.json"
        if not run_dir.exists() or not report_path.exists() or not raw_path.exists():
            raise FileNotFoundError(f"Report run not found: {run_id}")

        summary = self._read_summary(run_dir)
        if summary is None:
            summary = ReportRunSummary(
                run_id=run_id,
                generated_at=self._run_id_to_generated_at(run_id),
                report_path=report_path.resolve(),
                raw_data_path=raw_path.resolve(),
                warnings_count=0,
                news_total=0,
                provider_id="",
                model="",
            )

        return ReportRunDetail(
            summary=summary,
            report_markdown=report_path.read_text(encoding="utf-8"),
            raw_data=json.loads(raw_path.read_text(encoding="utf-8")),
        )

    def delete_report(self, run_id: str, user_id: Optional[int] = None) -> bool:
        config = self._load_config(user_id=user_id)
        root = self._resolve_output_root(config=config, user_id=user_id).resolve()
        root.mkdir(parents=True, exist_ok=True)
        target = (root / run_id).resolve()
        if not target.exists() or not target.is_dir():
            return False
        # Safety check prevents accidental deletion outside report root.
        if target == root or root not in target.parents:
            raise ValueError("Invalid report path.")
        shutil.rmtree(target)
        return True

    def _build_runtime_config(
        self,
        overrides: Optional[RunRequest],
        user_id: Optional[int] = None,
    ) -> AppConfig:
        config = self._load_config(user_id=user_id)
        if overrides is None:
            return config
        payload = config.model_dump(mode="python")
        if overrides.news_limit is not None:
            payload["news_limit"] = overrides.news_limit
        if overrides.flow_periods is not None:
            payload["flow_periods"] = overrides.flow_periods
        if overrides.timezone:
            payload["timezone"] = overrides.timezone
        if overrides.provider_id:
            payload["analysis"]["default_provider"] = overrides.provider_id
        if overrides.model:
            payload["analysis"]["default_model"] = overrides.model
        return AppConfig.model_validate(payload)

    @staticmethod
    def _build_run_dir(output_root: Path) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = output_root / stamp
        cursor = 1
        # Ensure unique run directory when multiple jobs finish in same second.
        while run_dir.exists():
            run_dir = output_root / f"{stamp}_{cursor}"
            cursor += 1
        run_dir.mkdir(parents=True, exist_ok=False)
        return run_dir

    @staticmethod
    def _resolve_output_root(config: AppConfig, user_id: Optional[int]) -> Path:
        base_root = config.ensure_output_root()
        if user_id is None:
            return base_root
        return base_root / f"user_{user_id}"

    def _load_config(self, user_id: Optional[int] = None) -> AppConfig:
        if user_id is None:
            return self.config_store.load(user_id=None)
        global_config = self.config_store.load(user_id=None)
        store = UserConfigStore(
            database_url=global_config.database.url,
            global_config_path=self.config_store.config_path,
            user_id=user_id,
        )
        if not store.has_user_config():
            store.init_from_global()
        return store.load()

    @staticmethod
    def _now_iso8601(timezone_name: str) -> str:
        try:
            tz = ZoneInfo(timezone_name)
        except Exception:
            tz = ZoneInfo("UTC")
        return datetime.now(tz).isoformat(timespec="seconds")

    def _read_summary(self, run_dir: Path) -> Optional[ReportRunSummary]:
        meta_path = run_dir / "meta.json"
        raw_payload = self._read_raw_payload(run_dir)
        fallback_fields = self._extract_summary_fields(raw_payload)
        if meta_path.exists():
            payload = json.loads(meta_path.read_text(encoding="utf-8"))
            summary_data = payload.get("summary")
            if isinstance(summary_data, dict):
                if (
                    summary_data.get("confidence") is None
                    and fallback_fields["confidence"] is not None
                ):
                    summary_data["confidence"] = fallback_fields["confidence"]
                if (
                    summary_data.get("sentiment") is None
                    and fallback_fields["sentiment"] is not None
                ):
                    summary_data["sentiment"] = fallback_fields["sentiment"]
                if (
                    summary_data.get("mode") is None
                    and fallback_fields["mode"] is not None
                ):
                    summary_data["mode"] = fallback_fields["mode"]
                return ReportRunSummary.model_validate(summary_data)

        report_path = run_dir / "report.md"
        raw_path = run_dir / "raw_data.json"
        if not report_path.exists() or not raw_path.exists():
            return None

        return ReportRunSummary(
            run_id=run_dir.name,
            generated_at=self._run_id_to_generated_at(run_dir.name),
            report_path=report_path.resolve(),
            raw_data_path=raw_path.resolve(),
            warnings_count=0,
            news_total=0,
            provider_id="",
            model="",
            confidence=fallback_fields["confidence"],
            sentiment=fallback_fields["sentiment"],
            mode=fallback_fields["mode"],
        )

    @staticmethod
    def _read_raw_payload(run_dir: Path) -> Dict[str, Any]:
        raw_path = run_dir / "raw_data.json"
        if not raw_path.exists():
            return {}
        try:
            payload = json.loads(raw_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    @classmethod
    def _extract_summary_fields(
        cls, raw_payload: Dict[str, Any]
    ) -> Dict[str, Optional[Any]]:
        analysis = raw_payload.get("analysis")
        analysis_dict = analysis if isinstance(analysis, dict) else {}
        return {
            "confidence": cls._coerce_float(analysis_dict.get("confidence")),
            "sentiment": cls._coerce_text(analysis_dict.get("sentiment")),
            "mode": cls._coerce_text(raw_payload.get("mode")),
        }

    @staticmethod
    def _coerce_float(value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            result = float(value)
        except (TypeError, ValueError):
            return None
        if result != result:  # NaN guard
            return None
        return result

    @staticmethod
    def _coerce_text(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _run_id_to_generated_at(run_id: str) -> str:
        try:
            compact = run_id
            if "_" in run_id:
                parts = run_id.split("_")
                if len(parts) >= 2 and parts[1].isdigit() and len(parts[1]) == 6:
                    compact = f"{parts[0]}_{parts[1]}"
            return datetime.strptime(compact, "%Y%m%d_%H%M%S").isoformat(
                timespec="seconds"
            )
        except Exception:
            return run_id
