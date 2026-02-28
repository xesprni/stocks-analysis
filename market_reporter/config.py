from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class NewsSource(BaseModel):
    source_id: Optional[str] = None
    name: str
    category: str
    url: str
    enabled: bool = True


class FredSeries(BaseModel):
    key: str
    display_name: str
    series_id: str
    unit: str
    market: str


class ModuleNewsConfig(BaseModel):
    default_provider: str = "rss"


class ModuleFundFlowConfig(BaseModel):
    providers: List[str] = Field(default_factory=lambda: ["eastmoney", "fred"])


class ModuleMarketDataConfig(BaseModel):
    default_provider: str = "longbridge"
    poll_seconds: int = Field(default=5, ge=3, le=30)


class ModuleNewsListenerConfig(BaseModel):
    default_provider: str = "watchlist_listener"


class ModuleSymbolSearchConfig(BaseModel):
    default_provider: str = "longbridge"


class ModulesConfig(BaseModel):
    news: ModuleNewsConfig = Field(default_factory=ModuleNewsConfig)
    fund_flow: ModuleFundFlowConfig = Field(default_factory=ModuleFundFlowConfig)
    market_data: ModuleMarketDataConfig = Field(default_factory=ModuleMarketDataConfig)
    news_listener: ModuleNewsListenerConfig = Field(
        default_factory=ModuleNewsListenerConfig
    )
    symbol_search: ModuleSymbolSearchConfig = Field(
        default_factory=ModuleSymbolSearchConfig
    )


class AnalysisProviderConfig(BaseModel):
    provider_id: str
    type: str = "openai_compatible"
    base_url: str = "https://api.openai.com/v1"
    models: List[str] = Field(default_factory=lambda: ["gpt-4o-mini"])
    timeout: int = Field(default=20, ge=3, le=120)
    enabled: bool = True
    auth_mode: Optional[str] = None
    login_callback_url: Optional[str] = None
    login_timeout_seconds: int = Field(default=600, ge=60, le=3600)


class AnalysisConfig(BaseModel):
    default_provider: str = "mock"
    default_model: str = "market-default"
    providers: List[AnalysisProviderConfig] = Field(default_factory=list)


class WatchlistConfig(BaseModel):
    default_market_scope: List[str] = Field(default_factory=lambda: ["CN", "HK", "US"])


class NewsListenerConfig(BaseModel):
    enabled: bool = True
    interval_minutes: int = Field(default=15, ge=5, le=120)
    move_window_minutes: int = Field(default=15, ge=5, le=120)
    move_threshold_percent: float = Field(default=2.0, ge=0.1, le=20.0)
    max_news_per_cycle: int = Field(default=120, ge=10, le=500)
    analysis_provider: Optional[str] = None
    analysis_model: Optional[str] = None


class SymbolSearchConfig(BaseModel):
    default_provider: str = "longbridge"
    max_results: int = Field(default=20, ge=5, le=100)


class DashboardIndexConfig(BaseModel):
    symbol: str
    market: str = Field(default="US", pattern="^(CN|HK|US)$")
    alias: Optional[str] = None
    enabled: bool = True


class DashboardConfig(BaseModel):
    indices: List[DashboardIndexConfig] = Field(
        default_factory=lambda: [
            DashboardIndexConfig(symbol="^GSPC", market="US", alias="S&P 500"),
            DashboardIndexConfig(symbol="^IXIC", market="US", alias="NASDAQ"),
            DashboardIndexConfig(symbol="^DJI", market="US", alias="Dow Jones"),
        ]
    )
    auto_refresh_enabled: bool = True
    auto_refresh_seconds: int = Field(default=15, ge=3, le=300)


class AgentConfig(BaseModel):
    enabled: bool = True
    max_steps: int = Field(default=8, ge=1, le=30)
    max_tool_calls: int = Field(default=12, ge=1, le=50)
    consistency_tolerance: float = Field(default=0.05, ge=0.0, le=1.0)
    default_news_window_days: int = Field(default=30, ge=1, le=3650)
    default_filing_window_days: int = Field(default=365, ge=1, le=3650)
    default_price_window_days: int = Field(default=365, ge=1, le=3650)


class LongbridgeConfig(BaseModel):
    enabled: bool = False
    app_key: str = ""
    app_secret: str = ""
    access_token: str = ""


class TelegramConfig(BaseModel):
    enabled: bool = False
    chat_id: str = ""
    bot_token: str = ""
    timeout_seconds: int = Field(default=10, ge=3, le=60)


class DatabaseConfig(BaseModel):
    url: str = "sqlite:///data/market_reporter.db"


