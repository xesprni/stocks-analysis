from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from market_reporter.config import AnalysisProviderConfig, AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.core.types import AnalysisInput, AnalysisOutput, FlowPoint, NewsItem
from market_reporter.infra.db.repos import AnalysisProviderSecretRepo, StockAnalysisRunRepo
from market_reporter.infra.db.session import session_scope
from market_reporter.infra.security.crypto import decrypt_text, encrypt_text
from market_reporter.infra.security.keychain_store import KeychainStore
from market_reporter.modules.analysis_engine.providers.mock_provider import MockAnalysisProvider
from market_reporter.modules.analysis_engine.providers.openai_compatible_provider import OpenAICompatibleProvider
from market_reporter.modules.analysis_engine.schemas import AnalysisProviderView, StockAnalysisHistoryItem, StockAnalysisRunView
from market_reporter.modules.fund_flow.service import FundFlowService
from market_reporter.modules.market_data.service import MarketDataService
from market_reporter.modules.market_data.symbol_mapper import normalize_symbol
from market_reporter.modules.news.service import NewsService


class AnalysisService:
    MODULE_NAME = "analysis"

    def __init__(
        self,
        config: AppConfig,
        registry: ProviderRegistry,
        market_data_service: Optional[MarketDataService] = None,
        news_service: Optional[NewsService] = None,
        fund_flow_service: Optional[FundFlowService] = None,
        keychain_store: Optional[KeychainStore] = None,
    ) -> None:
        self.config = config
        self.registry = registry
        self.market_data_service = market_data_service
        self.news_service = news_service
        self.fund_flow_service = fund_flow_service
        self.keychain_store = keychain_store or KeychainStore()

        self.registry.register(self.MODULE_NAME, "mock", self._build_mock)
        self.registry.register(self.MODULE_NAME, "openai_compatible", self._build_openai_compatible)

    def _build_mock(self, provider_config: AnalysisProviderConfig):
        return MockAnalysisProvider()

    def _build_openai_compatible(self, provider_config: AnalysisProviderConfig):
        return OpenAICompatibleProvider(provider_config=provider_config)

    def list_providers(self) -> List[AnalysisProviderView]:
        providers = []
        with session_scope(self.config.database.url) as session:
            secret_repo = AnalysisProviderSecretRepo(session)
            for provider in self.config.analysis.providers:
                has_secret = secret_repo.get(provider.provider_id) is not None
                secret_required = provider.type != "mock"
                status, status_message, ready = self._evaluate_provider_state(
                    enabled=provider.enabled,
                    has_models=bool(provider.models),
                    secret_required=secret_required,
                    has_secret=has_secret,
                )
                providers.append(
                    AnalysisProviderView(
                        provider_id=provider.provider_id,
                        type=provider.type,
                        base_url=provider.base_url,
                        models=provider.models,
                        timeout=provider.timeout,
                        enabled=provider.enabled,
                        has_secret=has_secret,
                        secret_required=secret_required,
                        ready=ready,
                        status=status,
                        status_message=status_message,
                        is_default=provider.provider_id == self.config.analysis.default_provider,
                    )
                )
        return providers

    def put_secret(self, provider_id: str, api_key: str) -> None:
        provider = self._find_provider(provider_id)
        if provider.type == "mock":
            return

        master_key = self.keychain_store.get_or_create_master_key()
        ciphertext, nonce = encrypt_text(api_key, master_key)
        with session_scope(self.config.database.url) as session:
            repo = AnalysisProviderSecretRepo(session)
            repo.upsert(provider_id=provider_id, ciphertext=ciphertext, nonce=nonce)

    def delete_secret(self, provider_id: str) -> bool:
        with session_scope(self.config.database.url) as session:
            repo = AnalysisProviderSecretRepo(session)
            return repo.delete(provider_id=provider_id)

    def ensure_provider_ready(
        self,
        provider_id: str,
        model: Optional[str] = None,
    ) -> AnalysisProviderConfig:
        provider = self._find_provider(provider_id)
        has_secret = self._has_secret(provider.provider_id)
        _, status_message, ready = self._evaluate_provider_state(
            enabled=provider.enabled,
            has_models=bool(provider.models),
            secret_required=provider.type != "mock",
            has_secret=has_secret,
        )
        if not ready:
            raise ValueError(status_message)
        if model and provider.models and model not in provider.models:
            raise ValueError(f"Model not found in provider models: {model}")
        return provider

    async def run_stock_analysis(
        self,
        symbol: str,
        market: str,
        provider_id: Optional[str] = None,
        model: Optional[str] = None,
        interval: str = "5m",
        lookback_bars: int = 120,
    ) -> StockAnalysisRunView:
        provider_cfg, selected_model = self._select_provider_and_model(provider_id=provider_id, model=model)
        if self.market_data_service is None or self.news_service is None or self.fund_flow_service is None:
            raise ValueError("AnalysisService missing runtime dependencies for stock analysis")
        normalized_symbol = normalize_symbol(symbol=symbol, market=market)

        quote_task = self.market_data_service.get_quote(symbol=normalized_symbol, market=market)
        kline_task = self.market_data_service.get_kline(
            symbol=normalized_symbol,
            market=market,
            interval=interval,
            limit=lookback_bars,
        )
        curve_task = self.market_data_service.get_curve(symbol=normalized_symbol, market=market, window="1d")
        news_task = self.news_service.collect(limit=min(self.config.news_limit, 30))
        flow_task = self.fund_flow_service.collect(periods=min(self.config.flow_periods, 12))

        quote, kline, curve, news_result, flow_result = await asyncio.gather(
            quote_task,
            kline_task,
            curve_task,
            news_task,
            flow_task,
        )
        news_items, _ = news_result
        flow_series, _ = flow_result

        payload = AnalysisInput(
            symbol=normalized_symbol,
            market=market,
            quote=quote,
            kline=kline,
            curve=curve,
            news=news_items,
            fund_flow=flow_series,
            watch_meta={"interval": interval, "lookback_bars": lookback_bars},
        )

        output = await self._invoke_provider(provider_cfg=provider_cfg, model=selected_model, payload=payload)
        run_id, created_at = self._save_run(
            symbol=normalized_symbol,
            market=market,
            provider_id=provider_cfg.provider_id,
            model=selected_model,
            status="SUCCESS",
            payload=payload,
            output=output,
        )

        return StockAnalysisRunView(
            id=run_id,
            symbol=normalized_symbol,
            market=market,
            provider_id=provider_cfg.provider_id,
            model=selected_model,
            status="SUCCESS",
            output=output,
            markdown=output.markdown,
            created_at=created_at,
        )

    async def analyze_market_overview(
        self,
        news_items: List[NewsItem],
        flow_series: Dict[str, List[FlowPoint]],
    ) -> Tuple[AnalysisOutput, str, str]:
        provider_cfg, selected_model = self._select_provider_and_model(provider_id=None, model=None)
        payload = AnalysisInput(
            symbol="MARKET",
            market="GLOBAL",
            quote=None,
            kline=[],
            curve=[],
            news=news_items,
            fund_flow=flow_series,
            watch_meta={"mode": "overview"},
        )
        output = await self._invoke_provider(provider_cfg=provider_cfg, model=selected_model, payload=payload)
        return output, provider_cfg.provider_id, selected_model

    async def analyze_news_alert_batch(
        self,
        candidates: List[Dict[str, object]],
        provider_id: Optional[str] = None,
        model: Optional[str] = None,
    ) -> List[Dict[str, object]]:
        provider_cfg, selected_model = self._select_provider_and_model(provider_id=provider_id, model=model)
        payload = AnalysisInput(
            symbol="WATCHLIST_ALERTS",
            market="GLOBAL",
            quote=None,
            kline=[],
            curve=[],
            news=[],
            fund_flow={},
            watch_meta={
                "mode": "watchlist_news_listener",
                "candidates": candidates,
                "required_output": {
                    "alerts": [
                        {
                            "summary": "string",
                            "severity": "LOW|MEDIUM|HIGH",
                            "markdown": "string",
                            "reason": "string",
                        }
                    ]
                },
            },
        )
        output = await self._invoke_provider(provider_cfg=provider_cfg, model=selected_model, payload=payload)
        return self._extract_alerts(output=output, size=len(candidates))

    def list_history(self, symbol: str, market: str, limit: int = 20) -> List[StockAnalysisHistoryItem]:
        normalized_symbol = normalize_symbol(symbol=symbol, market=market)
        with session_scope(self.config.database.url) as session:
            repo = StockAnalysisRunRepo(session)
            rows = repo.list_by_symbol(symbol=normalized_symbol, market=market.upper(), limit=limit)
        result: List[StockAnalysisHistoryItem] = []
        for row in rows:
            parsed_output = self._parse_json(row.output_json)
            result.append(
                StockAnalysisHistoryItem(
                    id=row.id,
                    symbol=row.symbol,
                    market=row.market,
                    provider_id=row.provider_id,
                    model=row.model,
                    status=row.status,
                    created_at=row.created_at,
                    markdown=row.markdown,
                    output_json=parsed_output,
                )
            )
        return result

    async def _invoke_provider(
        self,
        provider_cfg: AnalysisProviderConfig,
        model: str,
        payload: AnalysisInput,
    ) -> AnalysisOutput:
        provider = self.registry.resolve(
            self.MODULE_NAME,
            provider_cfg.type,
            provider_config=provider_cfg,
        )
        api_key = self._resolve_api_key(provider_cfg=provider_cfg)
        return await provider.analyze(payload=payload, model=model, api_key=api_key)

    def _resolve_api_key(self, provider_cfg: AnalysisProviderConfig) -> Optional[str]:
        if provider_cfg.type == "mock":
            return None
        with session_scope(self.config.database.url) as session:
            secret_repo = AnalysisProviderSecretRepo(session)
            secret = secret_repo.get(provider_cfg.provider_id)
        if secret is None:
            return None

        master_key = self.keychain_store.get_or_create_master_key()
        return decrypt_text(secret.key_ciphertext, secret.nonce, master_key)

    def _has_secret(self, provider_id: str) -> bool:
        with session_scope(self.config.database.url) as session:
            secret_repo = AnalysisProviderSecretRepo(session)
            return secret_repo.get(provider_id) is not None

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
        provider_map = self.config.analysis_provider_map()
        selected_provider_id = provider_id or self.config.analysis.default_provider
        if selected_provider_id not in provider_map:
            raise ValueError(f"Selected provider not enabled: {selected_provider_id}")
        provider_cfg = provider_map[selected_provider_id]

        selected_model = model or self.config.analysis.default_model
        if selected_model not in provider_cfg.models and provider_cfg.models:
            selected_model = provider_cfg.models[0]
        return provider_cfg, selected_model

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
            )
            run_id = row.id
            created_at = row.created_at
        return int(run_id), created_at

    @staticmethod
    def _parse_json(raw: str) -> Dict[str, object]:
        try:
            return json.loads(raw)
        except Exception:
            return {}

    @staticmethod
    def _evaluate_provider_state(
        enabled: bool,
        has_models: bool,
        secret_required: bool,
        has_secret: bool,
    ) -> Tuple[str, str, bool]:
        if not enabled:
            return "disabled", "Provider is disabled in config.", False
        if not has_models:
            return "no-model", "No available models configured for this provider.", False
        if secret_required and not has_secret:
            return "missing-secret", "Provider API key is not configured.", False
        return "ready", "Provider is ready to use.", True

    @staticmethod
    def _extract_alerts(output: AnalysisOutput, size: int) -> List[Dict[str, object]]:
        raw_alerts: List[Any] = []
        if isinstance(output.raw, dict):
            alerts = output.raw.get("alerts")
            if isinstance(alerts, list):
                raw_alerts = alerts

        parsed: List[Dict[str, object]] = []
        for item in raw_alerts:
            if not isinstance(item, dict):
                continue
            parsed.append(
                {
                    "summary": str(item.get("summary") or output.summary),
                    "severity": str(item.get("severity") or "MEDIUM").upper(),
                    "markdown": str(item.get("markdown") or item.get("summary") or output.markdown),
                    "reason": str(item.get("reason") or ""),
                    "raw": item,
                }
            )

        if parsed:
            if len(parsed) >= size:
                return parsed[:size]
            while len(parsed) < size:
                parsed.append(parsed[-1])
            return parsed

        fallback = {
            "summary": output.summary,
            "severity": "MEDIUM",
            "markdown": output.markdown or output.summary,
            "reason": "",
            "raw": output.raw,
        }
        return [fallback for _ in range(size)]
