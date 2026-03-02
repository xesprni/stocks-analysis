from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple

from market_reporter.modules.analysis.agent.skill_catalog import SkillCatalog
from market_reporter.modules.analysis.agent.subagents import SubAgentRegistry


@dataclass(frozen=True)
class RegisteredCapability:
    name: str
    description: str
    parameters: Dict[str, Any]
    modes: Tuple[str, ...]
    include_in_evidence: bool = True


class CapabilityRegistry:
    def __init__(self) -> None:
        self._capabilities: Dict[str, RegisteredCapability] = {}

    @classmethod
    def build_default(
        cls,
        skill_catalog: SkillCatalog,
        subagent_registry: SubAgentRegistry,
    ) -> "CapabilityRegistry":
        registry = cls()

        for item in _default_data_capabilities():
            registry.register(item)

        registry.register(
            RegisteredCapability(
                name="skill",
                description=_build_skill_tool_description(skill_catalog),
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Skill name from the available skill list.",
                        }
                    },
                    "required": ["name"],
                },
                modes=("stock", "market"),
                include_in_evidence=False,
            )
        )

        registry.register(
            RegisteredCapability(
                name="subagent",
                description=_build_subagent_tool_description(subagent_registry),
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Subagent name from available subagents.",
                        },
                        "task": {
                            "type": "string",
                            "description": "Task statement for the selected subagent.",
                        },
                    },
                    "required": ["name"],
                },
                modes=("stock", "market"),
                include_in_evidence=False,
            )
        )
        return registry

    def register(self, capability: RegisteredCapability) -> None:
        key = capability.name.strip().lower()
        if not key:
            raise ValueError("Capability name cannot be empty")
        existing = self._capabilities.get(key)
        if existing is not None and existing != capability:
            raise ValueError(f"Capability already registered: {capability.name}")
        self._capabilities[key] = capability

    def has(self, name: str) -> bool:
        key = (name or "").strip().lower()
        return key in self._capabilities

    def include_in_evidence(self, name: str) -> bool:
        key = (name or "").strip().lower()
        capability = self._capabilities.get(key)
        if capability is None:
            return False
        return capability.include_in_evidence

    def list_for_mode(self, mode: str) -> List[RegisteredCapability]:
        key = (mode or "").strip().lower()
        values = [item for item in self._capabilities.values() if key in item.modes]
        return sorted(values, key=lambda item: item.name)

    def tool_specs_for_mode(self, mode: str) -> List[Dict[str, Any]]:
        specs: List[Dict[str, Any]] = []
        for item in self.list_for_mode(mode):
            specs.append(
                {
                    "type": "function",
                    "function": {
                        "name": item.name,
                        "description": item.description,
                        "parameters": item.parameters,
                    },
                }
            )
        return specs


def _default_data_capabilities() -> Iterable[RegisteredCapability]:
    return [
        RegisteredCapability(
            name="get_price_history",
            description="Get historical OHLCV data",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "market": {"type": "string"},
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                    "interval": {"type": "string"},
                    "adjusted": {"type": "boolean"},
                },
            },
            modes=("stock",),
        ),
        RegisteredCapability(
            name="get_fundamentals_info",
            description="Get company fundamentals",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "market": {"type": "string"},
                },
            },
            modes=("stock",),
        ),
        RegisteredCapability(
            name="get_fundamentals",
            description="Get company fundamentals",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "market": {"type": "string"},
                },
            },
            modes=("stock",),
        ),
        RegisteredCapability(
            name="get_financial_reports",
            description="Get company financial statements",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "market": {"type": "string"},
                    "limit": {"type": "integer"},
                },
            },
            modes=("stock",),
        ),
        RegisteredCapability(
            name="search_news",
            description="Search and deduplicate news",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "symbol": {"type": "string"},
                    "market": {"type": "string"},
                    "from": {"type": "string"},
                    "to": {"type": "string"},
                    "limit": {"type": "integer"},
                },
            },
            modes=("stock", "market"),
        ),
        RegisteredCapability(
            name="search_web",
            description="Search web results from internet sources",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                    "from": {"type": "string"},
                    "to": {"type": "string"},
                },
            },
            modes=("stock", "market"),
        ),
        RegisteredCapability(
            name="compute_indicators",
            description="Compute technical indicators",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "market": {"type": "string"},
                    "price_df": {"type": "object"},
                    "indicators": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "indicator_profile": {"type": "string"},
                },
            },
            modes=("stock",),
        ),
        RegisteredCapability(
            name="peer_compare",
            description="Compare peer metrics",
            parameters={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "market": {"type": "string"},
                    "peer_list": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "metrics": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
            modes=("stock",),
        ),
        RegisteredCapability(
            name="get_macro_data",
            description="Get macro series from FRED/eastmoney",
            parameters={
                "type": "object",
                "properties": {
                    "periods": {"type": "integer"},
                    "market": {"type": "string"},
                },
            },
            modes=("stock", "market"),
        ),
    ]


def _build_skill_tool_description(skill_catalog: SkillCatalog) -> str:
    skills = skill_catalog.list_skill_payloads()
    if not skills:
        return (
            "Load a skill markdown document from skills/*/SKILL.md by name. "
            "No skills are currently registered."
        )

    rows = []
    for item in skills:
        name = str(item.get("name") or "").strip()
        desc = str(item.get("description") or "").strip()
        if not name:
            continue
        rows.append(f"- {name}: {desc}")

    summary = "\n".join(rows)
    return (
        "Load the full content of a registered skill (lazy loading). "
        "Call when you need detailed playbooks beyond the current context.\n"
        f"Available skills:\n{summary}"
    )


def _build_subagent_tool_description(subagent_registry: SubAgentRegistry) -> str:
    rows = []
    for item in subagent_registry.list_subagents():
        rows.append(f"- {item.name}: {item.description}")
    summary = "\n".join(rows) if rows else "- none"
    return (
        "Run a specialized subagent to synthesize intermediate findings. "
        "Use when you want focused analysis before final answer.\n"
        f"Available subagents:\n{summary}"
    )
