#!/usr/bin/env python3
"""Simple test MCP server for MCProxy validation.

This is a minimal MCP-compliant server for testing the gateway.
"""

import json
import sys
from typing import Any, Dict, List


def send_message(msg: Dict[str, Any]) -> None:
    """Send a JSON-RPC message."""
    print(json.dumps(msg), flush=True)


def handle_initialize(msg_id: Any) -> None:
    """Handle initialize request."""
    send_message(
        {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "test-server", "version": "1.0.0"},
            },
        }
    )


def handle_tools_list(msg_id: Any) -> None:
    """Handle tools/list request."""
    send_message(
        {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "tools": [
                    {
                        "name": "echo",
                        "description": "Echo back the input message",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "message": {
                                    "type": "string",
                                    "description": "Message to echo",
                                }
                            },
                            "required": ["message"],
                        },
                    },
                    {
                        "name": "add",
                        "description": "Add two numbers",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "a": {"type": "number", "description": "First number"},
                                "b": {"type": "number", "description": "Second number"},
                            },
                            "required": ["a", "b"],
                        },
                    },
                ]
            },
        }
    )


def handle_tools_call(msg_id: Any, params: Dict[str, Any]) -> None:
    """Handle tools/call request."""
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    if tool_name == "echo":
        message = arguments.get("message", "")
        send_message(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"content": [{"type": "text", "text": f"Echo: {message}"}]},
            }
        )
    elif tool_name == "add":
        a = arguments.get("a", 0)
        b = arguments.get("b", 0)
        result = a + b
        send_message(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"content": [{"type": "text", "text": f"Result: {result}"}]},
            }
        )
    else:
        send_message(
            {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Tool not found: {tool_name}"},
            }
        )


def main() -> None:
    """Main entry point."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = msg.get("method", "")
        msg_id = msg.get("id")
        params = msg.get("params", {})

        if method == "initialize":
            handle_initialize(msg_id)
        elif method == "notifications/initialized":
            pass  # No response needed
        elif method == "tools/list":
            handle_tools_list(msg_id)
        elif method == "tools/call":
            handle_tools_call(msg_id, params)


if __name__ == "__main__":
    main()
