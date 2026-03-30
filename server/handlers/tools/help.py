"""Meta-tool help handler."""

import json
from typing import Any, Dict


def handle_help(msg_id: Any, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle help action - return documentation about available actions.

    Args:
        msg_id: JSON-RPC message ID
        arguments: Help arguments (optional: topic)

    Returns:
        MCP response with help documentation
    """
    topic = arguments.get("topic", "").lower()

    if topic == "sandbox":
        help_data = {
            "topic": "sandbox",
            "description": "Security sandbox restrictions and blocked functions",
            "blocked_functions": [
                "eval()",
                "exec()",
                "compile()",
                "open() (file operations)",
                "input()",
                "__import__()",
                "breakpoint()",
                "hasattr()",
                "getattr()",
                "setattr()",
                "delattr()",
                "os.system()",
                "os.popen()",
                "subprocess.* (all subprocess calls)",
                "pickle.loads() / pickle.load()",
                "marshal.loads() / marshal.load()",
                "importlib.import_module()",
            ],
            "blocked_imports": [
                "os",
                "sys",
                "subprocess",
                "socket",
                "http",
                "urllib",
                "requests",
                "shutil",
                "tempfile",
                "multiprocessing",
                "pickle",
                "marshal",
                "importlib",
                "builtins",
            ],
            "how_to_check": {
                "blocked_functions": "get_blocked_functions()",
                "blocked_imports": "get_blocked_imports()",
                "blocked_attributes": "get_blocked_attributes()",
            },
            "examples": [
                {
                    "description": "Check blocked functions",
                    "code": "get_blocked_functions()",
                },
                {
                    "description": "Check blocked imports",
                    "code": "get_blocked_imports()",
                },
            ],
        }
    else:
        help_data = {
            "actions": {
                "execute": {
                    "description": "Run Python code with access to MCP tools",
                    "usage": "mcproxy(action='execute', code='...', namespace='...', timeout_secs=60, retries=0)",
                    "available_objects": {
                        "api": "Access MCP servers: api.server('name').tool(args)",
                        "parallel": "Execute multiple tool calls concurrently: parallel([lambda: ...])",
                        "mcproxy": "Call mcproxy from within code: mcproxy(action='search', ...)",
                    },
                    "parameters": {
                        "timeout_secs": "Optional execution timeout (default: 60 seconds)",
                        "retries": "Number of retries for failed tool calls (default: 0). Only retries on timeout/network errors with exponential backoff.",
                    },
                },
                "search": {
                    "description": "Discover available servers and tools (no schemas - use inspect for schemas)",
                    "usage": "mcproxy(action='search', query='...', namespace='...')",
                },
                "inspect": {
                    "description": "Get detailed schemas for a server's tools (parameters, types, required fields)",
                    "usage": "mcproxy(action='inspect', server='name', namespace='...')",
                },
                "help": {
                    "description": "Get help and documentation",
                    "usage": "mcproxy(action='help') or mcproxy(action='help', topic='sandbox')",
                    "available_topics": ["sandbox"],
                },
            },
            "examples": [
                {
                    "description": "Discover available servers",
                    "code": "mcproxy(action='search', query='', namespace='dev')",
                },
                {
                    "description": "Call a tool on a server",
                    "code": "mcproxy(action='execute', code='api.server(\"wikipedia\").search(query=\"Python\")', namespace='dev')",
                },
                {
                    "description": "Inspect tool schemas",
                    "code": "mcproxy(action='inspect', server='wikipedia', namespace='dev')",
                },
                {
                    "description": "Get sandbox restrictions",
                    "code": "mcproxy(action='help', topic='sandbox')",
                },
                {
                    "description": "Run parallel tool calls (faster than sequential)",
                    "code": 'mcproxy(action=\'execute\', code=\'results = parallel([\\n    lambda: api.server("wikipedia").search(query="Python"),\\n    lambda: api.server("wikipedia").search(query="JavaScript")\\n])\', namespace=\'dev\')',
                },
            ],
            "quick_start": {
                "step_1_discover": "mcproxy(action='search', query='', namespace='dev')",
                "step_2_inspect": "mcproxy(action='inspect', server='wikipedia', namespace='dev')",
                "step_3_execute": "mcproxy(action='execute', code='api.server(\"wikipedia\").search(query=\"Python\")', namespace='dev')",
            },
            "tips": {
                "parallel_execution": "Use parallel() for multiple tool calls - much faster than sequential",
                "timeout_errors": "If you see timeout errors, they're from upstream MCP servers (not mcproxy). Try increasing timeout_secs or use retries=3 for automatic retry.",
                "server_discovery": "Use search(query='') to list all available servers and their tool counts",
                "automatic_retries": "Use retries=N to automatically retry failed tool calls. Only retries on timeout/network errors with exponential backoff (100ms, 200ms, 400ms, ...).",
            },
        }

    content = [{"type": "text", "text": json.dumps(help_data)}]
    return {"jsonrpc": "2.0", "id": msg_id, "result": {"content": content}}
