"""FastAPI SSE server for MCProxy v3.1.

Exposes MCP protocol over Server-Sent Events (SSE).
Single meta-tool: mcproxy with actions (execute, search, inspect).
"""

from typing import Any, Callable, Dict, List, Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from manifest import CapabilityRegistry, EventHookManager
from sandbox import SandboxExecutor
from logging_config import get_logger

from server.sse import register_sse_endpoints
from server.handlers import create_message_handler
from server.lifecycle import (
    capability_registry,
    event_hook_manager,
    sandbox_executor,
    session_manager,
    _tool_executor,
    set_server_manager as _set_server_manager,
    init_v2_components as _init_v2_components,
    refresh_manifest as _refresh_manifest,
    on_config_change as _on_config_change,
    on_server_health as _on_server_health,
    get_capability_registry,
    get_sandbox_executor,
    get_session_manager,
    get_tool_executor,
)

logger = get_logger(__name__)

app = FastAPI(title="MCProxy", version="3.2.0")


_handle_message = create_message_handler(
    capability_registry_getter=get_capability_registry,
    sandbox_executor_getter=get_sandbox_executor,
    session_manager_getter=get_session_manager,
    tool_executor_getter=get_tool_executor,
)

register_sse_endpoints(
    app,
    capability_registry_getter=get_capability_registry,
    handle_message=_handle_message,
)


@app.post("/message")
async def handle_message(request: Any) -> Dict[str, Any]:
    """Handle MCP messages at /message endpoint."""
    return await _handle_message(request)


@app.get("/health")
async def health() -> Dict[str, Any]:
    """Health check endpoint with protocol information."""
    return {
        "status": "healthy",
        "version": app.version,
        "protocol": "MCP over SSE",
        "hint": "Use POST /sse with JSON-RPC, not REST endpoints",
        "available_tools": ["mcproxy"],
        "endpoints": {
            "health": "GET /health",
            "sse": "POST /sse (MCP JSON-RPC)",
            "namespaced_sse": "POST /sse/{namespace} (MCP JSON-RPC)",
        },
        "example_usage": {
            "list_tools": {
                "method": "POST /sse",
                "body": {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            },
            "execute_code": {
                "method": "POST /sse",
                "headers": {"X-Namespace": "dev"},
                "body": {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "mcproxy",
                        "arguments": {"action": "execute", "code": "1+1"},
                    },
                },
            },
        },
    }


@app.exception_handler(404)
async def custom_404_handler(request: Any, exc: Any) -> JSONResponse:
    """Provide helpful error message for 404s - agents often try REST endpoints."""
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not Found",
            "hint": "MCProxy uses MCP Protocol (JSON-RPC), not REST endpoints",
            "correct_usage": {
                "list_tools": "POST /sse with {'jsonrpc':'2.0','id':1,'method':'tools/list'}",
                "call_tool": "POST /sse with {'jsonrpc':'2.0','id':1,'method':'tools/call','params':{...}}",
                "health_check": "GET /health",
            },
            "example": 'curl -X POST http://localhost:12010/sse -H \'Content-Type: application/json\' -d \'{"jsonrpc":"2.0","id":1,"method":"tools/list"}\'',
            "documentation": "https://github.com/bkuri/mcproxy/blob/main/README.md",
        },
    )


def set_server_manager(manager: Any) -> None:
    """Set the global server manager reference (for backward compatibility)."""
    _set_server_manager(manager)


def init_v2_components(
    config: Optional[Dict] = None,
    tool_executor: Optional[Callable] = None,
    servers_tools: Optional[Dict[str, List]] = None,
) -> None:
    """Initialize v3.0 components: CapabilityRegistry and SandboxExecutor.

    Args:
        config: Optional configuration dict for components
        tool_executor: Callable to execute tools (server_name, tool_name, args) -> result
        servers_tools: Dict mapping server name to list of tools (from server_manager.get_all_tools())
    """
    _init_v2_components(config, tool_executor, servers_tools)


def refresh_manifest(servers_tools: Dict[str, List]) -> None:
    """Refresh the manifest when servers finish loading tools.

    Args:
        servers_tools: Dict mapping server name to list of tools
    """
    _refresh_manifest(servers_tools)


def on_config_change(new_config: Dict) -> None:
    """Handle config change event - reload manifests and sandbox config.

    Args:
        new_config: New configuration dict
    """
    _on_config_change(new_config)


def on_server_health(server_name: str, healthy: bool) -> None:
    """Handle server health change event.

    Args:
        server_name: Name of the affected server
        healthy: Whether the server is now healthy
    """
    _on_server_health(server_name, healthy)


__all__ = [
    "app",
    "set_server_manager",
    "init_v2_components",
    "refresh_manifest",
    "on_config_change",
    "on_server_health",
    "get_capability_registry",
]
