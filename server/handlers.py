"""MCP protocol handlers and meta-tool handlers for MCProxy."""

import asyncio
import json
import re
import sys
import traceback as traceback_module
from typing import Any, Callable, Dict, List, Optional

from fastapi import Request
from fastapi.responses import StreamingResponse

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
        "Use only the servers listed in the initialize instructions.",
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
    {
        "name": "sequence",
        "description": "Execute read and optional transform/write in a single call. "
        "Use for any tool operation: single reads, file modifications, config updates. "
        "Write optional - omit for read-only operations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "read": {
                    "type": "object",
                    "description": "Read operation specification",
                    "properties": {
                        "server": {"type": "string"},
                        "tool": {"type": "string"},
                        "args": {"type": "object"},
                    },
                    "required": ["server", "tool"],
                },
                "transform": {
                    "type": "string",
                    "description": "Python code to transform read_result. "
                    "'read_result' is extracted content from read step. "
                    "Must set 'result' variable with write args. Available: json, re, sys, stash. "
                    "Optional for simple read operations.",
                },
                "write": {
                    "type": "object",
                    "description": "Write operation specification (optional). "
                    "Omit for read-only operations.",
                    "properties": {
                        "server": {"type": "string"},
                        "tool": {"type": "string"},
                    },
                    "required": ["server", "tool"],
                },
                "timeout_secs": {
                    "type": "number",
                    "description": "Timeout in seconds (default: 30)",
                },
            },
            "required": ["read"],
        },
    },
]


# Global config storage for MCP client config
_mcp_config: dict = {}


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
        "serverInfo": {"name": "mcproxy", "version": "2.0.0"},
    }

    # Generate TypeScript-style instructions from manifest
    if capability_registry and capability_registry._manifest:
        logger.debug(
            f"Manifest has {len(capability_registry._manifest.get('tools_by_server', {}))} servers with tools"
        )
        instructions = generate_compact_instructions(
            capability_registry._manifest, config=_mcp_config
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

    try:
        if tool_name == "search":
            # Get config for search
            search_config = _mcp_config.get("search", {})
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

        elif tool_name == "execute":
            return await handle_execute(
                msg_id,
                arguments,
                connection_namespace=namespace,
                session_id=session_id,
                sandbox_executor=sandbox_executor,
                session_manager=session_manager,
                tool_executor=tool_executor,
            )
        elif tool_name == "sequence":
            return await handle_sequence(
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

        result = sandbox_executor.execute(
            code,
            namespace=effective_namespace,
            timeout_secs=timeout_secs,
            session=session,
        )

        pending_calls = result.get("deferred_calls", [])
        if pending_calls and tool_executor:
            call_results = []
            for call in pending_calls:
                server = call.get("server")
                tool = call.get("tool")
                args = call.get("args", {})
                try:
                    call_result = tool_executor(server, tool, args)
                    if asyncio.iscoroutine(call_result):
                        call_result = await call_result
                    call_results.append(
                        {
                            "server": server,
                            "tool": tool,
                            "status": "success",
                            "result": call_result,
                        }
                    )
                except Exception as e:
                    call_results.append(
                        {
                            "server": server,
                            "tool": tool,
                            "status": "error",
                            "error": str(e),
                        }
                    )
            result["tool_results"] = call_results

        content = [{"type": "text", "text": json.dumps(result, indent=2)}]
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"content": content}}

    except Exception as e:
        logger.error(f"[EXECUTE_ERROR] {e}")
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32000, "message": f"Execution failed: {e}"},
        }


