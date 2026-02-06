from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, Dict, TypeVar

from market_reporter.core.errors import ProviderNotFoundError

ProviderFactory = Callable[..., Any]
T = TypeVar("T")


class ProviderRegistry:
    def __init__(self) -> None:
        self._registry: Dict[str, Dict[str, ProviderFactory]] = defaultdict(dict)

    def register(self, module: str, provider_id: str, factory: ProviderFactory) -> None:
        self._registry[module][provider_id] = factory

    def has(self, module: str, provider_id: str) -> bool:
        return provider_id in self._registry.get(module, {})

    def resolve(self, module: str, provider_id: str, **kwargs: Any) -> Any:
        module_map = self._registry.get(module)
        if not module_map or provider_id not in module_map:
            raise ProviderNotFoundError(f"Provider not found: module={module}, provider_id={provider_id}")
        return module_map[provider_id](**kwargs)

    def list_ids(self, module: str) -> list[str]:
        return sorted(self._registry.get(module, {}).keys())
