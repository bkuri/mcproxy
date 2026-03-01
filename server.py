"""FastAPI SSE server for MCProxy v2.0.

Exposes MCP protocol over Server-Sent Events (SSE).
Meta-tools: search and execute for api_manifest/api_sandbox integration.
"""

import asyncio
import json
from typing import Any, Callable, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
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

_connection_namespaces: Dict[int, str] = {}

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


def _validate_namespace(namespace: str) -> bool:
    """Validate that a namespace or group exists in the registry.

    Args:
        namespace: Namespace or group name to validate

    Returns:
        True if namespace/group exists, False otherwise
    """
    if capability_registry is None:
        return False
    servers, error = capability_registry.resolve_endpoint_to_servers(namespace)
    return error is None


def _get_namespace_from_request(request: Request) -> Optional[str]:
    """Extract namespace from request headers.

    Args:
        request: FastAPI request object

    Returns:
        Namespace name from X-Namespace header, or None
    """
    return request.headers.get("X-Namespace")


def _resolve_default_namespace() -> str:
    """Get the default namespace name.

    Returns:
        Default namespace name (empty string if no default set)
    """
    if capability_registry is None:
        return ""
    namespaces = capability_registry._namespaces
    if "default" in namespaces:
        return "default"
    if "public" in namespaces:
        return "public"
    return ""


@app.get("/sse/{namespace}")
async def sse_endpoint_namespaced(
    namespace: str, request: Request
) -> StreamingResponse:
    """SSE endpoint with namespace isolation.

    Args:
        namespace: Namespace name for server filtering
        request: FastAPI request object

    Returns:
        StreamingResponse for SSE events

    Raises:
        HTTPException: If namespace is invalid
    """
    if not _validate_namespace(namespace):
        logger.warning(f"[SSE_NAMESPACE] Invalid namespace: {namespace}")
        raise HTTPException(status_code=404, detail=f"Namespace not found: {namespace}")

    header_ns = _get_namespace_from_request(request)
    effective_ns = header_ns if header_ns else namespace

    if header_ns and header_ns != namespace:
        logger.warning(
            f"[SSE_NAMESPACE] URL namespace '{namespace}' overridden by header '{header_ns}'"
        )
        if not _validate_namespace(header_ns):
            raise HTTPException(
                status_code=404, detail=f"Namespace not found: {header_ns}"
            )
        effective_ns = header_ns

    logger.info(
        f"[SSE_NAMESPACE] New connection from {request.client} namespace={effective_ns}"
    )

    async def event_stream():
        """Generate SSE events."""
        try:
            endpoint_data: Dict[str, Any] = {
                "uri": "/message",
                "namespace": effective_ns,
            }
            yield f"event: endpoint\ndata: {json.dumps(endpoint_data)}\n\n"

            while True:
                if await request.is_disconnected():
                    logger.info(
                        f"[SSE_NAMESPACE] Client disconnected namespace={effective_ns}"
                    )
                    break

                await asyncio.sleep(30)
                heartbeat_data: Dict[str, Any] = {
                    "timestamp": asyncio.get_event_loop().time(),
                    "namespace": effective_ns,
                }
                yield f"event: heartbeat\ndata: {json.dumps(heartbeat_data)}\n\n"

        except asyncio.CancelledError:
            logger.info(
                f"[SSE_NAMESPACE] Connection cancelled namespace={effective_ns}"
            )
        except Exception as e:
            logger.error(f"[SSE_NAMESPACE] Error namespace={effective_ns}: {e}")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Namespace": effective_ns,
        },
    )


