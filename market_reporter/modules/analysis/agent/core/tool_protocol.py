from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Literal

from pydantic import BaseModel

ToolExecutor = Callable[..., Awaitable[Dict[str, Any]]]


class ToolDefinition(BaseModel):
    """Describes a tool that can be registered with the ToolRegistry."""

    name: str
    description: str
    parameters: Dict[str, Any]
    source: Literal["builtin", "mcp", "skill"] = "builtin"

    def to_openai_spec(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
