from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Optional

import typer
import uvicorn
from rich.console import Console
from rich.table import Table

from market_reporter.config import AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.infra.db.repos import ApiKeyRepo, UserRepo
from market_reporter.infra.db.session import (
    generate_random_password,
    hash_password,
    init_db,
    session_scope,
)
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
auth_app = typer.Typer(help="Manage authentication")
app.add_typer(watchlist_app, name="watchlist")
app.add_typer(providers_app, name="providers")
app.add_typer(analyze_app, name="analyze")
app.add_typer(db_app, name="db")
app.add_typer(auth_app, name="auth")


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


@auth_app.command("generate-key")
def auth_generate_key() -> None:
    console.print(
        "[yellow]Note: JWT authentication is now used instead of API keys[/yellow]"
    )
    console.print(
        "[green]Set MARKET_REPORTER_AUTH_ENABLED=true to enable JWT auth[/green]"
    )
    console.print("[green]Use 'market-reporter user create' to create users[/green]")


@auth_app.command("enable")
def auth_enable() -> None:
    env_path = Path(".env")
    lines = []
    if env_path.exists():
        lines = env_path.read_text().splitlines()

    auth_enabled_line = "MARKET_REPORTER_AUTH_ENABLED=true"

    filtered = [
        l
        for l in lines
        if not l.startswith("MARKET_REPORTER_AUTH_ENABLED=")
        and not l.startswith("MARKET_REPORTER_AUTH_API_KEY=")
    ]
    filtered.append(auth_enabled_line)

    env_path.write_text("\n".join(filtered) + "\n")
    console.print(f"[green]JWT Auth enabled in .env file[/green]")
    console.print(
        "[yellow]Restart the server and use 'market-reporter user create' to create users[/green]"
    )


@auth_app.command("disable")
def auth_disable() -> None:
    env_path = Path(".env")
    if not env_path.exists():
        console.print("[yellow]No .env file found[/yellow]")
        return

    lines = env_path.read_text().splitlines()
    filtered = [
        l
        for l in lines
        if not l.startswith("MARKET_REPORTER_AUTH_ENABLED=")
        and not l.startswith("MARKET_REPORTER_AUTH_API_KEY=")
    ]
    filtered.append("MARKET_REPORTER_AUTH_ENABLED=false")

    env_path.write_text("\n".join(filtered) + "\n")
    console.print(f"[green]Auth disabled in .env file[/green]")


user_app = typer.Typer(help="Manage users")
app.add_typer(user_app, name="user")


@user_app.command("create")
def user_create(
    username: str = typer.Option(..., help="Username"),
    password: Optional[str] = typer.Option(
        None, help="Password (will be generated if not provided)"
    ),
    email: Optional[str] = typer.Option(None, help="Email"),
    display_name: Optional[str] = typer.Option(None, help="Display name"),
    is_admin: bool = typer.Option(False, help="Is admin user"),
) -> None:
    config = _load_config()
    with session_scope(config.database.url) as session:
        user_repo = UserRepo(session)
        existing = user_repo.get_by_username(username)
        if existing:
            console.print(f"[red]User already exists: {username}[/red]")
            raise typer.Exit(1)

        if not password:
            password = generate_random_password(16)

        password_hash = hash_password(password)
        user = user_repo.create(
            username=username,
            password_hash=password_hash,
            email=email,
            display_name=display_name,
            is_admin=is_admin,
        )
        console.print(f"[green]User created:[/green] {user.id} - {user.username}")
        console.print(f"[green]Password:[/green] {password}")
        console.print(
            "[yellow]Save this password securely, it won't be shown again[/yellow]"
        )


@user_app.command("list")
def user_list() -> None:
    config = _load_config()
    with session_scope(config.database.url) as session:
        user_repo = UserRepo(session)
        users = user_repo.list_all(include_inactive=True)
        table = Table(title="Users")
        table.add_column("ID")
        table.add_column("Username")
        table.add_column("Email")
        table.add_column("Admin")
        table.add_column("Active")
        for u in users:
            table.add_row(
                str(u.id),
                u.username,
                u.email or "",
                str(u.is_admin),
                str(u.is_active),
            )
        console.print(table)


@user_app.command("reset-password")
def user_reset_password(
    username: str = typer.Option(..., help="Username"),
    password: Optional[str] = typer.Option(
        None, help="New password (will be generated if not provided)"
    ),
) -> None:
    config = _load_config()
    with session_scope(config.database.url) as session:
        user_repo = UserRepo(session)
        user = user_repo.get_by_username(username)
        if not user:
            console.print(f"[red]User not found: {username}[/red]")
            raise typer.Exit(1)

        if not password:
            password = generate_random_password(16)

        password_hash = hash_password(password)
        user_repo.update_password(user, password_hash)
        console.print(f"[green]Password reset for {username}:[/green] {password}")
        console.print(
            "[yellow]Save this password securely, it won't be shown again[/yellow]"
        )


@user_app.command("deactivate")
def user_deactivate(
    username: str = typer.Option(..., help="Username"),
) -> None:
    config = _load_config()
    with session_scope(config.database.url) as session:
        user_repo = UserRepo(session)
        user = user_repo.get_by_username(username)
        if not user:
            console.print(f"[red]User not found: {username}[/red]")
            raise typer.Exit(1)
        user_repo.update(user, is_active=False)
        console.print(f"[green]User deactivated: {username}[/green]")


@user_app.command("delete")
def user_delete(
    username: str = typer.Option(..., help="Username"),
    force: bool = typer.Option(False, help="Force delete without confirmation"),
) -> None:
    if not force:
        confirm = typer.confirm(f"Delete user {username}? This cannot be undone.")
        if not confirm:
            console.print("[yellow]Cancelled[/yellow]")
            return

    config = _load_config()
    with session_scope(config.database.url) as session:
        user_repo = UserRepo(session)
        user = user_repo.get_by_username(username)
        if not user:
            console.print(f"[red]User not found: {username}[/red]")
            raise typer.Exit(1)
        user_repo.delete(user.id)
        console.print(f"[green]User deleted: {username}[/green]")


def main() -> None:
    app()
