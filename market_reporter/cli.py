from __future__ import annotations

import asyncio
import json
from typing import Optional

import typer
import uvicorn
from rich.console import Console
from rich.table import Table

from market_reporter.config import AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.infra.db.session import init_db
from market_reporter.infra.http.client import HttpClient
from market_reporter.modules.analysis.service import AnalysisService
from market_reporter.modules.fund_flow.service import FundFlowService
from market_reporter.modules.market_data.service import MarketDataService
from market_reporter.modules.news.service import NewsService
from market_reporter.modules.reports.service import ReportService
from market_reporter.modules.watchlist.service import WatchlistService
from market_reporter.schemas import RunRequest
from market_reporter.services.config_store import ConfigStore
from market_reporter.settings import AppSettings

app = typer.Typer(help="Market Reporter CLI")
console = Console()

watchlist_app = typer.Typer(help="Manage watchlist")
providers_app = typer.Typer(help="Manage analysis providers")
analyze_app = typer.Typer(help="Run analysis tasks")
db_app = typer.Typer(help="Database commands")
app.add_typer(watchlist_app, name="watchlist")
app.add_typer(providers_app, name="providers")
app.add_typer(analyze_app, name="analyze")
app.add_typer(db_app, name="db")


def _store() -> ConfigStore:
    settings = AppSettings()
    return ConfigStore(config_path=settings.config_file)


def _load_config() -> AppConfig:
    store = _store()
    config = store.load()
    init_db(config.database.url)
    return config


@app.command("init-config")
def init_config() -> None:
    store = _store()
    config = store.load()
    store.save(config)
    init_db(config.database.url)
    console.print(f"[green]Config initialized:[/green] {store.config_path.resolve()}")


@db_app.command("init")
def db_init() -> None:
    config = _load_config()
    init_db(config.database.url)
    console.print(f"[green]Database ready:[/green] {config.database.url}")


@app.command("run")
def run(
    news_limit: Optional[int] = typer.Option(
        None, help="Override news limit for this run."
    ),
    flow_periods: Optional[int] = typer.Option(
        None, help="Override flow periods for this run."
    ),
    timezone: Optional[str] = typer.Option(
        None, help="Override timezone for this run."
    ),
    provider_id: Optional[str] = typer.Option(
        None, help="Override analysis provider id."
    ),
    model: Optional[str] = typer.Option(None, help="Override analysis model."),
    mode: str = typer.Option("market", help="Report mode: market|stock|watchlist."),
    skill_id: Optional[str] = typer.Option(None, help="Optional report skill id."),
    symbol: Optional[str] = typer.Option(None, help="Symbol for stock report mode."),
    market: Optional[str] = typer.Option(
        None, help="Market for stock report mode (CN/HK/US)."
    ),
    question: Optional[str] = typer.Option(
        None, help="Optional custom analysis question."
    ),
    peer_list: Optional[str] = typer.Option(
        None, help="Optional peer list, comma separated."
    ),
    watchlist_limit: Optional[int] = typer.Option(
        None, help="Optional max watchlist symbols for watchlist mode."
    ),
) -> None:
    store = _store()
    service = ReportService(config_store=store)
    peers = None
    if peer_list:
        peers = [item.strip() for item in peer_list.split(",") if item.strip()]
    payload = RunRequest(
        skill_id=skill_id,
        news_limit=news_limit,
        flow_periods=flow_periods,
        timezone=timezone,
        provider_id=provider_id,
        model=model,
        mode=mode,
        symbol=symbol,
        market=market,
        question=question,
        peer_list=peers,
        watchlist_limit=watchlist_limit,
    )
    result = asyncio.run(service.run_report(overrides=payload))

    console.print(f"[green]Report generated:[/green] {result.summary.report_path}")
    console.print(f"[green]Raw data:[/green] {result.summary.raw_data_path}")
    console.print(
        f"[green]Analysis engine:[/green] {result.summary.provider_id} / {result.summary.model}"
    )
    if result.warnings:
        console.print("[yellow]Warnings:[/yellow]")
        for warning in result.warnings:
            console.print(f"- {warning}")


@app.command("serve")
def serve(
    host: Optional[str] = typer.Option(None, help="Bind host, default from settings."),
    port: Optional[int] = typer.Option(None, help="Bind port, default from settings."),
    reload: bool = typer.Option(False, help="Enable autoreload mode."),
) -> None:
    settings = AppSettings()
    uvicorn.run(
        "market_reporter.api:app",
        host=host or settings.api_host,
        port=port or settings.api_port,
        reload=reload,
    )


