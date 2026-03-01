from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from typing import Any, Dict, List, Optional, Tuple

from market_reporter.config import AnalysisProviderConfig, AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.core.utils import parse_json
from market_reporter.core.types import (
    AnalysisInput,
    AnalysisOutput,
    FlowPoint,
    NewsItem,
)
from market_reporter.infra.db.repos import (
    AnalysisProviderAccountRepo,
    AnalysisProviderAuthStateRepo,
    AnalysisProviderSecretRepo,
    StockAnalysisRunRepo,
)
from market_reporter.infra.db.session import session_scope
from market_reporter.infra.security.crypto import decrypt_text, encrypt_text
from market_reporter.infra.security.keychain_store import KeychainStore
from market_reporter.modules.analysis.providers.codex_app_server_provider import (
    CodexAppServerProvider,
)
from market_reporter.modules.analysis.providers.mock_provider import (
    MockAnalysisProvider,
)
from market_reporter.modules.analysis.providers.openai_compatible_provider import (
    OpenAICompatibleProvider,
)
from market_reporter.modules.analysis.schemas import (
    AnalysisProviderView,
    ProviderAuthStartResponse,
    ProviderAuthStatusView,
    ProviderModelsView,
    StockAnalysisHistoryItem,
    StockAnalysisRunView,
)
from market_reporter.modules.analysis.agent.schemas import AgentRunRequest
from market_reporter.modules.analysis.agent.service import AgentService
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
        user_id: Optional[int] = None,
        market_data_service: Optional[MarketDataService] = None,
        news_service: Optional[NewsService] = None,
        fund_flow_service: Optional[FundFlowService] = None,
        keychain_store: Optional[KeychainStore] = None,
    ) -> None:
        self.config = config
        self.registry = registry
        self.user_id = user_id
        self.market_data_service = market_data_service
        self.news_service = news_service
        self.fund_flow_service = fund_flow_service
        self.keychain_store = keychain_store or KeychainStore(
            database_url=config.database.url
        )

        # Register provider factories by type; actual instances are created per invocation.
        self.registry.register(self.MODULE_NAME, "mock", self._build_mock)
        self.registry.register(
            self.MODULE_NAME, "openai_compatible", self._build_openai_compatible
        )
        self.registry.register(
            self.MODULE_NAME, "codex_app_server", self._build_codex_app_server
        )

    def _build_mock(self, provider_config: AnalysisProviderConfig):
        return MockAnalysisProvider()

    def _build_openai_compatible(self, provider_config: AnalysisProviderConfig):
        return OpenAICompatibleProvider(provider_config=provider_config)

    def _build_codex_app_server(self, provider_config: AnalysisProviderConfig):
        return CodexAppServerProvider(provider_config=provider_config)

    def list_providers(self) -> List[AnalysisProviderView]:
        providers = []
        with session_scope(self.config.database.url) as session:
            secret_repo = AnalysisProviderSecretRepo(session)
            account_repo = AnalysisProviderAccountRepo(session)
            # Readiness state is derived from config + secret presence + OAuth connection.
            for provider in self.config.analysis.providers:
                auth_mode = self._resolve_auth_mode(provider)
                has_secret = (
                    secret_repo.get(
                        provider.provider_id,
                        user_id=self.user_id,
                    )
                    is not None
                )
                account = account_repo.get(
                    provider.provider_id,
                    user_id=self.user_id,
                )
                credential_expires_at = account.expires_at if account else None
                connected = self._is_account_connected(account)
                secret_required = auth_mode == "api_key"
                base_url_required = provider.type not in {"mock", "codex_app_server"}
                has_base_url = (
                    bool((provider.base_url or "").strip())
                    if base_url_required
                    else True
                )
                status, status_message, ready = self._evaluate_provider_state(
                    enabled=provider.enabled,
                    has_models=bool(provider.models),
                    secret_required=secret_required,
                    has_secret=has_secret,
                    auth_mode=auth_mode,
                    connected=connected,
                    base_url_required=base_url_required,
                    has_base_url=has_base_url,
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
                        is_default=provider.provider_id
                        == self.config.analysis.default_provider,
                        auth_mode=auth_mode,
                        connected=connected,
                        credential_expires_at=credential_expires_at,
                    )
                )
        return providers

    def put_secret(self, provider_id: str, api_key: str) -> None:
        provider = self._find_provider(provider_id)
        auth_mode = self._resolve_auth_mode(provider)
        if auth_mode == "none":
            return
        if auth_mode != "api_key":
            raise ValueError(
                f"Provider does not use API key authentication: {provider.provider_id}"
            )

        master_key = self.keychain_store.get_or_create_master_key()
        # Persist encrypted API key material only; plaintext never touches DB.
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

    async def start_provider_auth(
        self,
        provider_id: str,
        callback_url: str,
        redirect_to: Optional[str] = None,
    ) -> ProviderAuthStartResponse:
        provider_cfg = self._find_provider(provider_id)
        auth_mode = self._resolve_auth_mode(provider_cfg)
        if auth_mode != "chatgpt_oauth":
            raise ValueError(f"Provider does not support OAuth login: {provider_id}")

        state = uuid4().hex
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=provider_cfg.login_timeout_seconds)
        with session_scope(self.config.database.url) as session:
            state_repo = AnalysisProviderAuthStateRepo(session)
            state_repo.delete_expired(now, user_id=self.user_id)
            # Store one-time state to validate callback origin and expiry.
            state_repo.create(
                state=state,
                provider_id=provider_cfg.provider_id,
                redirect_to=redirect_to,
                expires_at=expires_at,
                user_id=self.user_id,
            )

        provider = self.registry.resolve(
            self.MODULE_NAME,
            provider_cfg.type,
            provider_config=provider_cfg,
        )
        payload = await provider.start_login(
            state=state,
            callback_url=self._resolve_callback_url(
                provider_cfg=provider_cfg, fallback=callback_url
            ),
            redirect_to=redirect_to,
        )
        auth_url = str(payload.get("auth_url") or "").strip()
        if not auth_url:
            raise ValueError("Login start failed: missing auth_url from provider.")
        return ProviderAuthStartResponse(
            provider_id=provider_id,
            auth_url=auth_url,
            state=state,
            expires_at=expires_at,
        )

    async def complete_provider_auth(
        self,
        provider_id: str,
        state: str,
        code: Optional[str],
        callback_url: str,
        query_params: Optional[Dict[str, str]] = None,
    ) -> ProviderAuthStatusView:
        provider_cfg = self._find_provider(provider_id)
        auth_mode = self._resolve_auth_mode(provider_cfg)
        if auth_mode != "chatgpt_oauth":
            raise ValueError(f"Provider does not support OAuth login: {provider_id}")
        now = datetime.utcnow()
        with session_scope(self.config.database.url) as session:
            state_repo = AnalysisProviderAuthStateRepo(session)
            auth_state = state_repo.get_valid(
                state=state,
                provider_id=provider_cfg.provider_id,
                now=now,
                user_id=self.user_id,
            )
            if auth_state is None:
                raise ValueError("Login callback state is invalid or expired.")
            # State is single-use to prevent callback replay.
            state_repo.mark_used(auth_state)

        provider = self.registry.resolve(
            self.MODULE_NAME,
            provider_cfg.type,
            provider_config=provider_cfg,
        )
        token_payload = await provider.complete_login(
            code=code,
            state=state,
            callback_url=self._resolve_callback_url(
                provider_cfg=provider_cfg, fallback=callback_url
            ),
            query_params=query_params or {},
        )
        access_token = str(token_payload.get("access_token") or "").strip()
        if not access_token:
            raise ValueError("Login callback did not return access token.")

        expires_at = provider.normalize_expires_at(
            expires_at=self._to_optional_string(token_payload.get("expires_at")),
            expires_in=self._to_optional_float(token_payload.get("expires_in")),
        )
        credential_payload = {
            "access_token": access_token,
            "refresh_token": self._to_optional_string(
                token_payload.get("refresh_token")
            ),
            "token_type": self._to_optional_string(token_payload.get("token_type"))
            or "Bearer",
        }
        master_key = self.keychain_store.get_or_create_master_key()
        # OAuth credential payload is encrypted before persistence.
        ciphertext, nonce = encrypt_text(
            json.dumps(credential_payload, ensure_ascii=False), master_key
        )
        with session_scope(self.config.database.url) as session:
            account_repo = AnalysisProviderAccountRepo(session)
            account_repo.upsert(
                provider_id=provider_cfg.provider_id,
                account_type="chatgpt",
                credential_ciphertext=ciphertext,
                nonce=nonce,
                expires_at=expires_at,
                user_id=self.user_id,
            )
        return await self.get_provider_auth_status(provider_id=provider_id)

    async def get_provider_auth_status(
        self, provider_id: str
    ) -> ProviderAuthStatusView:
        provider_cfg = self._find_provider(provider_id)
        auth_mode = self._resolve_auth_mode(provider_cfg)
        if auth_mode == "none":
            return ProviderAuthStatusView(
                provider_id=provider_id,
                auth_mode=auth_mode,
                connected=True,
                status="ready",
                message="No authentication required.",
            )
        if auth_mode == "chatgpt_oauth":
            if provider_cfg.type == "codex_app_server":
                provider = self.registry.resolve(
                    self.MODULE_NAME,
                    provider_cfg.type,
                    provider_config=provider_cfg,
                )
                status_payload = await provider.get_auth_status()
                connected = bool(status_payload.get("connected"))
                message = str(status_payload.get("message") or "")
                # Mirror external connection state into local marker row for UI consistency.
                self._sync_oauth_connection_marker(
                    provider_id=provider_id,
                    connected=connected,
                    marker_payload=status_payload.get("raw"),
                )
                return ProviderAuthStatusView(
                    provider_id=provider_id,
                    auth_mode=auth_mode,
                    connected=connected,
                    status="connected" if connected else "disconnected",
                    message=message
                    or (
                        "Connected."
                        if connected
                        else "Provider account is not connected."
                    ),
                    expires_at=None,
                )
            account = self._get_account(provider_id=provider_cfg.provider_id)
            connected = self._is_account_connected(account)
            if account is None:
                return ProviderAuthStatusView(
                    provider_id=provider_id,
                    auth_mode=auth_mode,
                    connected=False,
                    status="disconnected",
                    message="Provider account is not connected.",
                )
            if connected:
                return ProviderAuthStatusView(
                    provider_id=provider_id,
                    auth_mode=auth_mode,
                    connected=True,
                    status="connected",
                    message="Connected.",
                    expires_at=account.expires_at,
                )
            return ProviderAuthStatusView(
                provider_id=provider_id,
                auth_mode=auth_mode,
                connected=False,
                status="expired",
                message="Login credential expired.",
                expires_at=account.expires_at,
            )

        has_secret = self._has_secret(provider_cfg.provider_id)
        return ProviderAuthStatusView(
            provider_id=provider_id,
            auth_mode=auth_mode,
            connected=has_secret,
            status="connected" if has_secret else "missing-secret",
            message="API key is configured." if has_secret else "API key is missing.",
        )

    async def logout_provider_auth(self, provider_id: str) -> bool:
        provider_cfg = self._find_provider(provider_id)
        auth_mode = self._resolve_auth_mode(provider_cfg)
        if auth_mode == "chatgpt_oauth":
            external_deleted = False
            if provider_cfg.type == "codex_app_server":
                provider = self.registry.resolve(
                    self.MODULE_NAME,
                    provider_cfg.type,
                    provider_config=provider_cfg,
                )
                external_deleted = bool(await provider.logout())
            with session_scope(self.config.database.url) as session:
                repo = AnalysisProviderAccountRepo(session)
                deleted = repo.delete(provider_id=provider_id, user_id=self.user_id)
            return bool(external_deleted or deleted)
        with session_scope(self.config.database.url) as session:
            repo = AnalysisProviderSecretRepo(session)
            return repo.delete(provider_id=provider_id, user_id=self.user_id)

    async def list_provider_models(self, provider_id: str) -> ProviderModelsView:
        provider_cfg = self._find_provider(provider_id)
        auth_mode = self._resolve_auth_mode(provider_cfg)
        if provider_cfg.type == "codex_app_server" and auth_mode == "chatgpt_oauth":
            provider = self.registry.resolve(
                self.MODULE_NAME,
                provider_cfg.type,
                provider_config=provider_cfg,
            )
            try:
                models = await provider.list_models(access_token=None)
                if models:
                    return ProviderModelsView(
                        provider_id=provider_id,
                        models=models,
                        source="remote",
                    )
            except Exception:
                pass
        return ProviderModelsView(
            provider_id=provider_id,
            models=provider_cfg.models,
            source="config",
        )

    def ensure_provider_ready(
        self,
        provider_id: str,
        model: Optional[str] = None,
    ) -> AnalysisProviderConfig:
        provider = self._find_provider(provider_id)
        auth_mode = self._resolve_auth_mode(provider)
        has_secret = self._has_secret(provider.provider_id)
        connected = self._has_connected_account(provider.provider_id)
        base_url_required = provider.type not in {"mock", "codex_app_server"}
        has_base_url = (
            bool((provider.base_url or "").strip()) if base_url_required else True
        )
        _, status_message, ready = self._evaluate_provider_state(
            enabled=provider.enabled,
            has_models=bool(provider.models),
            secret_required=auth_mode == "api_key",
            has_secret=has_secret,
            auth_mode=auth_mode,
            connected=connected,
            base_url_required=base_url_required,
            has_base_url=has_base_url,
        )
        if not ready:
            raise ValueError(status_message)
        is_dynamic_model_provider = self._resolve_auth_mode(provider) == "chatgpt_oauth"
        # Static providers enforce model whitelist; OAuth providers may expose dynamic models.
        if (
            model
            and provider.models
            and model not in provider.models
            and not is_dynamic_model_provider
        ):
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
        if self.news_service is None or self.fund_flow_service is None:
            raise ValueError(
                "AnalysisService missing runtime dependencies for stock analysis"
            )
        normalized_symbol = normalize_symbol(symbol=symbol, market=market)

        agent_service = AgentService(
            config=self.config,
            registry=self.registry,
            news_service=self.news_service,
            fund_flow_service=self.fund_flow_service,
        )
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
            access_token=access_token,
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
    ) -> Tuple[AnalysisProviderConfig, str, Optional[str], Optional[str]]:
        """Select a provider and resolve its credentials.

        Returns ``(provider_cfg, selected_model, api_key, access_token)``.
        This is the public entry-point for callers that need to construct an
        ``AgentService`` without going through ``run_stock_analysis``.
        """
        provider_cfg, selected_model = self._select_provider_and_model(
            provider_id=provider_id, model=model
        )
        auth_mode = self._resolve_auth_mode(provider_cfg)
        api_key: Optional[str] = None
        access_token: Optional[str] = None
        if provider_cfg.type == "codex_app_server":
            access_token = None
        elif auth_mode == "chatgpt_oauth":
            access_token = self._resolve_access_token(provider_cfg=provider_cfg)
        elif auth_mode == "api_key":
            api_key = self._resolve_api_key(provider_cfg=provider_cfg)
        return provider_cfg, selected_model, api_key, access_token

    async def analyze_news_alert_batch(
        self,
        candidates: List[Dict[str, object]],
        provider_id: Optional[str] = None,
        model: Optional[str] = None,
    ) -> List[Dict[str, object]]:
        provider_cfg, selected_model = self._select_provider_and_model(
            provider_id=provider_id, model=model
        )
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
                # Contract hints help keep provider output parseable and stable.
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
        output = await self._invoke_provider(
            provider_cfg=provider_cfg, model=selected_model, payload=payload
        )
        return self._extract_alerts(output=output, size=len(candidates))

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
        auth_mode = self._resolve_auth_mode(provider_cfg)
        # Dispatch credentials based on provider auth mode.
        if provider_cfg.type == "codex_app_server":
            return await provider.analyze(
                payload=payload,
                model=model,
                access_token=None,
            )
        if auth_mode == "chatgpt_oauth":
            access_token = self._resolve_access_token(provider_cfg=provider_cfg)
            return await provider.analyze(
                payload=payload,
                model=model,
                access_token=access_token,
            )
        api_key = self._resolve_api_key(provider_cfg=provider_cfg)
        return await provider.analyze(payload=payload, model=model, api_key=api_key)

    def _resolve_api_key(self, provider_cfg: AnalysisProviderConfig) -> Optional[str]:
        if self._resolve_auth_mode(provider_cfg) != "api_key":
            return None
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
        # Decrypt only at call time to keep key exposure window short.
        return decrypt_text(key_ciphertext, nonce, master_key)

    def _resolve_access_token(
        self, provider_cfg: AnalysisProviderConfig
    ) -> Optional[str]:
        if self._resolve_auth_mode(provider_cfg) != "chatgpt_oauth":
            return None
        account = self._get_account(provider_id=provider_cfg.provider_id)
        if account is None:
            return None
        if not self._is_account_connected(account):
            return None
        master_key = self.keychain_store.get_or_create_master_key()
        # Stored credentials are JSON blob encrypted with local master key.
        raw = decrypt_text(account.credential_ciphertext, account.nonce, master_key)
        try:
            payload = json.loads(raw)
        except Exception:
            return None
        token = payload.get("access_token")
        if isinstance(token, str) and token.strip():
            return token.strip()
        return None

    def _has_secret(self, provider_id: str) -> bool:
        with session_scope(self.config.database.url) as session:
            secret_repo = AnalysisProviderSecretRepo(session)
            return secret_repo.get(provider_id, user_id=self.user_id) is not None

    def _has_connected_account(self, provider_id: str) -> bool:
        account = self._get_account(provider_id=provider_id)
        return self._is_account_connected(account)

    def _get_account(self, provider_id: str):
        with session_scope(self.config.database.url) as session:
            repo = AnalysisProviderAccountRepo(session)
            account = repo.get(provider_id=provider_id, user_id=self.user_id)
            if account is not None:
                session.expunge(account)
            return account

    def _sync_oauth_connection_marker(
        self,
        provider_id: str,
        connected: bool,
        marker_payload: Optional[object] = None,
    ) -> None:
        with session_scope(self.config.database.url) as session:
            repo = AnalysisProviderAccountRepo(session)
            if not connected:
                repo.delete(provider_id=provider_id, user_id=self.user_id)
                return

            try:
                master_key = self.keychain_store.get_or_create_master_key()
                payload = {
                    "provider_id": provider_id,
                    "marker_type": "codex_app_server",
                    "connected": True,
                    "payload": marker_payload
                    if isinstance(marker_payload, dict)
                    else {},
                }
                ciphertext, nonce = encrypt_text(
                    json.dumps(payload, ensure_ascii=False), master_key
                )
                repo.upsert(
                    provider_id=provider_id,
                    account_type="chatgpt",
                    credential_ciphertext=ciphertext,
                    nonce=nonce,
                    expires_at=None,
                    user_id=self.user_id,
                )
            except Exception:
                # This marker does not contain secrets; keep provider status functional even if keychain is unavailable.
                repo.upsert(
                    provider_id=provider_id,
                    account_type="chatgpt",
                    credential_ciphertext='{"marker_type":"codex_app_server","connected":true}',
                    nonce="plain",
                    expires_at=None,
                    user_id=self.user_id,
                )

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
                # Auto-fallback to first enabled provider for default path.
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
        is_dynamic_model_provider = (
            self._resolve_auth_mode(provider_cfg) == "chatgpt_oauth"
        )
        if (
            not is_dynamic_model_provider
            and selected_model not in provider_cfg.models
            and provider_cfg.models
        ):
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
                user_id=self.user_id,
            )
            run_id = row.id
            created_at = row.created_at
        return int(run_id), created_at

    @staticmethod
    def _resolve_auth_mode(provider_cfg: AnalysisProviderConfig) -> str:
        if provider_cfg.auth_mode:
            return provider_cfg.auth_mode
        if provider_cfg.type == "mock":
            return "none"
        if provider_cfg.type == "codex_app_server":
            return "chatgpt_oauth"
        return "api_key"

    @staticmethod
    def _resolve_callback_url(
        provider_cfg: AnalysisProviderConfig, fallback: str
    ) -> str:
        if provider_cfg.login_callback_url and provider_cfg.login_callback_url.strip():
            return provider_cfg.login_callback_url.strip()
        return fallback

    @staticmethod
    def _is_account_connected(account) -> bool:
        if account is None:
            return False
        expires_at = getattr(account, "expires_at", None)
        if expires_at is None:
            return True
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return expires_at >= now

    @staticmethod
    def _to_optional_string(value: object) -> Optional[str]:
        if isinstance(value, str):
            value = value.strip()
            if value:
                return value
        return None

    @staticmethod
    def _to_optional_float(value: object) -> Optional[float]:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.strip())
            except ValueError:
                return None
        return None

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

    @staticmethod
    def _evaluate_provider_state(
        enabled: bool,
        has_models: bool,
        secret_required: bool,
        has_secret: bool,
        auth_mode: str,
        connected: bool,
        base_url_required: bool,
        has_base_url: bool,
    ) -> Tuple[str, str, bool]:
        if not enabled:
            return "disabled", "Provider is disabled in config.", False
        if not has_models:
            return (
                "no-model",
                "No available models configured for this provider.",
                False,
            )
        if base_url_required and not has_base_url:
            return "missing-base-url", "Provider base_url is not configured.", False
        if auth_mode == "chatgpt_oauth" and not connected:
            return "login-required", "Provider account login is required.", False
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
                    "markdown": str(
                        item.get("markdown") or item.get("summary") or output.markdown
                    ),
                    "reason": str(item.get("reason") or ""),
                    "raw": item,
                }
            )

        if parsed:
            if len(parsed) >= size:
                return parsed[:size]
            # Pad short outputs so caller can index alerts by original candidate order.
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
