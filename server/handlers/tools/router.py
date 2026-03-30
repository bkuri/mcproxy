"""Meta-tool router - handles tools/call and routes to appropriate handler."""

from typing import Any, Callable, Dict, Optional

from logging_config import get_logger
from manifest import CapabilityRegistry

from .execute import handle_execute, handle_trace
from .help import handle_help
from .inspect import handle_inspect
from .search import handle_search

logger = get_logger(__name__)


async def handle_tools_call(
    msg_id: Any,
    params: Dict[str, Any],
    namespace: Optional[str] = None,
    session_id: Optional[str] = None,
    capability_registry: Optional[CapabilityRegistry] = None,
    sandbox_executor: Optional[Any] = None,
    session_manager: Optional[Any] = None,
    tool_executor: Optional[Callable] = None,
    mcproxy_config: Optional[Dict[str, Any]] = None,
    mcp_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Handle tools/call request - route to appropriate action handler.

    Args:
        msg_id: JSON-RPC message ID
        params: Tool call parameters
        namespace: Optional namespace context from X-Namespace header
        session_id: Optional session ID from X-Session-ID header
        capability_registry: Capability registry instance
        sandbox_executor: Sandbox executor instance
        session_manager: Session manager instance
        tool_executor: Callable to execute tools
        mcproxy_config: mcproxy.json configuration
        mcp_config: MCP client configuration

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
        # Support prefixed names (mcproxy_mcproxy, mcproxy)
        canonical_name = tool_name.replace("mcproxy_", "")

        if canonical_name != "mcproxy":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32601,
                    "message": f"Unknown tool: {tool_name}. v3.1.0 only supports 'mcproxy' tool.",
                },
            }

        action = arguments.get("action")
        if not action:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32602,
                    "message": "Missing required parameter: action",
                },
            }

        if action == "execute":
            return await handle_execute(
                msg_id,
                arguments,
                connection_namespace=namespace,
                session_id=session_id,
                sandbox_executor=sandbox_executor,
                session_manager=session_manager,
                tool_executor=tool_executor,
            )

        elif action == "search":
            # Get config for search (merge mcproxy.json + MCP client config)
            merged_config = {**(mcp_config or {}), **(mcproxy_config or {})}
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

        elif action == "inspect":
            return await handle_inspect(
                msg_id,
                arguments,
                connection_namespace=namespace,
                capability_registry=capability_registry,
            )

        elif action == "help":
            return handle_help(msg_id, arguments)

        elif action == "trace":
            return await handle_trace(
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
                    "code": -32602,
                    "message": f"Unknown action: {action}. Supported actions: execute, search, inspect, help, trace",
                },
            }
    except Exception as e:
        logger.error(f"[META_TOOL_ERROR] {tool_name}: {e}")
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32000, "message": f"Tool execution failed: {e}"},
        }
