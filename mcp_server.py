"""MCProxy as an MCP server over stdio using FastMCP.

Simple, clean MCP server that exposes all aggregated MCP tools.
"""

from typing import Any

import fastmcp

from logging_config import get_logger
from tool_aggregator import aggregate_tools, parse_prefixed_tool_name

logger = get_logger(__name__)


def create_mcp_server(server_manager: Any) -> fastmcp.FastMCP:
    """Create MCProxy FastMCP server.

    Args:
        server_manager: HotReloadServerManager instance with spawned servers

    Returns:
        Configured FastMCP server instance
    """
    mcp = fastmcp.FastMCP("mcproxy")

    @mcp.tool()
    async def call_tool(name: str, arguments: dict[str, Any] | None = None) -> str:
        """Call any aggregated MCP tool.

        Args:
            name: Tool name in format "server__tool_name"
            arguments: Tool arguments (optional)

        Returns:
            Tool result as formatted string
        """
        if arguments is None:
            arguments = {}

        try:
            # Parse prefixed name to get server and tool
            server_name, tool_name = parse_prefixed_tool_name(name)

            logger.info(f"Calling tool '{name}' on server '{server_name}'")

            # Route to server
            result = await server_manager.call_tool(server_name, tool_name, arguments)

            # Format result
            if isinstance(result, dict) and "content" in result:
                content_list = result.get("content", [])
                texts = []
                for c in content_list:
                    if isinstance(c, dict):
                        texts.append(c.get("text", ""))
                    else:
                        texts.append(str(c))
                return "\n".join(texts)
            else:
                return str(result)

        except ValueError as e:
            raise ValueError(f"Invalid tool name '{name}': {e}")
        except Exception as e:
            logger.error(f"Error calling tool '{name}': {e}")
            raise

    @mcp.resource("tools://list")
    def list_all_tools() -> str:
        """List all available tools.

        Returns:
            Formatted list of all aggregated tools
        """
        try:
            servers_tools = server_manager.get_all_tools()
            tools = aggregate_tools(servers_tools)

            lines = [f"Available Tools ({len(tools)} total):"]
            lines.append("")

            # Group by server
            by_server = {}
            for tool in tools:
                server = tool.get("_server", "unknown")
                if server not in by_server:
                    by_server[server] = []
                by_server[server].append(tool["name"])

            # Format output
            for server in sorted(by_server.keys()):
                tool_names = by_server[server]
                lines.append(f"{server} ({len(tool_names)} tools):")
                for tool_name in sorted(tool_names):
                    lines.append(f"  - {tool_name}")
                lines.append("")

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"Error listing tools: {e}")
            raise

    logger.info("MCProxy FastMCP server created")
    return mcp
