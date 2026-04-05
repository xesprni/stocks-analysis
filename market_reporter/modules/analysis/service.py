from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from openai import AsyncOpenAI

from market_reporter.config import AnalysisProviderConfig, AppConfig
from market_reporter.core.utils import parse_json
from market_reporter.core.types import (
    AnalysisInput,
    AnalysisOutput,
)
from market_reporter.infra.db.repos import (
    AnalysisProviderSecretRepo,
    StockAnalysisRunRepo,
)
from market_reporter.infra.db.session import session_scope
from market_reporter.infra.security.crypto import decrypt_text, encrypt_text
from market_reporter.infra.security.keychain_store import KeychainStore
from market_reporter.modules.analysis.schemas import (
    AnalysisProviderView,
    ProviderAvailabilityView,
    ProviderModelsView,
    StockAnalysisHistoryItem,
    StockAnalysisRunView,
)
from market_reporter.modules.analysis.agent.schemas import AgentRunRequest
from market_reporter.modules.analysis.agent.service import AgentService
from market_reporter.modules.market_data.symbol_mapper import normalize_symbol


class AnalysisService:
    MODULE_NAME = "analysis"

    def __init__(
        self,
        config: AppConfig,
        user_id: Optional[int] = None,
        keychain_store: Optional[KeychainStore] = None,
    ) -> None:
        self.config = config
        self.user_id = user_id
        self.keychain_store = keychain_store or KeychainStore(
            database_url=config.database.url
        )

    # ------------------------------------------------------------------
    # Provider listing
    # ------------------------------------------------------------------

    def list_providers(self) -> List[AnalysisProviderView]:
        providers = []
        with session_scope(self.config.database.url) as session:
            secret_repo = AnalysisProviderSecretRepo(session)
            for provider in self.config.analysis.providers:
                has_secret = (
                    secret_repo.get(
                        provider.provider_id,
                        user_id=self.user_id,
                    )
                    is not None
                )
                has_base_url = bool((provider.base_url or "").strip())
                ready = provider.enabled and bool(provider.models) and has_secret and has_base_url
                providers.append(
                    AnalysisProviderView(
                        provider_id=provider.provider_id,
                        type=provider.type,
                        base_url=provider.base_url,
                        models=provider.models,
                        timeout=provider.timeout,
                        enabled=provider.enabled,
                        has_secret=has_secret,
                        secret_required=True,
                        ready=ready,
                        status="ready" if ready else "not-ready",
                        status_message="Provider is ready." if ready else "API key or configuration missing.",
                        is_default=provider.provider_id
                        == self.config.analysis.default_provider,
                        auth_mode="api_key",
                        connected=has_secret,
                        credential_expires_at=None,
                    )
                )
        return providers

    # ------------------------------------------------------------------
    # Secret management (API key)
    # ------------------------------------------------------------------

    def put_secret(self, provider_id: str, api_key: str) -> None:
        provider = self._find_provider(provider_id)
        master_key = self.keychain_store.get_or_create_master_key()
        ciphertext, nonce = encrypt_text(api_key, master_key)
        with session_scope(self.config.database.url) as session:
            repo = AnalysisProviderSecretRepo(session)
            repo.upsert(
                provider_id=provider_id,
                ciphertext=ciphertext,
                nonce=nonce,
                user_id=self.user_id,
            )

    def delete_secret(self, provider_id: str) -> bool:
        with session_scope(self.config.database.url) as session:
            repo = AnalysisProviderSecretRepo(session)
            return repo.delete(provider_id=provider_id, user_id=self.user_id)

    # ------------------------------------------------------------------
    # Provider availability check
    # ------------------------------------------------------------------

    async def check_provider_availability(
        self,
        provider_id: str,
        model: Optional[str] = None,
    ) -> ProviderAvailabilityView:
        started = time.perf_counter()
        checked_at = datetime.now(timezone.utc)

        try:
            provider_cfg = self.ensure_provider_ready(
                provider_id=provider_id, model=model
            )
        except Exception as exc:
            return ProviderAvailabilityView(
                provider_id=provider_id,
                model=(model or "").strip(),
                available=False,
                status="not-ready",
                message=str(exc),
                checked_at=checked_at,
                latency_ms=self._elapsed_ms(started),
                details={"error_type": type(exc).__name__},
            )

        selected_model = self._resolve_healthcheck_model(
            provider_cfg=provider_cfg,
            requested_model=model,
        )
        if not selected_model:
            return ProviderAvailabilityView(
                provider_id=provider_id,
                model="",
                available=False,
                status="missing-model",
                message="No model available for availability check.",
                checked_at=checked_at,
                latency_ms=self._elapsed_ms(started),
            )

        try:
            api_key = self._resolve_api_key(provider_cfg=provider_cfg)
            if not api_key:
                raise ValueError("Provider API key is not configured.")

            client = AsyncOpenAI(
                api_key=api_key,
                base_url=provider_cfg.base_url,
                timeout=max(3, min(provider_cfg.timeout, 20)),
            )
            response = await client.chat.completions.create(
                model=selected_model,
                temperature=0,
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
            content = (response.choices[0].message.content or "").strip()
            return ProviderAvailabilityView(
                provider_id=provider_id,
                model=selected_model,
                available=True,
                status="ready",
                message="Provider response is available.",
                checked_at=checked_at,
                latency_ms=self._elapsed_ms(started),
                details={
                    "probe": "chat.completions",
                    "content_preview": content[:80],
                },
            )
        except Exception as exc:
            return ProviderAvailabilityView(
                provider_id=provider_id,
                model=selected_model,
                available=False,
                status="unavailable",
                message=str(exc),
                checked_at=checked_at,
                latency_ms=self._elapsed_ms(started),
                details={"error_type": type(exc).__name__},
            )

    async def list_provider_models(self, provider_id: str) -> ProviderModelsView:
        provider_cfg = self._find_provider(provider_id)
        return ProviderModelsView(
            provider_id=provider_id,
            models=provider_cfg.models,
            source="config",
        )

    # ------------------------------------------------------------------
    # Stock analysis (core)
    # ------------------------------------------------------------------

    def ensure_provider_ready(
        self,
        provider_id: str,
        model: Optional[str] = None,
    ) -> AnalysisProviderConfig:
        provider = self._find_provider(provider_id)
        has_secret = self._has_secret(provider.provider_id)
        has_base_url = bool((provider.base_url or "").strip())
        if not provider.enabled:
            raise ValueError("Provider is disabled in config.")
        if not provider.models:
            raise ValueError("No available models configured for this provider.")
        if not has_base_url:
            raise ValueError("Provider base_url is not configured.")
        if not has_secret:
            raise ValueError("Provider API key is not configured.")
        if model and provider.models and model not in provider.models:
            raise ValueError(f"Model not found in provider models: {model}")
        return provider

    async def run_stock_analysis(
        self,
        symbol: str,
        market: str,
        skill_id: Optional[str] = None,
        provider_id: Optional[str] = None,
        model: Optional[str] = None,
        interval: str = "5m",
        lookback_bars: int = 120,
        question: Optional[str] = None,
        peer_list: Optional[List[str]] = None,
        indicators: Optional[List[str]] = None,
        news_from: Optional[str] = None,
        news_to: Optional[str] = None,
        filing_from: Optional[str] = None,
        filing_to: Optional[str] = None,
        timeframes: Optional[List[str]] = None,
        indicator_profile: Optional[str] = None,
    ) -> StockAnalysisRunView:
        provider_cfg, selected_model, api_key, access_token = self.resolve_credentials(
            provider_id=provider_id, model=model
        )
        normalized_symbol = normalize_symbol(symbol=symbol, market=market)

        agent_service = AgentService(config=self.config)
        agent_request = AgentRunRequest(
            mode="stock",
            skill_id=skill_id,
            symbol=normalized_symbol,
            market=market.upper(),
            question=question or "",
            peer_list=peer_list or [],
            indicators=indicators or [],
            news_from=news_from,
            news_to=news_to,
            filing_from=filing_from,
            filing_to=filing_to,
            timeframes=timeframes or [],
            indicator_profile=indicator_profile or "balanced",
        )
        agent_run = await agent_service.run(
            request=agent_request,
            provider_cfg=provider_cfg,
            model=selected_model,
            api_key=api_key,
        )
        payload, output = agent_service.to_analysis_payload(
            request=agent_request,
            run_result=agent_run,
        )
        run_id, created_at = self._save_run(
            symbol=normalized_symbol,
            market=market.upper(),
            provider_id=provider_cfg.provider_id,
            model=selected_model,
            status="SUCCESS",
            payload=payload,
            output=output,
        )

        return StockAnalysisRunView(
            id=run_id,
            symbol=normalized_symbol,
            market=market.upper(),
            provider_id=provider_cfg.provider_id,
            model=selected_model,
            status="SUCCESS",
            output=output,
            markdown=output.markdown,
            created_at=created_at,
        )

    def resolve_credentials(
        self,
        provider_id: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Tuple[AnalysisProviderConfig, str, Optional[str], None]:
        """Select a provider and resolve its credentials.

        Returns ``(provider_cfg, selected_model, api_key, None)``.
        """
        provider_cfg, selected_model = self._select_provider_and_model(
            provider_id=provider_id, model=model
        )

        try:
            self.ensure_provider_ready(
                provider_id=provider_cfg.provider_id,
                model=selected_model or None,
            )
        except Exception:
            if provider_id:
                raise
            fallback = self._select_first_ready_provider(preferred_model=model)
            if fallback is None:
                raise
            provider_cfg, selected_model = fallback

        api_key = self._resolve_api_key(provider_cfg=provider_cfg)
        return provider_cfg, selected_model, api_key, None

    # ------------------------------------------------------------------
    # History CRUD
    # ------------------------------------------------------------------

    def list_history(
        self, symbol: str, market: str, limit: int = 20
    ) -> List[StockAnalysisHistoryItem]:
        normalized_symbol = normalize_symbol(symbol=symbol, market=market)
        with session_scope(self.config.database.url) as session:
            repo = StockAnalysisRunRepo(session)
            rows = repo.list_by_symbol(
                symbol=normalized_symbol,
                market=market.upper(),
                limit=limit,
                user_id=self.user_id,
            )
            return [self._to_history_item(row) for row in rows]

    def list_recent_history(
        self,
        limit: int = 50,
        symbol: Optional[str] = None,
        market: Optional[str] = None,
    ) -> List[StockAnalysisHistoryItem]:
        normalized_symbol = None
        normalized_market = market.upper() if market else None
        if symbol and market:
            normalized_symbol = normalize_symbol(symbol=symbol, market=market)
        elif symbol:
            normalized_symbol = symbol.strip().upper()

        with session_scope(self.config.database.url) as session:
            repo = StockAnalysisRunRepo(session)
            rows = repo.list_recent(
                limit=limit,
                symbol=normalized_symbol,
                market=normalized_market,
                user_id=self.user_id,
            )
            return [self._to_history_item(row) for row in rows]

    def get_history_item(self, run_id: int) -> StockAnalysisHistoryItem:
        with session_scope(self.config.database.url) as session:
            repo = StockAnalysisRunRepo(session)
            row = repo.get(run_id=run_id, user_id=self.user_id)
            if row is None:
                raise FileNotFoundError(f"Stock analysis run not found: {run_id}")
            return self._to_history_item(row)

    def delete_history_item(self, run_id: int) -> bool:
        with session_scope(self.config.database.url) as session:
            repo = StockAnalysisRunRepo(session)
            return repo.delete(run_id=run_id, user_id=self.user_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_api_key(self, provider_cfg: AnalysisProviderConfig) -> Optional[str]:
        with session_scope(self.config.database.url) as session:
            secret_repo = AnalysisProviderSecretRepo(session)
            secret = secret_repo.get(
                provider_cfg.provider_id,
                user_id=self.user_id,
            )
            if secret is None:
                return None
            key_ciphertext = secret.key_ciphertext
            nonce = secret.nonce

        master_key = self.keychain_store.get_or_create_master_key()
        return decrypt_text(key_ciphertext, nonce, master_key)

    def _has_secret(self, provider_id: str) -> bool:
        with session_scope(self.config.database.url) as session:
            secret_repo = AnalysisProviderSecretRepo(session)
            return secret_repo.get(provider_id, user_id=self.user_id) is not None

    def _find_provider(self, provider_id: str) -> AnalysisProviderConfig:
        for provider in self.config.analysis.providers:
            if provider.provider_id == provider_id:
                return provider
        raise ValueError(f"Unknown analysis provider: {provider_id}")

    def _select_provider_and_model(
        self,
        provider_id: Optional[str],
        model: Optional[str],
    ) -> Tuple[AnalysisProviderConfig, str]:
        provider_map = {
            provider.provider_id: provider
            for provider in self.config.analysis.providers
        }
        selected_provider_id = provider_id or self.config.analysis.default_provider
        if selected_provider_id not in provider_map:
            raise ValueError(f"Selected provider not found: {selected_provider_id}")
        provider_cfg = provider_map[selected_provider_id]
        if not provider_cfg.enabled:
            if provider_id:
                provider_cfg = provider_cfg.model_copy(update={"enabled": True})
            else:
                fallback_enabled = next(
                    (item for item in provider_map.values() if item.enabled), None
                )
                if fallback_enabled is None:
                    raise ValueError(
                        f"Selected provider not enabled: {selected_provider_id}"
                    )
                provider_cfg = fallback_enabled

        selected_model = model or self.config.analysis.default_model
        if not selected_model and provider_cfg.models:
            selected_model = provider_cfg.models[0]
        if selected_model not in provider_cfg.models and provider_cfg.models:
            selected_model = provider_cfg.models[0]
        return provider_cfg, selected_model

    def _select_first_ready_provider(
        self,
        preferred_model: Optional[str] = None,
    ) -> Optional[Tuple[AnalysisProviderConfig, str]]:
        for provider in self.config.analysis.providers:
            candidate_model = self._resolve_fallback_model_for_provider(
                provider_cfg=provider,
                preferred_model=preferred_model,
            )
            try:
                self.ensure_provider_ready(
                    provider_id=provider.provider_id,
                    model=candidate_model or None,
                )
            except Exception:
                continue

            resolved_model = candidate_model
            if not resolved_model and provider.models:
                resolved_model = str(provider.models[0]).strip()
            if not resolved_model:
                resolved_model = str(self.config.analysis.default_model or "").strip()

            return provider, resolved_model
        return None

    def _save_run(
        self,
        symbol: str,
        market: str,
        provider_id: str,
        model: str,
        status: str,
        payload: AnalysisInput,
        output: AnalysisOutput,
    ) -> Tuple[int, datetime]:
        with session_scope(self.config.database.url) as session:
            repo = StockAnalysisRunRepo(session)
            row = repo.add(
                symbol=symbol,
                market=market,
                provider_id=provider_id,
                model=model,
                status=status,
                input_json=payload.model_dump_json(),
                output_json=output.model_dump_json(),
                markdown=output.markdown,
                user_id=self.user_id,
            )
            run_id = row.id
            created_at = row.created_at
        return int(run_id), created_at

    def _resolve_healthcheck_model(
        self,
        provider_cfg: AnalysisProviderConfig,
        requested_model: Optional[str],
    ) -> str:
        candidate = (requested_model or "").strip()
        if candidate:
            return candidate

        default_model = (self.config.analysis.default_model or "").strip()
        if default_model:
            return default_model

        if provider_cfg.models:
            first = provider_cfg.models[0]
            if isinstance(first, str):
                return first.strip()
        return ""

    def _resolve_fallback_model_for_provider(
        self,
        provider_cfg: AnalysisProviderConfig,
        preferred_model: Optional[str],
    ) -> str:
        candidate = (preferred_model or "").strip()
        if candidate and candidate in provider_cfg.models:
            return candidate

        if provider_cfg.models:
            first = provider_cfg.models[0]
            if isinstance(first, str):
                return first.strip()

        default_model = (self.config.analysis.default_model or "").strip()
        return default_model

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(0, int((time.perf_counter() - started) * 1000))

    def _to_history_item(self, row) -> StockAnalysisHistoryItem:
        parsed_output = parse_json(row.output_json) or {}
        return StockAnalysisHistoryItem(
            id=int(row.id),
            symbol=row.symbol,
            market=row.market,
            provider_id=row.provider_id,
            model=row.model,
            status=row.status,
            created_at=row.created_at,
            markdown=row.markdown,
            output_json=parsed_output,
        )