async def handle_sequence(
    msg_id: Any,
    params: Dict[str, Any],
    connection_namespace: Optional[str] = None,
    session_id: Optional[str] = None,
    sandbox_executor: Optional[SandboxExecutor] = None,
    session_manager: Optional[SessionManager] = None,
    tool_executor: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Handle sequence meta-tool for read-transform-write operations.

    Args:
        msg_id: JSON-RPC message ID
        params: Sequence parameters (read, transform, write, timeout_secs)
        connection_namespace: Namespace from connection context (X-Namespace header)
        session_id: Optional session ID for session-scoped storage
        sandbox_executor: Sandbox executor instance
        session_manager: Session manager instance
        tool_executor: Callable to execute tools

    Returns:
        MCP response with read/transform/write results
    """
    read_spec = params.get("read")
    transform_code = params.get("transform")
    write_spec = params.get("write")
    timeout_secs = params.get("timeout_secs", 30)

    if not read_spec:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32602, "message": "Missing required parameter: read"},
        }

    if tool_executor is None:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32000, "message": "Tool executor not initialized"},
        }

    session: Optional[SessionStash] = None
    if session_manager is not None:
        session = await session_manager.get_or_create(session_id)

    result: Dict[str, Any] = {
        "read_result": None,
        "transform_result": None,
        "write_result": None,
    }

    try:
        read_server = read_spec.get("server")
        read_tool = read_spec.get("tool")
        read_args = read_spec.get("args", {})

        if not read_server or not read_tool:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32602,
                    "message": "Read spec requires 'server' and 'tool' fields",
                },
            }

        logger.debug(f"[SEQUENCE] READ: server={read_server} tool={read_tool}")
        read_result_raw = tool_executor(read_server, read_tool, read_args)
        if asyncio.iscoroutine(read_result_raw):
            read_result_raw = await read_result_raw

        # Store raw result for debugging, but use extracted data
        result["read_result_raw"] = read_result_raw
        result["read_result"] = data  # What was actually provided to transform

    except Exception as e:
        logger.error(f"[SEQUENCE_ERROR] READ step failed: {e}")
        result["error"] = {"step": "read", "message": str(e)}
        content = [{"type": "text", "text": json.dumps(result, indent=2)}]
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"content": content}}

    # Extract data from read result
    data = _extract_data_from_tool_result(read_result_raw)

    # TRANSFORM step (optional)
    transform_result = data
    if transform_code:
        try:
            local_vars: Dict[str, Any] = {
                "read_result": data,
                "json": json,
                "re": re,
                "sys": sys,
                "result": None,
            }

            if session is not None:
                local_vars["stash"] = _SyncStashWrapper(session)

            exec(transform_code, {"__builtins__": __builtins__}, local_vars)

            transform_result = local_vars.get("result")
            if transform_result is None:
                raise ValueError("Transform code must set 'result' variable")

            result["transform_result"] = transform_result
            logger.debug(f"[SEQUENCE] TRANSFORM: completed")

        except Exception as e:
            tb = traceback_module.format_exc()
            logger.error(f"[SEQUENCE_ERROR] TRANSFORM step failed: {e}")
            result["error"] = {"step": "transform", "message": str(e), "traceback": tb}
            content = [{"type": "text", "text": json.dumps(result, indent=2)}]
            return {"jsonrpc": "2.0", "id": msg_id, "result": {"content": content}}
    else:
        # No transform - use data directly
        result["transform_result"] = data

    # WRITE step (optional - skip if no write spec)
    if write_spec:
        try:
            write_server = write_spec.get("server")
            write_tool = write_spec.get("tool")

            if not write_server or not write_tool:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {
                        "code": -32602,
                        "message": "Write spec requires 'server' and 'tool' fields",
                    },
                }

            logger.debug(f"[SEQUENCE] WRITE: server={write_server} tool={write_tool}")
            write_result_raw = tool_executor(write_server, write_tool, transform_result)
            if asyncio.iscoroutine(write_result_raw):
                write_result_raw = await write_result_raw

            result["write_result"] = write_result_raw

        except Exception as e:
            logger.error(f"[SEQUENCE_ERROR] WRITE step failed: {e}")
            result["error"] = {"step": "write", "message": str(e)}
            content = [{"type": "text", "text": json.dumps(result, indent=2)}]
            return {"jsonrpc": "2.0", "id": msg_id, "result": {"content": content}}

    content = [{"type": "text", "text": json.dumps(result, indent=2)}]
    return {"jsonrpc": "2.0", "id": msg_id, "result": {"content": content}}


def _extract_data_from_tool_result(tool_result: Any) -> Any:
    """Extract data from tool result, handling different response formats.

    Args:
        tool_result: Raw tool result from tool_executor

    Returns:
        Extracted data (typically string content)
    """
    if isinstance(tool_result, str):
        return tool_result

    if isinstance(tool_result, dict):
        if "content" in tool_result:
            content = tool_result["content"]
            if isinstance(content, list) and len(content) > 0:
                first_content = content[0]
                if isinstance(first_content, dict) and "text" in first_content:
                    return first_content["text"]
            return content

        if "result" in tool_result:
            inner = tool_result["result"]
            if isinstance(inner, dict):
                if "content" in inner:
                    content = inner["content"]
                    if isinstance(content, list) and len(content) > 0:
                        first_content = content[0]
                        if isinstance(first_content, dict) and "text" in first_content:
                            return first_content["text"]
                    return content
            return inner

    return tool_result


class _SyncStashWrapper:
    """Synchronous wrapper for async SessionStash to use in transform exec."""

    def __init__(self, session: SessionStash):
        self._session = session
        self._cache: Dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return self._cache.get(key, default)
            else:
                result = loop.run_until_complete(self._session.get(key))
                return result if result is not None else default
        except Exception:
            return self._cache.get(key, default)

    def put(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        self._cache[key] = value
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._session.put(key, value, ttl_seconds))
            else:
                loop.run_until_complete(self._session.put(key, value, ttl_seconds))
        except Exception:
            pass

    def has(self, key: str) -> bool:
        return key in self._cache or self.get(key) is not None

    def delete(self, key: str) -> bool:
        if key in self._cache:
            del self._cache[key]
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._session.delete(key))
                return True
            else:
                return loop.run_until_complete(self._session.delete(key))
        except Exception:
            return False


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
