"""Tools subpackage - meta-tool definitions and handlers.

This package contains modular handlers for different meta-tool actions:
- router.py: Main handler that routes tools/call to appropriate action
- execute.py: handle_execute(), handle_trace() - code execution handlers
- search.py: handle_search() - tool discovery handler
- inspect.py: handle_inspect() - schema inspection handler
- help.py: handle_help() - documentation handler
"""

from typing import Any, Callable, Dict, List, Optional

from manifest import CapabilityRegistry
from manifest.typescript_gen import generate_compact_instructions

# Re-export router and handlers
from .execute import handle_execute, handle_trace
from .help import handle_help
from .inspect import handle_inspect
from .router import handle_tools_call
from .search import handle_search


# ============================================================================
# META_TOOLS Definition
# ============================================================================

META_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "mcproxy",
        "description": "Unified tool: execute (run code), search (find tools), inspect (get schemas), help (get docs). "
        "Response: {status, result, stdout, traceback}. "
        "Use api.server('name').tool(args) with servers from initialize instructions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["execute", "search", "inspect", "help"],
                    "description": "Action to perform: execute (run code), search (find tools), inspect (get tool schemas), help (get documentation)",
                },
                "code": {
                    "type": "string",
                    "description": "Code expression (for action='execute' or 'inspect'). Execute: api.server('name').tool(args). Inspect: api.server('name').tool or api.server('name')",
                },
                "query": {
                    "type": "string",
                    "description": "Search query for tools (for action='search'). Returns descriptions only - use inspect for schemas.",
                },
                "namespace": {
                    "type": "string",
                    "description": "Optional namespace for context",
                },
                "timeout_secs": {
                    "type": "integer",
                    "description": "Execution timeout in seconds (for action='execute')",
                },
                "retries": {
                    "type": "integer",
                    "description": "Number of retries for failed tool calls (for action='execute', default: 0)",
                    "default": 0,
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum search depth (for action='search', default: 2)",
                    "default": 2,
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results per server (for action='search', default: 5)",
                    "default": 5,
                },
                "brief": {
                    "type": "boolean",
                    "description": "Return brief results (force max_depth=1, for action='search', default: false)",
                },
                "topic": {
                    "type": "string",
                    "description": "Help topic (for action='help', e.g., 'sandbox' for security restrictions)",
                },
                "trace": {
                    "type": "boolean",
                    "description": "Enable call tracing (for action='execute', default: false)",
                },
            },
            "required": ["action"],
        },
    },
]


# ============================================================================
# Exports
# ============================================================================

__all__ = [
    "META_TOOLS",
    "handle_tools_call",
    "handle_help",
    "handle_search",
    "handle_execute",
    "handle_trace",
    "handle_inspect",
]
