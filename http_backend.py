"""HTTP backend connector for mcproxy.

Allows mcproxy to connect to pre-existing MCP servers via HTTP/SSE
instead of spawning as child processes. This enables:
- Independent server lifecycle management via systemd
- Eliminates sandbox IPC issues
- Simpler architecture where servers run as standalone services
"""

import asyncio
import json
from typing import Any, Dict, List, Optional

import requests

from logging_config import get_logger

logger = get_logger(__name__)

LONG_RUNNING_TOOL_TIMEOUT_SECS = 350


class HTTPServerConnector:
    """Manages an MCP server connection via HTTP/SSE."""

    def __init__(
        self,
        name: str,
        url: str,
        timeout: int = 60,
        tool_timeout: Optional[int] = None,
        tool_timeouts: Optional[Dict[str, int]] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        """Initialize HTTP server connector.

        Args:
            name: Server identifier
            url: HTTP endpoint (e.g., http://localhost:12011/mcp)
            timeout: Connection timeout in seconds
            tool_timeout: Default tool call timeout
            tool_timeouts: Per-tool timeout overrides
            headers: Additional HTTP headers
        """
        self.name = name
        self.url = url.rstrip("/")
        self.timeout = timeout
        self.tool_timeout = tool_timeout or LONG_RUNNING_TOOL_TIMEOUT_SECS
        self.tool_timeouts = tool_timeouts or {}
        self.headers = headers or {
            "Accept": "text/event-stream, application/json",
            "Content-Type": "application/json",
        }
        self.session: Optional[requests.Session] = None
        self.session_id: Optional[str] = None
        self.tools: List[Dict[str, Any]] = []
        self._initialized = False

    async def start(self) -> bool:
        """Connect to the HTTP server and discover tools.

        Returns:
            True if connected successfully, False otherwise
        """
        try:
            logger.info(f"Connecting to HTTP server '{self.name}': {self.url}")

            self.session = requests.Session()
            self.session.headers.update(self.headers)

            init_response = self._send_request(
                method="initialize",
                params={
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "mcproxy", "version": "4.2.0"},
                },
                id="init",
            )

            if init_response is None or "error" in init_response:
                logger.error(
                    f"Server '{self.name}' initialization failed: {init_response}"
                )
                return False

            logger.info(f"Initialized HTTP server '{self.name}'")

            self._initialized = True

            await self._discover_tools()
            logger.info(f"HTTP server '{self.name}' connected with {len(self.tools)} tools")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to HTTP server '{self.name}': {e}")
            return False

    async def stop(self) -> None:
        """Disconnect from the HTTP server."""
        logger.info(f"Disconnecting from HTTP server '{self.name}'")
        if self.session:
            self.session.close()
        self.session = None
        self._initialized = False

    def is_running(self) -> bool:
        """Check if connected to the server."""
        return self._initialized and self.session is not None

    async def restart_if_needed(self) -> bool:
        """Reconnect if connection is lost."""
        if self.is_running():
            return True

        logger.warning(f"HTTP server '{self.name}' disconnected, reconnecting")
        return await self.start()

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool on this server."""
        if not self.is_running():
            raise RuntimeError(f"HTTP server '{self.name}' is not connected")

        timeout_seconds = self.tool_timeouts.get(
            tool_name, self.tool_timeout
        )

        logger.info(f"[CALL_TOOL_START] server={self.name} tool={tool_name}")

        response = self._send_request(
            method="tools/call",
            params={"name": tool_name, "arguments": arguments},
            id=f"call_{tool_name}",
            timeout=timeout_seconds,
        )

        if response is None:
            raise RuntimeError(f"No response from HTTP server '{self.name}'")

        if "error" in response:
            error_details = response.get("error", {})
            error_msg = str(error_details)
            logger.error(f"[CALL_TOOL_REMOTE_ERROR] tool={tool_name} error={error_details}")
            raise RuntimeError(f"Tool call failed: {error_msg}")

        logger.info(f"[CALL_TOOL_SUCCESS] tool={tool_name}")
        return response.get("result", {})

    async def _discover_tools(self) -> None:
        """Discover available tools from the server."""
        response = self._send_request(method="tools/list", id="list_tools")

        if response and "result" in response and "tools" in response["result"]:
            self.tools = response["result"]["tools"]
            logger.debug(f"Discovered {len(self.tools)} tools from '{self.name}'")
        else:
            logger.warning(f"Failed to discover tools from '{self.name}': {response}")
            self.tools = []

    def _send_request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        id: str = "1",
        timeout: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Send a JSON-RPC request via HTTP/SSE."""
        if self.session is None:
            return None

        payload = {"jsonrpc": "2.0", "id": id, "method": method}
        if params:
            payload["params"] = params

        try:
            response = self.session.post(
                self.url,
                json=payload,
                stream=True,
                timeout=timeout or self.timeout,
            )
            response.raise_for_status()

            buffer = ""
            for line in response.iter_lines():
                if not line:
                    continue

                line_str = line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue

                if line_str.startswith("data:"):
                    data_str = line_str[5:].strip()
                    try:
                        result = json.loads(data_str)
                        if "result" in result:
                            return result
                        if "error" in result:
                            return result
                    except json.JSONDecodeError:
                        continue

            logger.warning(f"No valid JSON-RPC response from '{self.name}'")
            return None

        except requests.exceptions.Timeout:
            logger.error(f"Request to '{self.name}' timed out")
            raise RuntimeError(f"Request timed out: {method}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request to '{self.name}' failed: {e}")
            raise RuntimeError(f"Request failed: {e}")
