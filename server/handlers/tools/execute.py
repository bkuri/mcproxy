"""Meta-tool execute and trace handlers."""

import json
from typing import Any, Callable, Dict, List, Optional

from logging_config import get_logger

logger = get_logger(__name__)


async def handle_execute(
    msg_id: Any,
    params: Dict,
    connection_namespace: Optional[str] = None,
    session_id: Optional[str] = None,
    sandbox_executor: Optional[Any] = None,
    session_manager: Optional[Any] = None,
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
    retries = params.get("retries", 0)

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

        session = None
        if session_manager is not None:
            session = await session_manager.get_or_create(session_id)

        result = await sandbox_executor.execute(
            code,
            namespace=effective_namespace,
            timeout_secs=timeout_secs,
            session=session,
            retries=retries,
        )

        tool_time_ms = result.get("tool_time_ms", 0)
        execution_time_ms = result.get("execution_time_ms", 0)
        overhead_ms = execution_time_ms - tool_time_ms
        result["overhead_ms"] = overhead_ms

        if tool_time_ms > 5000:
            logger.warning(
                f"[SLOW_TOOL]{log_ns}{log_sess} tool_time={tool_time_ms}ms "
                f"overhead={overhead_ms}ms - slowness is from upstream MCP server, not mcproxy"
            )

        content = [{"type": "text", "text": json.dumps(result)}]
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"content": content}}

    except Exception as e:
        logger.error(f"[EXECUTE_ERROR] {e}")
        error_msg = str(e)
        # Detect common agent mistakes and provide corrective guidance
        if "_ToolProxy.__call__()" in error_msg and "positional argument" in error_msg:
            error_msg = (
                f"Tool call syntax error: {e}. "
                "Tool calls require KEYWORD arguments only. "
                "CORRECT: api.server('name').tool_name(param1='val1', param2='val2') "
                "INCORRECT: api.server('name').tool_name({'param1': 'val1'}) "
                "If you have a dict, unpack it: api.server('name').tool_name(**my_dict)"
            )
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32000, "message": f"Execution failed: {error_msg}"},
        }


async def handle_trace(
    msg_id: Any,
    params: Dict,
    connection_namespace: Optional[str] = None,
    session_id: Optional[str] = None,
    sandbox_executor: Optional[Any] = None,
    session_manager: Optional[Any] = None,
    tool_executor: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Handle trace action - execute code with full call stack tracing.

    Args:
        msg_id: JSON-RPC message ID
        params: Execution parameters (code, namespace, timeout_secs)
        connection_namespace: Namespace from connection context
        session_id: Optional session ID
        sandbox_executor: Sandbox executor instance
        session_manager: Session manager instance
        tool_executor: Callable to execute tools

    Returns:
        MCP response with execution result and trace data
    """
    import time
    from typing import Dict as TDict, Any as TAny

    trace_events: List[TDict[str, TAny]] = []

    def add_event(
        step: str,
        data: Optional[TDict[str, TAny]] = None,
        duration_ms: Optional[int] = None,
    ):
        event = {
            "timestamp": time.time(),
            "step": step,
        }
        if data:
            event["data"] = data
        if duration_ms is not None:
            event["duration_ms"] = duration_ms
        trace_events.append(event)

    start_time = time.perf_counter()
    add_event("trace_start", {"action": "trace"})

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
    retries = params.get("retries", 0)

    add_event(
        "params_parsed",
        {
            "namespace": effective_namespace,
            "timeout_secs": timeout_secs,
            "retries": retries,
            "code_length": len(code),
        },
    )

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
                    "message": "Missing required parameter: namespace",
                },
            }

        validate_start = time.perf_counter()
        is_valid, error = sandbox_executor.validate_code(code)
        validate_ms = int((time.perf_counter() - validate_start) * 1000)
        add_event(
            "code_validated",
            {
                "valid": is_valid,
                "error": error if error else None,
            },
            duration_ms=validate_ms,
        )

        if not is_valid:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32602, "message": f"Validation error: {error}"},
            }

        session = None
        if session_manager is not None:
            session = await session_manager.get_or_create(session_id)
            add_event("session_created", {"session_id": session_id})

        exec_start = time.perf_counter()
        result = await sandbox_executor.execute(
            code,
            namespace=effective_namespace,
            timeout_secs=timeout_secs,
            session=session,
            retries=retries,
            trace=True,  # Enable tracing
        )
        exec_ms = int((time.perf_counter() - exec_start) * 1000)
        add_event(
            "sandbox_execution_complete",
            {
                "status": result.get("status"),
                "has_result": result.get("result") is not None,
                "has_traceback": result.get("traceback") is not None,
            },
            duration_ms=exec_ms,
        )

        total_ms = int((time.perf_counter() - start_time) * 1000)
        add_event(
            "trace_complete",
            {
                "total_duration_ms": total_ms,
                "event_count": len(trace_events),
            },
        )

        trace_result = {
            "execution_result": result,
            "trace": {
                "events": trace_events,
                "summary": {
                    "total_ms": total_ms,
                    "validation_ms": validate_ms,
                    "execution_ms": exec_ms,
                    "overhead_ms": total_ms - exec_ms,
                },
            },
        }

        content = [{"type": "text", "text": json.dumps(trace_result)}]
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"content": content}}

    except Exception as e:
        logger.error(f"[TRACE_ERROR] {e}")
        add_event("error", {"error": str(e)})
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32000, "message": f"Trace failed: {e}"},
        }
