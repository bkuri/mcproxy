"""MCProxy as an MCP server over stdio.

Allows MCProxy to function as a native MCP server that can be launched
directly by MCP clients (like this chat interface) over stdin/stdout.
"""

import asyncio
import json
from typing import Any

from mcp.server import Server
from mcp.types import Tool, TextContent

from logging_config import get_logger
from tool_aggregator import aggregate_tools, parse_prefixed_tool_name

logger = get_logger(__name__)


class MCProxyMCPServer:
    """MCProxy as an MCP server over stdio."""

    def __init__(self, server_manager: Any) -> None:
        """Initialize MCProxy MCP server.

        Args:
            server_manager: HotReloadServerManager instance with spawned servers
        """
        self.server_manager = server_manager
        self.server = Server("mcproxy")

        # Register handlers
        self.server.list_tools()(self.list_tools)
        self.server.call_tool()(self.call_tool)

    async def list_tools(self) -> list[Tool]:
        """Return all available tools from aggregated MCP servers.

        Returns:
            List of Tool objects with name, description, and input schema
        """
        try:
            servers_tools = self.server_manager.get_all_tools()
            tools = aggregate_tools(servers_tools)

            # Convert to MCP Tool objects
            mcp_tools = []
            for tool in tools:
                mcp_tools.append(
                    Tool(
                        name=tool["name"],
                        description=tool.get("description", "No description"),
                        inputSchema=tool.get("inputSchema", {"type": "object"}),
                    )
                )

            logger.info(f"Listed {len(mcp_tools)} tools")
            return mcp_tools

        except Exception as e:
            logger.error(f"Error listing tools: {e}")
            return []

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> list[TextContent]:
        """Call a tool on the appropriate MCP server.

        Args:
            name: Prefixed tool name (e.g., "think_tool__think")
            arguments: Tool arguments

        Returns:
            List with TextContent containing the tool result

        Raises:
            ValueError: If tool name is invalid or tool call fails
        """
        try:
            # Parse prefixed name to get server and tool
            server_name, tool_name = parse_prefixed_tool_name(name)

            logger.info(f"Calling tool '{name}' on server '{server_name}'")

            # Route to server
            result = await self.server_manager.call_tool(
                server_name, tool_name, arguments
            )

            # Convert result to TextContent
            if isinstance(result, dict) and "content" in result:
                # Tool returned MCP-formatted result
                content_list = result.get("content", [])
                return [
                    TextContent(
                        type="text",
                        text=str(c.get("text", "")) if isinstance(c, dict) else str(c),
                    )
                    for c in content_list
                ]
            else:
                # Tool returned raw result
                return [TextContent(type="text", text=str(result))]

        except ValueError as e:
            logger.error(f"Invalid tool name: {e}")
            raise
        except Exception as e:
            logger.error(f"Error calling tool: {e}")
            raise

    async def run(self) -> None:
        """Run the MCP server over stdio."""
        logger.info("MCProxy MCP stdio server starting")
        async with self.server:
            logger.info("MCProxy MCP stdio server ready")
            # Server runs indefinitely
            while True:
                await asyncio.sleep(1)
