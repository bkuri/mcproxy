"""FastAPI SSE server for MCProxy v2.0.

Exposes MCP protocol over Server-Sent Events (SSE).
Meta-tools: search and execute for api_manifest/api_sandbox integration.
"""

import asyncio
import json
from typing import Any, Callable, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from api_manifest import CapabilityRegistry, EventHookManager, ManifestQuery
from api_sandbox import SandboxExecutor, SandboxManifest
from logging_config import get_logger

logger = get_logger(__name__)

server_manager: Optional[Any] = None
capability_registry: Optional[CapabilityRegistry] = None
event_hook_manager: Optional[EventHookManager] = None
sandbox_executor: Optional[SandboxExecutor] = None
_tool_executor: Optional[Callable] = None

app = FastAPI(title="MCProxy", version="2.0.0")

META_TOOLS = [
    {
        "name": "search",
        "description": "Search for tools and capabilities in the manifest registry. "
        "Returns matching tools with metadata and usage examples.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural language search query for tools",
                },
                "namespace": {
                    "type": "string",
                    "description": "Optional namespace to filter results",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum search depth (default: 2)",
                    "default": 2,
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "execute",
        "description": "Execute a tool in a sandboxed environment. "
        "Returns execution results with safety validation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Code or command to execute",
                },
                "namespace": {
                    "type": "string",
                    "description": "Optional namespace for execution context",
                },
                "timeout_secs": {
                    "type": "integer",
                    "description": "Execution timeout in seconds",
                },
            },
            "required": ["code"],
        },
    },
]


@app.get("/sse")
async def sse_endpoint(request: Request) -> StreamingResponse:
    """SSE endpoint for MCP protocol.

    Handles MCP initialization, tool listing, and tool calls over SSE.
    """
    logger.info(f"New SSE connection from {request.client}")

    async def event_stream():
        """Generate SSE events."""
        try:
            yield f"event: endpoint\ndata: {json.dumps({'uri': '/message'})}\n\n"

            while True:
                if await request.is_disconnected():
                    logger.info("Client disconnected")
                    break

                await asyncio.sleep(30)
                yield f"event: heartbeat\ndata: {json.dumps({'timestamp': asyncio.get_event_loop().time()})}\n\n"

        except asyncio.CancelledError:
            logger.info("SSE connection cancelled")
        except Exception as e:
            logger.error(f"SSE error: {e}")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@app.post("/sse")
async def handle_sse_message(request: Request) -> Dict[str, Any]:
    """Handle MCP POST messages at /sse (for OpenCode compatibility)."""
    return await handle_message(request)


@app.post("/message")
async def handle_message(request: Request) -> Dict[str, Any]:
    """Handle MCP messages from clients.

    Processes initialize, tools/list, and tools/call requests.
    v2.0 only supports search and execute meta-tools.
    """
    try:
        body = await request.json()
        method = body.get("method")
        msg_id = body.get("id")
        params = body.get("params", {})

        logger.debug(f"Received message: {method}")

        if method == "initialize":
            return await handle_initialize(msg_id, params)
        elif method == "tools/list":
            return await handle_tools_list(msg_id)
        elif method == "tools/call":
            return await handle_tools_call(msg_id, params)
        else:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }

    except json.JSONDecodeError:
        return {"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}}
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        return {"jsonrpc": "2.0", "error": {"code": -32000, "message": str(e)}}


async def handle_initialize(msg_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle MCP initialize request."""
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "mcproxy", "version": "2.0.0"},
        },
    }


async def handle_tools_list(msg_id: Any) -> Dict[str, Any]:
    """Handle tools/list request - return meta-tools only (v2.0)."""
    return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": META_TOOLS}}


async def handle_tools_call(msg_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle tools/call request - route to search or execute."""
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    logger.info(f"[META_TOOL_CALL] tool={tool_name}")

    try:
        if tool_name == "search":
            return await handle_search(msg_id, arguments)
        elif tool_name == "execute":
            return await handle_execute(msg_id, arguments)
        else:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32601,
                    "message": f"Unknown tool: {tool_name}. v2.0 only supports 'search' and 'execute'.",
                },
            }
    except Exception as e:
        logger.error(f"[META_TOOL_ERROR] {tool_name}: {e}")
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32000, "message": f"Tool execution failed: {e}"},
        }


async def handle_search(msg_id: Any, params: Dict) -> Dict[str, Any]:
    """Handle search meta-tool.

    Args:
        msg_id: JSON-RPC message ID
        params: Search parameters (query, namespace, max_depth)

    Returns:
        MCP response with search results
    """
    query = params.get("query", "")
    if query is None:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32602, "message": "Missing required parameter: query"},
        }

    namespace = params.get("namespace")
    max_depth = params.get("max_depth", 2)

    logger.debug(f"[SEARCH] query={query} namespace={namespace} max_depth={max_depth}")

    try:
        if capability_registry is None:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32000,
                    "message": "Capability registry not initialized",
                },
            }

        mq = ManifestQuery(capability_registry)
        results = mq.search(query, namespace=namespace, max_depth=max_depth)

        content = [{"type": "text", "text": json.dumps(results, indent=2)}]
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"content": content}}

    except Exception as e:
        logger.error(f"[SEARCH_ERROR] {e}")
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32000, "message": f"Search failed: {e}"},
        }


