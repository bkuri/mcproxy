"""Tool aggregation and prefixing for MCProxy.

Aggregates tools from multiple MCP servers and adds server name prefixes.
"""

from typing import Any, Dict, List

from logging_config import get_logger

logger = get_logger(__name__)


def prefix_tool_name(server_name: str, tool_name: str) -> str:
    """Prefix tool name with server name.

    Format: {server_name}__{tool_name}

    Args:
        server_name: Name of the MCP server
        tool_name: Original tool name

    Returns:
        Prefixed tool name
    """
    return f"{server_name}__{tool_name}"


def aggregate_tools(
    servers_tools: Dict[str, List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Aggregate tools from all servers with prefixed names.

    Args:
        servers_tools: Dict mapping server name to list of tools from that server

    Returns:
        List of all tools with prefixed names
    """
    aggregated: List[Dict[str, Any]] = []
    seen_names: set = set()

    for server_name, tools in servers_tools.items():
        for tool in tools:
            if not isinstance(tool, dict) or "name" not in tool:
                logger.warning(f"Invalid tool format from server {server_name}: {tool}")
                continue

            original_name = tool["name"]
            prefixed_name = prefix_tool_name(server_name, original_name)

            if prefixed_name in seen_names:
                logger.warning(
                    f"Duplicate tool name '{prefixed_name}' from server {server_name}"
                )
                continue

            seen_names.add(prefixed_name)

            # Create new tool dict with prefixed name
            prefixed_tool = tool.copy()
            prefixed_tool["name"] = prefixed_name
            prefixed_tool["_original_name"] = original_name
            prefixed_tool["_server"] = server_name

            aggregated.append(prefixed_tool)

    logger.debug(
        f"Aggregated {len(aggregated)} tools from {len(servers_tools)} servers"
    )
    return aggregated


def parse_prefixed_tool_name(prefixed_name: str) -> tuple:
    """Parse a prefixed tool name into server and tool components.

    Args:
        prefixed_name: Tool name in format {server}__{tool}

    Returns:
        Tuple of (server_name, tool_name)

    Raises:
        ValueError: If name format is invalid
    """
    parts = prefixed_name.split("__", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid tool name format: {prefixed_name}")
    return parts[0], parts[1]
