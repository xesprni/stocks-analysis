from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, List, Tuple

from market_reporter.modules.analysis.agent.core.tool_protocol import (
    ToolDefinition,
    ToolExecutor,
)

logger = logging.getLogger(__name__)

_Entry = Tuple[ToolDefinition, ToolExecutor]


class ToolRegistry:
    """Unified registry for builtin, MCP and skill tools."""

    def __init__(self) -> None:
        self._tools: Dict[str, _Entry] = {}

    def register(
        self,
        definition: ToolDefinition,
        executor: ToolExecutor,
    ) -> None:
        key = definition.name.strip().lower()
        if not key:
            raise ValueError("Tool name cannot be empty")
        if key in self._tools:
            existing_def = self._tools[key][0]
            if existing_def.source == definition.source:
                logger.debug("Overwriting tool %s (same source)", key)
            else:
                logger.warning(
                    "Tool %s already registered from %s, overwriting with %s",
                    key,
                    existing_def.source,
                    definition.source,
                )
        self._tools[key] = (definition, executor)

    def has(self, name: str) -> bool:
        return name.strip().lower() in self._tools

    def get(self, name: str) -> ToolDefinition | None:
        entry = self._tools.get(name.strip().lower())
        return entry[0] if entry else None

    def list_tools(self) -> List[ToolDefinition]:
        return [entry[0] for entry in sorted(self._tools.values(), key=lambda e: e[0].name)]

    def get_tool_specs(self) -> List[Dict[str, Any]]:
        return [definition.to_openai_spec() for definition in self.list_tools()]

    async def execute(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        key = name.strip().lower()
        entry = self._tools.get(key)
        if entry is None:
            raise ValueError(f"Unknown tool: {name}")
        definition, executor = entry
        return await executor(**arguments)