async def handle_execute(msg_id: Any, params: Dict) -> Dict[str, Any]:
    """Handle execute meta-tool.

    Args:
        msg_id: JSON-RPC message ID
        params: Execution parameters (code, namespace, timeout_secs)

    Returns:
        MCP response with execution result
    """
    code = params.get("code")
    if not code:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32602, "message": "Missing required parameter: code"},
        }

    namespace = params.get("namespace")
    timeout_secs = params.get("timeout_secs")

    logger.debug(f"[EXECUTE] namespace={namespace} timeout={timeout_secs}")

    try:
        if sandbox_executor is None:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32000,
                    "message": "Sandbox executor not initialized",
                },
            }

        if not namespace:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32602,
                    "message": "Missing required parameter: namespace. "
                    "v2.0 requires explicit namespace for execute().",
                },
            }

        result = sandbox_executor.execute(
            code, namespace=namespace, timeout_secs=timeout_secs
        )

        content = [{"type": "text", "text": json.dumps(result, indent=2)}]
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"content": content}}

    except Exception as e:
        logger.error(f"[EXECUTE_ERROR] {e}")
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32000, "message": f"Execution failed: {e}"},
        }


def set_server_manager(manager: Any) -> None:
    """Set the global server manager reference (for backward compatibility)."""
    global server_manager
    server_manager = manager


def init_v2_components(
    config: Optional[Dict] = None,
    tool_executor: Optional[Callable] = None,
    servers_tools: Optional[Dict[str, List]] = None,
) -> None:
    """Initialize v2.0 components: CapabilityRegistry and SandboxExecutor.

    Args:
        config: Optional configuration dict for components
        tool_executor: Callable to execute tools (server_name, tool_name, args) -> result
        servers_tools: Dict mapping server name to list of tools (from server_manager.get_all_tools())
    """
    global capability_registry, sandbox_executor, event_hook_manager, _tool_executor

    config = config or {}
    _tool_executor = tool_executor

    capability_registry = CapabilityRegistry()

    if config and "namespaces" in config:
        capability_registry._namespaces = config["namespaces"]

    if servers_tools:
        logger.info(f"[V2_INIT] Building manifest from {len(servers_tools)} servers")
        capability_registry.build(servers_tools)
    else:
        logger.warning("[V2_INIT] No servers_tools provided, manifest will be empty")

    event_hook_manager = EventHookManager(capability_registry)

    if tool_executor and capability_registry:
        sandbox_manifest = SandboxManifest(
            servers=capability_registry._manifest.get("servers", {}),
            namespaces=capability_registry._namespaces,
        )
        sandbox_executor = SandboxExecutor(
            manifest=sandbox_manifest,
            tool_executor=tool_executor,
            uv_path=config.get("sandbox", {}).get("uv_path", "uv"),
            default_timeout_secs=config.get("sandbox", {}).get("timeout_secs", 30),
        )

    _log_manifest_stats()


def refresh_manifest(servers_tools: Dict[str, List]) -> None:
    """Refresh the manifest when servers finish loading tools.

    Args:
        servers_tools: Dict mapping server name to list of tools
    """
    global capability_registry, sandbox_executor, _tool_executor

    if capability_registry is None:
        logger.warning("[REFRESH_MANIFEST] CapabilityRegistry not initialized")
        return

    logger.info(
        f"[REFRESH_MANIFEST] Rebuilding manifest from {len(servers_tools)} servers"
    )
    capability_registry.build(servers_tools)

    if sandbox_executor and capability_registry:
        sandbox_executor._manifest = SandboxManifest(
            servers=capability_registry._manifest.get("servers", {}),
            namespaces=capability_registry._namespaces,
        )

    _log_manifest_stats()


def _log_manifest_stats() -> None:
    """Log current manifest statistics."""
    tool_count = (
        capability_registry._manifest.get("tool_count", 0) if capability_registry else 0
    )
    server_count = (
        len(capability_registry._manifest.get("servers", {}))
        if capability_registry
        else 0
    )
    logger.info(f"[MANIFEST_STATS] {server_count} servers, {tool_count} tools")


def on_config_change(new_config: Dict) -> None:
    """Handle config change event - reload manifests and sandbox config.

    Args:
        new_config: New configuration dict
    """
    logger.info("[CONFIG_CHANGE] Reloading v2.0 components")
    if event_hook_manager:
        event_hook_manager.trigger("config_change", {"config": new_config})


def on_server_health(server_name: str, healthy: bool) -> None:
    """Handle server health change event.

    Args:
        server_name: Name of the affected server
        healthy: Whether the server is now healthy
    """
    status = "healthy" if healthy else "unhealthy"
    logger.info(f"[SERVER_HEALTH] {server_name} is now {status}")
    if event_hook_manager:
        event_hook_manager.trigger(
            "server_health", {"server": server_name, "healthy": healthy}
        )
