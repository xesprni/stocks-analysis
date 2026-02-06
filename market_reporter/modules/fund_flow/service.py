from __future__ import annotations

from typing import Dict, List, Tuple

from market_reporter.config import AppConfig
from market_reporter.core.registry import ProviderRegistry
from market_reporter.core.types import FlowPoint
from market_reporter.infra.http.client import HttpClient
from market_reporter.modules.fund_flow.providers.eastmoney_provider import EastMoneyFundFlowProvider
from market_reporter.modules.fund_flow.providers.fred_provider import FredFundFlowProvider


class FundFlowService:
    MODULE_NAME = "fund_flow"

    def __init__(self, config: AppConfig, client: HttpClient, registry: ProviderRegistry) -> None:
        self.config = config
        self.client = client
        self.registry = registry
        self.registry.register(self.MODULE_NAME, "eastmoney", self._build_eastmoney)
        self.registry.register(self.MODULE_NAME, "fred", self._build_fred)

    def _build_eastmoney(self):
        return EastMoneyFundFlowProvider(config=self.config, client=self.client)

    def _build_fred(self):
        return FredFundFlowProvider(config=self.config, client=self.client)

    async def collect(self, periods: int) -> Tuple[Dict[str, List[FlowPoint]], List[str]]:
        merged: Dict[str, List[FlowPoint]] = {}
        warnings: List[str] = []
        for provider_id in self.config.modules.fund_flow.providers:
            try:
                provider = self.registry.resolve(self.MODULE_NAME, provider_id)
                result = await provider.collect(periods=periods)
                for key, points in result.items():
                    merged[key] = points
            except Exception as exc:
                warnings.append(f"Fund-flow provider failed [{provider_id}]: {exc}")
        return merged, warnings

    def provider_ids(self) -> List[str]:
        return self.registry.list_ids(self.MODULE_NAME)
