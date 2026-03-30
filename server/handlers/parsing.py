"""Parsing utilities for MCP handlers."""

import re
from typing import Optional, Tuple


def parse_inspect_code(code: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse code expression to extract server and tool names for inspect.

    Supports patterns:
    - api.server("name") -> returns (name, None)
    - api.server("name").tool -> returns (name, tool)
    - api.server('name') -> single quotes also work

    Args:
        code: Code expression like 'api.server("wikipedia").search'

    Returns:
        Tuple of (server_name, tool_name) where tool_name may be None
    """
    if not code:
        return None, None

    code = code.strip()

    # Pattern: api.server("server_name") or api.server("server_name").tool_name
    # Also supports single quotes
    pattern = r"api\.server\(['\"]([\w\-]+)['\"]\)(?:\.(\w+))?"
    match = re.match(pattern, code)

    if match:
        server_name = match.group(1)
        tool_name = match.group(2)  # May be None
        return server_name, tool_name

    return None, None