def default_news_sources() -> List[NewsSource]:
    return [
        NewsSource(
            source_id="yahoo-finance-top-stories",
            name="Yahoo Finance Top Stories",
            category="finance",
            url="https://finance.yahoo.com/news/rssindex",
            enabled=True,
        ),
        NewsSource(
            source_id="federal-reserve-monetary-policy",
            name="Federal Reserve Monetary Policy",
            category="policy",
            url="https://www.federalreserve.gov/feeds/press_monetary.xml",
            enabled=True,
        ),
        NewsSource(
            source_id="investing-com",
            name="investing.com",
            category="finance",
            url="https://www.investing.com/rss/news_14.rss",
            enabled=True,
        ),
        NewsSource(
            source_id="federalreserve",
            name="federalreserve",
            category="finance",
            url="https://www.federalreserve.gov/feeds/press_all.xml",
            enabled=True,
        ),
        NewsSource(
            source_id="us-congress",
            name="us-congress",
            category="policy",
            url="https://www.congress.gov/rss/notification.xml",
            enabled=True,
        ),
        NewsSource(
            source_id="us-sec",
            name="us-sec",
            category="finance",
            url="https://www.sec.gov/news/pressreleases.rss",
            enabled=True,
        ),
    ]


def default_fred_series() -> List[FredSeries]:
    return [
        FredSeries(
            key="us_equity_mutual_fund_flow",
            display_name="美国共同基金股票资产交易额",
            series_id="BOGZ1FU483081005Q",
            unit="十亿美元",
            market="US",
        ),
        FredSeries(
            key="us_equity_etf_flow",
            display_name="美国ETF股票资产交易额",
            series_id="BOGZ1FU573064105Q",
            unit="十亿美元",
            market="US",
        ),
    ]


def default_analysis_providers() -> List[AnalysisProviderConfig]:
    return [
        AnalysisProviderConfig(
            provider_id="mock",
            type="mock",
            base_url="",
            models=["market-default"],
            timeout=5,
            enabled=True,
            auth_mode="none",
        ),
        AnalysisProviderConfig(
            provider_id="openai_compatible",
            type="openai_compatible",
            base_url="https://api.openai.com/v1",
            models=["gpt-4o-mini", "gpt-4.1"],
            timeout=30,
            enabled=True,
            auth_mode="api_key",
        ),
        AnalysisProviderConfig(
            provider_id="codex_app_server",
            type="codex_app_server",
            base_url="",
            models=["gpt-5-codex"],
            timeout=30,
            enabled=False,
            auth_mode="chatgpt_oauth",
        ),
        AnalysisProviderConfig(
            provider_id="glm_coding_plan",
            type="openai_compatible",
            base_url="https://api.z.ai/api/coding/paas/v4",
            models=["glm-5"],
            timeout=60,
            enabled=True,
            auth_mode="api_key",
        ),
    ]


FRED_SERIES: List[FredSeries] = default_fred_series()
EASTMONEY_FLOW_URL = "https://push2his.eastmoney.com/api/qt/kamt.kline/get"
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


class AppConfig(BaseModel):
    output_root: Path = Path("output")
    config_file: Path = Path("config/settings.yaml")
    timezone: str = "Asia/Shanghai"
    news_limit: int = Field(default=20, ge=1, le=100)
    flow_periods: int = Field(default=12, ge=1, le=120)
    request_timeout_seconds: int = Field(default=20, ge=3, le=120)
    user_agent: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    modules: ModulesConfig = Field(default_factory=ModulesConfig)
    analysis: AnalysisConfig = Field(
        default_factory=lambda: AnalysisConfig(providers=default_analysis_providers())
    )
    watchlist: WatchlistConfig = Field(default_factory=WatchlistConfig)
    news_listener: NewsListenerConfig = Field(default_factory=NewsListenerConfig)
    symbol_search: SymbolSearchConfig = Field(default_factory=SymbolSearchConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    longbridge: LongbridgeConfig = Field(default_factory=LongbridgeConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)

    def ensure_output_root(self) -> Path:
        self.output_root.mkdir(parents=True, exist_ok=True)
        return self.output_root

    def ensure_data_root(self) -> Path:
        path = self.database.url
        if path.startswith("sqlite:///"):
            db_file = Path(path.replace("sqlite:///", "", 1))
            db_file.parent.mkdir(parents=True, exist_ok=True)
        return Path("data")

    def normalized(self) -> "AppConfig":
        payload = self.model_dump(mode="python")
        payload["output_root"] = Path(payload["output_root"])
        payload["config_file"] = Path(payload["config_file"])
        return AppConfig.model_validate(payload)

    def analysis_provider_map(self) -> Dict[str, AnalysisProviderConfig]:
        return {
            provider.provider_id: provider
            for provider in self.analysis.providers
            if provider.enabled
        }


def default_app_config() -> AppConfig:
    return AppConfig(analysis=AnalysisConfig(providers=default_analysis_providers()))


def normalize_source_id(raw: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", str(raw or "").lower()).strip("-")
    return value or "source"


def normalize_news_sources(news_sources: List[NewsSource]) -> List[NewsSource]:
    normalized: List[NewsSource] = []
    used_ids: set[str] = set()
    for idx, source in enumerate(news_sources):
        candidate = source.source_id or source.name or f"source-{idx + 1}"
        base_id = normalize_source_id(candidate)
        source_id = base_id
        cursor = 2
        while source_id in used_ids:
            source_id = f"{base_id}-{cursor}"
            cursor += 1
        used_ids.add(source_id)
        normalized.append(
            source.model_copy(
                update={
                    "source_id": source_id,
                    "enabled": bool(source.enabled),
                }
            )
        )
    return normalized
