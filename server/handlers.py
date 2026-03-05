"""MCP protocol handlers and meta-tool handlers for MCProxy."""

import asyncio
import json
from typing import Any, Callable, Dict, Optional

from fastapi import Request

from manifest import CapabilityRegistry, ManifestQuery
from manifest.typescript_gen import generate_compact_instructions
from sandbox import SandboxExecutor, AccessControlConfig
from logging_config import get_logger
from session_stash import SessionManager, SessionStash

from .sse import (
    get_namespace_from_request,
    get_session_id_from_request,
    validate_namespace,
)

logger = get_logger(__name__)

META_TOOLS = [
    {
        "name": "search",
        "description": "OPTIONAL - Only use if you don't know the server/tool name. "
        "Available servers are listed in the initialize instructions. "
        "Skip this and call execute directly with api.server('name').tool(args). "
        "Returns matching tools with metadata.",
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
            "required": [],
        },
    },
    {
        "name": "execute",
        "description": "Execute Python code with tool access via api.server('name').tool(args). "
        "Tools return results immediately. Use only the servers listed in the initialize instructions. "
        "Use .inspect() on any tool to get its schema. "
        "Use parallel([...]) for concurrent execution (rare).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to execute",
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


# Global config storage for MCP client config and mcproxy.json config
_mcp_config: dict = {}
_mcproxy_config: dict = {}


def set_mcproxy_config(config: dict) -> None:
    """Set the mcproxy.json configuration.

    Args:
        config: Configuration dictionary from mcproxy.json
    """
    global _mcproxy_config
    _mcproxy_config = config


def get_mcproxy_config() -> dict:
    """Get the mcproxy.json configuration.

    Returns:
        Configuration dictionary from mcproxy.json
    """
    return _mcproxy_config


async def handle_initialize(
    msg_id: Any,
    params: Dict[str, Any],
    namespace: Optional[str] = None,
    capability_registry: Optional[CapabilityRegistry] = None,
) -> Dict[str, Any]:
    """Handle MCP initialize request.

    Args:
        msg_id: JSON-RPC message ID
        params: Initialize parameters (may contain 'config' from MCP client)
        namespace: Optional namespace context from X-Namespace header
        capability_registry: Capability registry instance

    Returns:
        MCP initialize response
    """
    # Store client config if provided
    global _mcp_config
    if isinstance(params, dict) and params.get("config"):
        _mcp_config = params.get("config", {})

    result = {
        "protocolVersion": "2024-11-05",
        "capabilities": {"tools": {}},
        "serverInfo": {"name": "mcproxy", "version": "3.0.0"},
    }

    # Generate TypeScript-style instructions from manifest
    if capability_registry and capability_registry._manifest:
        logger.debug(
            f"Manifest has {len(capability_registry._manifest.get('tools_by_server', {}))} servers with tools"
        )
        # Merge configs: mcproxy.json takes precedence over MCP client config
        merged_config = {**_mcp_config, **_mcproxy_config}
        instructions = generate_compact_instructions(
            capability_registry._manifest, config=merged_config
        )
        result["instructions"] = instructions
    else:
        logger.warning("No capability registry or manifest available during initialize")

    if namespace and capability_registry is not None:
        result["namespace"] = namespace
        servers, _ = capability_registry.resolve_namespace_to_servers(namespace)
        result["namespaceInfo"] = {
            "name": namespace,
            "servers": servers,
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
    msg_id: Any,
    params: Dict[str, Any],
    namespace: Optional[str] = None,
    session_id: Optional[str] = None,
    capability_registry: Optional[CapabilityRegistry] = None,
    sandbox_executor: Optional[SandboxExecutor] = None,
    session_manager: Optional[SessionManager] = None,
    tool_executor: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Handle tools/call request - route to search or execute.

    Args:
        msg_id: JSON-RPC message ID
        params: Tool call parameters
        namespace: Optional namespace context from X-Namespace header
        session_id: Optional session ID from X-Session-ID header
        capability_registry: Capability registry instance
        sandbox_executor: Sandbox executor instance
        session_manager: Session manager instance
        tool_executor: Callable to execute tools

    Returns:
        MCP response with tool result or error
    """
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    ns_context = f" namespace={namespace}" if namespace else ""
    sess_context = f" session={session_id}" if session_id else ""
    logger.info(f"[META_TOOL_CALL] tool={tool_name}{ns_context}{sess_context}")
    logger.info(
        f"[HTTP_HANDLER_ARGS] tool={tool_name} arguments={arguments} type={type(arguments)}"
    )

    try:
        # Support both prefixed (mcproxy_*) and non-prefixed names as aliases
        canonical_name = tool_name.replace("mcproxy_", "")

        if canonical_name == "search":
            # Get config for search (merge mcproxy.json + MCP client config)
            merged_config = {**_mcproxy_config, **_mcp_config}
            search_config = merged_config.get("search", {})
            min_words = search_config.get("min_words", 2)
            max_tools = search_config.get("max_tools", 5)

            return await handle_search(
                msg_id,
                arguments,
                connection_namespace=namespace,
                capability_registry=capability_registry,
                min_words=min_words,
                max_tools=max_tools,
            )

        elif canonical_name == "execute":
            return await handle_execute(
                msg_id,
                arguments,
                connection_namespace=namespace,
                session_id=session_id,
                sandbox_executor=sandbox_executor,
                session_manager=session_manager,
                tool_executor=tool_executor,
            )
        else:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32601,
                    "message": f"Unknown tool: {tool_name}. v2.0 supports 'search', 'execute', 'mcproxy_search', or 'mcproxy_execute'.",
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
    msg_id: Any,
    params: Dict,
    connection_namespace: Optional[str] = None,
    capability_registry: Optional[CapabilityRegistry] = None,
    min_words: int = 2,
    max_tools: int = 5,
) -> Dict[str, Any]:
    """Handle search meta-tool.

    Args:
        msg_id: JSON-RPC message ID
        params: Search parameters (query, namespace, max_depth)
        connection_namespace: Namespace from connection context (X-Namespace header)
        capability_registry: Capability registry instance
        min_words: Minimum words to trigger depth=2 (default: 2)
        max_tools: Maximum tools to return at depth=2 (default: 5)

    Returns:
        MCP response with search results
    """
    query = params.get("query", "")

    param_namespace = params.get("namespace")
    effective_namespace = param_namespace or connection_namespace
    # Get depth override from params
    effective_depth = params.get("depth", None)

    # Count words in query
    query_words = query.strip().split() if query else []

    # Default to depth=1 for empty/short queries (concise), depth=2 for specific queries
    # min_words <= 0 means always use depth=2
    if min_words <= 0:
        default_depth = 2  # Always show schemas
    else:
        default_depth = 1 if not query or len(query_words) < min_words else 2
    max_depth = effective_depth if effective_depth is not None else default_depth

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
        results = mq.search(
            query,
            namespace=effective_namespace,
            max_depth=max_depth,
            max_tools=max_tools,
        )

        if not effective_namespace:
            results["warning"] = (
                "No namespace specified. Results include default servers only. "
                "Isolated namespaces (e.g., 'system', 'home') require explicit namespace parameter."
            )

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
    msg_id: Any,
    params: Dict,
    connection_namespace: Optional[str] = None,
    session_id: Optional[str] = None,
    sandbox_executor: Optional[SandboxExecutor] = None,
    session_manager: Optional[SessionManager] = None,
    tool_executor: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Handle execute meta-tool.

    Args:
        msg_id: JSON-RPC message ID
        params: Execution parameters (code, namespace, timeout_secs)
        connection_namespace: Namespace from connection context (X-Namespace header)
        session_id: Optional session ID for session-scoped storage
        sandbox_executor: Sandbox executor instance
        session_manager: Session manager instance
        tool_executor: Callable to execute tools

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
    log_sess = f" session={session_id}" if session_id else ""
    logger.debug(f"[EXECUTE]{log_ns}{log_sess} timeout={timeout_secs}")

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

        session: Optional[SessionStash] = None
        if session_manager is not None:
            session = await session_manager.get_or_create(session_id)

        result = await sandbox_executor.execute(
            code,
            namespace=effective_namespace,
            timeout_secs=timeout_secs,
            session=session,
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


def create_message_handler(
    capability_registry_getter: Callable[[], Optional[CapabilityRegistry]],
    sandbox_executor_getter: Callable[[], Optional[SandboxExecutor]],
    session_manager_getter: Callable[[], Optional[SessionManager]],
    tool_executor_getter: Callable[[], Optional[Callable]],
) -> Callable:
    """Create a message handler with dependency injection.

    Args:
        capability_registry_getter: Callable that returns capability registry
        sandbox_executor_getter: Callable that returns sandbox executor
        session_manager_getter: Callable that returns session manager
        tool_executor_getter: Callable that returns tool executor

    Returns:
        Async message handler function
    """

    async def handle_message(
        request: Request, path_namespace: Optional[str] = None
    ) -> Dict[str, Any]:
        """Handle MCP messages from clients.

        Processes initialize, tools/list, and tools/call requests.
        v2.0 only supports search and execute meta-tools.
        Supports X-Namespace header for namespace context.
        Supports X-Session-ID header for session context.

        Args:
            request: FastAPI request object
            path_namespace: Namespace from URL path (takes precedence over header)
        """
        capability_registry = capability_registry_getter()
        sandbox_executor = sandbox_executor_getter()
        session_manager = session_manager_getter()
        tool_executor = tool_executor_getter()

        try:
            body = await request.json()
            method = body.get("method")
            msg_id = body.get("id")
            params = body.get("params", {})

            header_ns = path_namespace or get_namespace_from_request(request)
            if header_ns and not validate_namespace(header_ns, capability_registry):
                logger.warning(f"[MESSAGE] Invalid X-Namespace header: {header_ns}")
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {
                        "code": -32602,
                        "message": f"Invalid namespace: {header_ns}",
                    },
                }

            session_id = get_session_id_from_request(request)

            ns_context = f" namespace={header_ns}" if header_ns else ""
            sess_context = f" session={session_id}" if session_id else ""
            logger.debug(f"[MESSAGE] method={method}{ns_context}{sess_context}")

            if method == "initialize":
                return await handle_initialize(
                    msg_id,
                    params,
                    namespace=header_ns,
                    capability_registry=capability_registry,
                )
            elif method == "tools/list":
                return await handle_tools_list(msg_id, namespace=header_ns)
            elif method == "tools/call":
                return await handle_tools_call(
                    msg_id,
                    params,
                    namespace=header_ns,
                    session_id=session_id,
                    capability_registry=capability_registry,
                    sandbox_executor=sandbox_executor,
                    session_manager=session_manager,
                    tool_executor=tool_executor,
                )
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }

        except json.JSONDecodeError:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32700, "message": "Parse error"},
            }
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            return {"jsonrpc": "2.0", "error": {"code": -32000, "message": str(e)}}

    return handle_message
