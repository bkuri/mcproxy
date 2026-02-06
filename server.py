"""FastAPI SSE server for MCProxy.

Exposes MCP protocol over Server-Sent Events (SSE).
"""

import asyncio
import json
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from logging_config import get_logger
from tool_aggregator import aggregate_tools, parse_prefixed_tool_name

logger = get_logger(__name__)

# Global server manager reference (set by main.py)
server_manager: Optional[Any] = None

app = FastAPI(title="MCProxy", version="1.0.0")


@app.get("/sse")
async def sse_endpoint(request: Request) -> StreamingResponse:
    """SSE endpoint for MCP protocol.

    Handles MCP initialization, tool listing, and tool calls over SSE.
    """
    logger.info(f"New SSE connection from {request.client}")

    async def event_stream():
        """Generate SSE events."""
        try:
            # Send endpoint event
            yield f"event: endpoint\ndata: {json.dumps({'uri': '/message'})}\n\n"

            # Keep connection alive with periodic messages
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    logger.info("Client disconnected")
                    break

                # Send heartbeat every 30 seconds
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
    """
    if server_manager is None:
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32000, "message": "Server manager not initialized"},
        }

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
            "serverInfo": {"name": "mcproxy", "version": "1.0.0"},
        },
    }


async def handle_tools_list(msg_id: Any) -> Dict[str, Any]:
    """Handle tools/list request - return aggregated tools."""
    if server_manager is None:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32000, "message": "Server manager not initialized"},
        }

    try:
        servers_tools = server_manager.get_all_tools()
        tools = aggregate_tools(servers_tools)

        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": tools}}
    except Exception as e:
        logger.error(f"Error listing tools: {e}")
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32000, "message": f"Failed to list tools: {e}"},
        }


async def handle_tools_call(msg_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    """Handle tools/call request - route to appropriate server."""
    if server_manager is None:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32000, "message": "Server manager not initialized"},
        }

    try:
        prefixed_name = params.get("name", "")
        arguments = params.get("arguments", {})

        # Parse prefixed name to get server and tool
        server_name, tool_name = parse_prefixed_tool_name(prefixed_name)

        logger.info(f"Calling tool '{prefixed_name}' on server '{server_name}'")

        # Route to server
        result = await server_manager.call_tool(server_name, tool_name, arguments)

        return {"jsonrpc": "2.0", "id": msg_id, "result": result}

    except ValueError as e:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32602, "message": f"Invalid tool name: {e}"},
        }
    except Exception as e:
        logger.error(f"Error calling tool: {e}")
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32000, "message": f"Tool call failed: {e}"},
        }


def set_server_manager(manager: Any) -> None:
    """Set the global server manager reference."""
    global server_manager
    server_manager = manager
