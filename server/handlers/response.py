"""Response building utilities for MCP handlers."""

import json
from typing import Any, Dict, List, Optional


def build_success_response(msg_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    """Build a successful MCP response.

    Args:
        msg_id: JSON-RPC message ID
        result: The result data

    Returns:
        MCP success response dictionary
    """
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def build_error_response(
    msg_id: Any,
    code: int,
    message: str,
    data: Optional[Any] = None,
) -> Dict[str, Any]:
    """Build an error MCP response.

    Args:
        msg_id: JSON-RPC message ID
        code: JSON-RPC error code
        message: Error message
        data: Optional additional error data

    Returns:
        MCP error response dictionary
    """
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": msg_id, "error": error}


def wrap_content(data: Any, content_type: str = "text") -> List[Dict[str, Any]]:
    """Wrap data in MCP content format.

    Args:
        data: Data to wrap (will be JSON serialized)
        content_type: Content type (default: "text")

    Returns:
        List containing the wrapped content
    """
    text = data if isinstance(data, str) else json.dumps(data)
    return [{"type": content_type, "text": text}]


def build_content_response(
    msg_id: Any, data: Any, content_type: str = "text"
) -> Dict[str, Any]:
    """Build a response with content wrapped in MCP format.

    Args:
        msg_id: JSON-RPC message ID
        data: Data to wrap (will be JSON serialized)
        content_type: Content type (default: "text")

    Returns:
        MCP response with content
    """
    content = wrap_content(data, content_type)
    return build_success_response(msg_id, {"content": content})