@app.get("/sse")
async def sse_endpoint(request: Request) -> StreamingResponse:
    """SSE endpoint for MCP protocol.

    Handles MCP initialization, tool listing, and tool calls over SSE.
    Supports X-Namespace header for namespace context.
    """
    header_ns = _get_namespace_from_request(request)
    default_ns = _resolve_default_namespace()
    effective_ns = header_ns if header_ns else default_ns

    if header_ns and not _validate_namespace(header_ns):
        logger.warning(f"[SSE] Invalid X-Namespace header: {header_ns}")
        raise HTTPException(status_code=404, detail=f"Namespace not found: {header_ns}")

    ns_info = f" namespace={effective_ns}" if effective_ns else ""
    logger.info(f"[SSE] New connection from {request.client}{ns_info}")

    async def event_stream():
        """Generate SSE events."""
        try:
            endpoint_data = {"uri": "/message"}
            if effective_ns:
                endpoint_data["namespace"] = effective_ns
            yield f"event: endpoint\ndata: {json.dumps(endpoint_data)}\n\n"

            while True:
                if await request.is_disconnected():
                    logger.info(f"[SSE] Client disconnected{ns_info}")
                    break

                await asyncio.sleep(30)
                heartbeat_data: Dict[str, Any] = {
                    "timestamp": asyncio.get_event_loop().time()
                }
                if effective_ns:
                    heartbeat_data["namespace"] = effective_ns
                yield f"event: heartbeat\ndata: {json.dumps(heartbeat_data)}\n\n"

        except asyncio.CancelledError:
            logger.info(f"[SSE] Connection cancelled{ns_info}")
        except Exception as e:
            logger.error(f"[SSE] Error{ns_info}: {e}")

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
    }
    if effective_ns:
        headers["X-Namespace"] = effective_ns

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers=headers,
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
    Supports X-Namespace header for namespace context.
    """
    try:
        body = await request.json()
        method = body.get("method")
        msg_id = body.get("id")
        params = body.get("params", {})

        header_ns = _get_namespace_from_request(request)
        if header_ns and not _validate_namespace(header_ns):
            logger.warning(f"[MESSAGE] Invalid X-Namespace header: {header_ns}")
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32602, "message": f"Invalid namespace: {header_ns}"},
            }

        ns_context = f" namespace={header_ns}" if header_ns else ""
        logger.debug(f"[MESSAGE] method={method}{ns_context}")

        if method == "initialize":
            return await handle_initialize(msg_id, params, namespace=header_ns)
        elif method == "tools/list":
            return await handle_tools_list(msg_id, namespace=header_ns)
        elif method == "tools/call":
            return await handle_tools_call(msg_id, params, namespace=header_ns)
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


async def handle_initialize(
    msg_id: Any, params: Dict[str, Any], namespace: Optional[str] = None
) -> Dict[str, Any]:
    """Handle MCP initialize request.

    Args:
        msg_id: JSON-RPC message ID
        params: Initialize parameters
        namespace: Optional namespace context from X-Namespace header

    Returns:
        MCP initialize response
    """
    result = {
        "protocolVersion": "2024-11-05",
        "capabilities": {"tools": {}},
        "serverInfo": {"name": "mcproxy", "version": "2.0.0"},
    }
    if namespace and capability_registry is not None:
        result["namespace"] = namespace
        ns_info = (
            capability_registry.resolve_namespace(namespace)
            if _validate_namespace(namespace)
            else []
        )
        result["namespaceInfo"] = {
            "name": namespace,
            "servers": ns_info,
        }

    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


async def handle_tools_list(
    msg_id: Any, namespace: Optional[str] = None
) -> Dict[str, Any]:
    """Handle tools/list request - return meta-tools only (v2.0).

    Args:
        msg_id: JSON-RPC message ID
        namespace: Optional namespace context for filtering

    Returns:
        MCP response with meta-tools list
    """
    return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": META_TOOLS}}


async def handle_tools_call(
    msg_id: Any, params: Dict[str, Any], namespace: Optional[str] = None
) -> Dict[str, Any]:
    """Handle tools/call request - route to search or execute.

    Args:
        msg_id: JSON-RPC message ID
        params: Tool call parameters
        namespace: Optional namespace context from X-Namespace header

    Returns:
        MCP response with tool result or error
    """
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    ns_context = f" namespace={namespace}" if namespace else ""
    logger.info(f"[META_TOOL_CALL] tool={tool_name}{ns_context}")

    try:
        if tool_name == "search":
            return await handle_search(
                msg_id, arguments, connection_namespace=namespace
            )
        elif tool_name == "execute":
            return await handle_execute(
                msg_id, arguments, connection_namespace=namespace
            )
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


async def handle_search(
    msg_id: Any, params: Dict, connection_namespace: Optional[str] = None
) -> Dict[str, Any]:
    """Handle search meta-tool.

    Args:
        msg_id: JSON-RPC message ID
        params: Search parameters (query, namespace, max_depth)
        connection_namespace: Namespace from connection context (X-Namespace header)

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

    param_namespace = params.get("namespace")
    effective_namespace = param_namespace or connection_namespace
    max_depth = params.get("max_depth", 2)

    log_ns = f" namespace={effective_namespace}" if effective_namespace else ""
    logger.debug(f"[SEARCH] query={query}{log_ns} max_depth={max_depth}")

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
        results = mq.search(query, namespace=effective_namespace, max_depth=max_depth)

        content = [{"type": "text", "text": json.dumps(results, indent=2)}]
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"content": content}}

    except Exception as e:
        logger.error(f"[SEARCH_ERROR] {e}")
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32000, "message": f"Search failed: {e}"},
        }


async def handle_execute(
    msg_id: Any, params: Dict, connection_namespace: Optional[str] = None
) -> Dict[str, Any]:
    """Handle execute meta-tool.

    Args:
        msg_id: JSON-RPC message ID
        params: Execution parameters (code, namespace, timeout_secs)
        connection_namespace: Namespace from connection context (X-Namespace header)

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

    param_namespace = params.get("namespace")
    effective_namespace = param_namespace or connection_namespace
    timeout_secs = params.get("timeout_secs")

    log_ns = f" namespace={effective_namespace}" if effective_namespace else ""
    logger.debug(f"[EXECUTE]{log_ns} timeout={timeout_secs}")

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

        if not effective_namespace:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32602,
                    "message": "Missing required parameter: namespace. "
                    "v2.0 requires explicit namespace for execute(). "
                    "Provide in params or via X-Namespace header.",
                },
            }

        result = sandbox_executor.execute(
            code, namespace=effective_namespace, timeout_secs=timeout_secs
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

    if config and "groups" in config:
        capability_registry._groups = config["groups"]

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