@watchlist_app.command("list")
def watchlist_list() -> None:
    config = _load_config()
    service = WatchlistService(config)
    items = service.list_items()
    table = Table(title="Watchlist")
    table.add_column("ID")
    table.add_column("Symbol")
    table.add_column("Market")
    table.add_column("Alias")
    table.add_column("Enabled")
    for item in items:
        table.add_row(
            str(item.id), item.symbol, item.market, item.alias or "", str(item.enabled)
        )
    console.print(table)


@watchlist_app.command("add")
def watchlist_add(
    symbol: str = typer.Option(...),
    market: str = typer.Option(..., help="CN/HK/US"),
    alias: Optional[str] = typer.Option(None),
    display_name: Optional[str] = typer.Option(None),
    keywords: Optional[str] = typer.Option(None, help="Comma-separated keywords"),
) -> None:
    config = _load_config()
    service = WatchlistService(config)
    keyword_list = None
    if keywords:
        keyword_list = [entry.strip() for entry in keywords.split(",") if entry.strip()]
    item = service.add_item(
        symbol=symbol,
        market=market,
        alias=alias,
        display_name=display_name,
        keywords=keyword_list,
    )
    console.print(f"[green]Added:[/green] {item.id} {item.symbol} ({item.market})")


@watchlist_app.command("remove")
def watchlist_remove(item_id: int = typer.Option(...)) -> None:
    config = _load_config()
    service = WatchlistService(config)
    if service.delete_item(item_id=item_id):
        console.print(f"[green]Removed:[/green] {item_id}")
    else:
        console.print(f"[yellow]Not found:[/yellow] {item_id}")


@providers_app.command("list")
def providers_list() -> None:
    config = _load_config()
    service = AnalysisService(config=config, registry=ProviderRegistry())
    providers = service.list_providers()

    table = Table(title="Analysis Providers")
    table.add_column("Provider ID")
    table.add_column("Type")
    table.add_column("Models")
    table.add_column("Enabled")
    table.add_column("Secret")
    for provider in providers:
        table.add_row(
            provider.provider_id,
            provider.type,
            ", ".join(provider.models),
            str(provider.enabled),
            "yes" if provider.has_secret else "no",
        )
    console.print(table)


@providers_app.command("set-default")
def providers_set_default(
    provider: str = typer.Option(..., help="Provider ID"),
    model: str = typer.Option(..., help="Model name"),
) -> None:
    store = _store()
    config = store.load()
    provider_map = config.analysis_provider_map()
    if provider not in provider_map:
        raise typer.BadParameter(f"Unknown provider: {provider}")
    provider_cfg = provider_map[provider]
    if model not in provider_cfg.models and provider_cfg.models:
        raise typer.BadParameter(f"Model not in provider list: {model}")

    next_config = config.model_copy(
        update={
            "analysis": config.analysis.model_copy(
                update={
                    "default_provider": provider,
                    "default_model": model,
                }
            )
        }
    )
    store.save(next_config)
    console.print(f"[green]Updated default analysis:[/green] {provider} / {model}")


@analyze_app.command("stock")
def analyze_stock(
    symbol: str = typer.Option(...),
    market: str = typer.Option(..., help="CN/HK/US"),
    skill_id: Optional[str] = typer.Option(None, help="Optional agent skill id."),
    provider_id: Optional[str] = typer.Option(None),
    model: Optional[str] = typer.Option(None),
    interval: str = typer.Option("5m"),
    lookback_bars: int = typer.Option(120),
) -> None:
    config = _load_config()

    async def _run() -> None:
        async with HttpClient(
            timeout_seconds=config.request_timeout_seconds,
            user_agent=config.user_agent,
        ) as client:
            registry = ProviderRegistry()
            news_service = NewsService(config=config, client=client, registry=registry)
            flow_service = FundFlowService(
                config=config, client=client, registry=registry
            )
            market_data_service = MarketDataService(config=config, registry=registry)
            analysis_service = AnalysisService(
                config=config,
                registry=registry,
                market_data_service=market_data_service,
                news_service=news_service,
                fund_flow_service=flow_service,
            )
            result = await analysis_service.run_stock_analysis(
                symbol=symbol,
                market=market,
                skill_id=skill_id,
                provider_id=provider_id,
                model=model,
                interval=interval,
                lookback_bars=lookback_bars,
            )
            console.print(f"[green]Analysis run id:[/green] {result.id}")
            console.print(result.markdown)
            console.print(
                json.dumps(
                    result.output.model_dump(mode="json"), ensure_ascii=False, indent=2
                )
            )

    asyncio.run(_run())


def main() -> None:
    app()
