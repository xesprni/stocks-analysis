"""MCP client wrapper that connects to a single MCP Server and registers its tools."""

from __future__ import annotations

import json
import logging
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Optional, Tuple

from market_reporter.modules.analysis.agent.core.tool_protocol import ToolDefinition

logger = logging.getLogger(__name__)


class MCPClientTool:
    """Connects to a single MCP Server, discovers tools, and provides an executor."""

    def __init__(
        self,
        server_name: str,
        transport_type: str,
        config: Dict[str, Any],
    ) -> None:
        self.server_name = server_name
        self.transport_type = transport_type
        self.config = config
        self._exit_stack: Optional[AsyncExitStack] = None
        self._session: Any = None
        self._tool_map: Dict[str, Any] = {}

    async def connect(self) -> List[ToolDefinition]:
        """Connect to the MCP Server and return discovered tool definitions."""
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        self._exit_stack = AsyncExitStack()

        if self.transport_type == "stdio":
            server_params = StdioServerParameters(
                command=self.config.get("command", ""),
                args=self.config.get("args", []),
                env=self.config.get("env") or None,
            )
            read_stream, write_stream = await self._exit_stack.enter_async_context(
                stdio_client(server_params)
            )
        else:
            from mcp.client.sse import sse_client

            url = self.config.get("url", "")
            headers = self.config.get("headers") or {}
            read_stream, write_stream = await self._exit_stack.enter_async_context(
                sse_client(url=url, headers=headers)
            )

        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )
        await self._session.initialize()

        result = await self._session.list_tools()
        definitions: List[ToolDefinition] = []
        for tool in result.tools:
            qualified_name = f"{self.server_name}__{tool.name}"
            self._tool_map[qualified_name] = tool

            parameters: Dict[str, Any] = {"type": "object", "properties": {}}
            if tool.inputSchema and isinstance(tool.inputSchema, dict):
                parameters = tool.inputSchema

            definitions.append(
                ToolDefinition(
                    name=qualified_name,
                    description=tool.description or "",
                    parameters=parameters,
                    source="mcp",
                )
            )

        logger.info(
            "MCP server '%s' connected, discovered %d tools: %s",
            self.server_name,
            len(definitions),
            [d.name for d in definitions],
        )
        return definitions

    async def call_tool(self, **kwargs: Any) -> Dict[str, Any]:
        """Execute a tool on the MCP Server.

        Expects ``_mcp_tool_name`` in kwargs to identify the target tool.
        All other kwargs are forwarded as arguments.
        """
        tool_name = kwargs.pop("_mcp_tool_name", "")
        if not tool_name or not self._session:
            return {"error": "MCP tool name or session missing", "source": "mcp"}

        arguments = {k: v for k, v in kwargs.items() if not k.startswith("_")}

        try:
            result = await self._session.call_tool(tool_name, arguments=arguments)

            text_parts: List[str] = []
            data_parts: List[Any] = []
            for content in result.content:
                if hasattr(content, "text"):
                    text_parts.append(content.text)
                elif hasattr(content, "data"):
                    data_parts.append(content.data)
                else:
                    text_parts.append(str(content))

            parsed: Dict[str, Any] = {}
            combined_text = "\n".join(text_parts)
            if combined_text:
                try:
                    parsed = json.loads(combined_text)
                    if not isinstance(parsed, dict):
                        parsed = {"text": combined_text}
                except (json.JSONDecodeError, ValueError):
                    parsed = {"text": combined_text}

            if data_parts:
                parsed["_data"] = data_parts

            return parsed

        except Exception as exc:
            logger.exception("MCP tool '%s' call failed", tool_name)
            return {"error": str(exc), "source": "mcp", "tool": tool_name}

    async def close(self) -> None:
        if self._exit_stack is not None:
            await self._exit_stack.aclose()
            self._exit_stack = None
            self._session = None
            self._tool_map.clear()


class McpManager:
    """Manages lifecycle of all MCP client connections for a user."""

    def __init__(self) -> None:
        self._clients: List[MCPClientTool] = []

    async def load_from_db(
        self,
        database_url: str,
        user_id: Optional[int] = None,
    ) -> List[Tuple[MCPClientTool, List[ToolDefinition]]]:
        """Load enabled MCP configs from DB, connect, and discover tools."""
        from market_reporter.infra.db.repos import McpServerConfigRepo
        from market_reporter.infra.db.session import session_scope

        rows = []
        with session_scope(database_url) as session:
            repo = McpServerConfigRepo(session)
            rows = repo.list_enabled(user_id=user_id)

        results: List[Tuple[MCPClientTool, List[ToolDefinition]]] = []
        for row in rows:
            try:
                config = json.loads(row.config_json) if row.config_json else {}
            except (json.JSONDecodeError, ValueError):
                logger.warning("MCP config '%s' has invalid JSON, skipping", row.server_name)
                continue

            client = MCPClientTool(
                server_name=row.server_name,
                transport_type=row.transport_type,
                config=config,
            )
            try:
                definitions = await client.connect()
                self._clients.append(client)
                results.append((client, definitions))
            except Exception as exc:
                logger.warning(
                    "MCP server '%s' connection failed: %s", row.server_name, exc
                )
                await client.close()

        return results

    async def test_connection(
        self,
        server_name: str,
        transport_type: str,
        config: Dict[str, Any],
    ) -> McpConnectionTestResult:
        """Test connection to an MCP Server and return discovered tools."""
        from market_reporter.modules.analysis.schemas import McpConnectionTestResult

        client = MCPClientTool(
            server_name=server_name,
            transport_type=transport_type,
            config=config,
        )
        try:
            definitions = await client.connect()
            tools = [
                {
                    "name": d.name,
                    "description": d.description,
                    "parameters": d.parameters,
                }
                for d in definitions
            ]
            return McpConnectionTestResult(
                success=True,
                server_name=server_name,
                tools=tools,
            )
        except Exception as exc:
            return McpConnectionTestResult(
                success=False,
                server_name=server_name,
                error=str(exc),
            )
        finally:
            await client.close()

    async def close_all(self) -> None:
        for client in self._clients:
            try:
                await client.close()
            except Exception:
                pass
        self._clients.clear()
