"""FastAPI dependency factories for service injection."""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, Request

from market_reporter.api.auth import CurrentUser, require_user
from market_reporter.config import AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.infra.db.session import init_db
from market_reporter.infra.http.client import HttpClient
from market_reporter.modules.analysis.service import AnalysisService
from market_reporter.modules.fund_flow.service import FundFlowService
from market_reporter.modules.market_data.service import MarketDataService
from market_reporter.modules.news.service import NewsService
from market_reporter.modules.news_listener.service import NewsListenerService
from market_reporter.modules.reports.service import ReportService
from market_reporter.modules.symbol_search.service import SymbolSearchService
from market_reporter.modules.watchlist.service import WatchlistService
from market_reporter.services.config_store import ConfigStore
from market_reporter.services.user_config_store import UserConfigStore
from market_reporter.settings import AppSettings


def get_config_store(request: Request) -> ConfigStore:
    return request.app.state.config_store


def get_effective_user_id(user: CurrentUser) -> Optional[int]:
    user_id = int(getattr(user, "user_id", 0) or 0)
    return user_id if user_id > 0 else None


def get_user_config_store(
    request: Request,
    user: CurrentUser = Depends(require_user),
) -> UserConfigStore:
    settings: AppSettings = request.app.state.settings
    global_store: ConfigStore = request.app.state.config_store
    effective_user_id = get_effective_user_id(user)
    store = UserConfigStore(
        database_url=global_store.load().database.url,
        global_config_path=settings.config_file,
        user_id=effective_user_id,
    )
    if effective_user_id is not None and not store.has_user_config():
        store.init_from_global()
    return store


def get_user_config(
    store: UserConfigStore = Depends(get_user_config_store),
) -> AppConfig:
    return store.load()


def get_settings(request: Request) -> AppSettings:
    return request.app.state.settings


def get_report_service(request: Request) -> ReportService:
    return request.app.state.report_service


def get_config(request: Request) -> AppConfig:
    config_store: ConfigStore = request.app.state.config_store
    return config_store.load()


def ensure_database(config: AppConfig) -> None:
    init_db(config.database.url)


def get_registry() -> ProviderRegistry:
    return ProviderRegistry()


def get_watchlist_service(config: AppConfig) -> WatchlistService:
    return WatchlistService(config)


def get_symbol_search_service(
    config: AppConfig, registry: ProviderRegistry | None = None
) -> SymbolSearchService:
    return SymbolSearchService(config=config, registry=registry or ProviderRegistry())


def get_market_data_service(
    config: AppConfig, registry: ProviderRegistry | None = None
) -> MarketDataService:
    return MarketDataService(config=config, registry=registry or ProviderRegistry())


def get_analysis_service(
    config: AppConfig,
    registry: ProviderRegistry | None = None,
    market_data_service: MarketDataService | None = None,
    news_service: NewsService | None = None,
    fund_flow_service: FundFlowService | None = None,
) -> AnalysisService:
    reg = registry or ProviderRegistry()
    return AnalysisService(
        config=config,
        registry=reg,
        market_data_service=market_data_service,
        news_service=news_service,
        fund_flow_service=fund_flow_service,
    )


def build_listener_query_service(config: AppConfig) -> NewsListenerService:
    registry = ProviderRegistry()
    market_data_service = MarketDataService(config=config, registry=registry)
    watchlist_service = WatchlistService(config)
    analysis_service = AnalysisService(
        config=config,
        registry=registry,
        market_data_service=market_data_service,
    )
    return NewsListenerService(
        config=config,
        registry=registry,
        news_service=None,
        watchlist_service=watchlist_service,
        market_data_service=market_data_service,
        analysis_service=analysis_service,
    )


def build_http_client(config: AppConfig) -> HttpClient:
    return HttpClient(
        timeout_seconds=config.request_timeout_seconds,
        user_agent=config.user_agent,
    )
