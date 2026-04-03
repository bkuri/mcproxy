"""Parsing utilities for MCP handlers."""

import re
from typing import Optional, Tuple


def parse_inspect_code(code: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse code expression to extract server and tool names for inspect.

    Supports patterns:
    - api.server("name") -> returns (name, None)
    - api.server("name").tool -> returns (name, tool)
    - api.server("name").tool("tool_name") -> returns (name, tool_name)
    - api.server('name') -> single quotes also work

    Args:
        code: Code expression like 'api.server("wikipedia").search'

    Returns:
        Tuple of (server_name, tool_name) where tool_name may be None
    """
    if not code:
        return None, None

    code = code.strip()

    # Pattern 1: api.server("server_name").method("tool_name")
    # Agents often write .tool('name') instead of .tool_name
    pattern_method = r"api\.server\(['\"]([\w\-]+)['\"]\)\.\w+\(['\"]([\w\-]+)['\"]\)"
    match = re.match(pattern_method, code)
    if match:
        return match.group(1), match.group(2)

    # Pattern 2: api.server("server_name").tool_name (attribute access)
    pattern_attr = r"api\.server\(['\"]([\w\-]+)['\"]\)(?:\.(\w+))?"
    match = re.match(pattern_attr, code)
    if match:
        server_name = match.group(1)
        tool_name = match.group(2)  # May be None
        return server_name, tool_name

    return None, None
