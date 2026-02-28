"""Server manager for spawning and managing stdio MCP processes.

Handles process lifecycle, tool discovery, and routing tool calls.
Includes automatic restart for crashed servers.
"""

import asyncio
import json
from typing import Any, Callable, Dict, List, Optional

from logging_config import get_logger

logger = get_logger(__name__)


class ServerProcess:
    """Manages a single MCP server process."""

    def __init__(
        self,
        name: str,
        command: str,
        args: List[str],
        env: Dict[str, str],
        timeout: int = 60,
    ):
        """Initialize server process configuration.

        Args:
            name: Server identifier
            command: Executable to run
            args: Command arguments
            env: Environment variables
            timeout: Startup timeout in seconds (default: 60 for npx)
        """
        self.name = name
        self.command = command
        self.args = args
        self.env = env
        self.timeout = timeout
        self.process: Optional[asyncio.subprocess.Process] = None
        self.tools: List[Dict[str, Any]] = []
        self._lock = asyncio.Lock()
        self._config = None  # Store config for restart
        self._restart_count = 0
        self._max_restarts = 3

    def set_config(
        self, command: str, args: List[str], env: Dict[str, str], timeout: int
    ) -> None:
        """Store configuration for potential restart."""
        self._config = {
            "command": command,
            "args": args,
            "env": env,
            "timeout": timeout,
        }

    async def start(self) -> bool:
        """Start the server process and discover tools.

        Returns:
            True if started successfully, False otherwise
        """
        try:
            logger.info(
                f"Starting server '{self.name}': {self.command} {' '.join(self.args)}"
            )

            self.process = await asyncio.create_subprocess_exec(
                self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.env,
            )

            # Use lock for initialization sequence
            async with self._lock:
                # Send initialize request
                init_request = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "mcproxy", "version": "2.0.0"},
                    },
                }

                await self._send_message(init_request)

                # Wait for initialize response with robust reading
                response = await asyncio.wait_for(
                    self._read_message(), timeout=self.timeout
                )

                if response and "result" in response:
                    # Send initialized notification
                    await self._send_message(
                        {"jsonrpc": "2.0", "method": "notifications/initialized"}
                    )

                    # Discover tools will be called outside the lock
                else:
                    logger.error(
                        f"Server '{self.name}' initialization failed: {response}"
                    )
                    await self.stop()
                    return False

            # Discover tools outside the lock since _discover_tools acquires its own lock
            await self._discover_tools()
            logger.info(f"Server '{self.name}' started with {len(self.tools)} tools")
            self._restart_count = 0  # Reset restart counter on successful start
            return True

        except asyncio.TimeoutError:
            logger.error(
                f"Server '{self.name}' startup timed out after {self.timeout}s"
            )
            await self.stop()
            return False
        except Exception as e:
            logger.error(f"Failed to start server '{self.name}': {e}")
            await self.stop()
            return False

    async def stop(self) -> None:
        """Stop the server process gracefully."""
        if self.process is None:
            return

        try:
            logger.info(f"Stopping server '{self.name}'")

            # Try graceful shutdown
            if self.process.returncode is None:
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=5)
                except asyncio.TimeoutError:
                    logger.warning(
                        f"Server '{self.name}' did not terminate gracefully, killing"
                    )
                    self.process.kill()
                    await self.process.wait()
        except Exception as e:
            logger.error(f"Error stopping server '{self.name}': {e}")
        finally:
            self.process = None
            self.tools = []

    def is_running(self) -> bool:
        """Check if the server process is still running."""
        if self.process is None:
            return False
        if self.process.returncode is not None:
            return False
        return True

    async def restart_if_needed(self) -> bool:
        """Restart the server if it has crashed and hasn't exceeded max restarts."""
        if self.is_running():
            return True

        if self._restart_count >= self._max_restarts:
            logger.error(
                f"Server '{self.name}' exceeded max restarts ({self._max_restarts})"
            )
            return False

        self._restart_count += 1
        logger.warning(
            f"Server '{self.name}' crashed, restarting (attempt {self._restart_count}/{self._max_restarts})"
        )

        # Wait a bit before restarting to avoid rapid restart loops
        await asyncio.sleep(2)

        return await self.start()

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Call a tool on this server with automatic restart on crash."""
        logger.info(f"[CALL_TOOL_START] server={self.name} tool={tool_name}")

        if not self.is_running():
            logger.warning(
                f"[CALL_TOOL_RESTART] Server '{self.name}' not running, attempting restart"
            )
            # Try to restart if crashed
            success = await self.restart_if_needed()
            if not success:
                raise RuntimeError(
                    f"Server '{self.name}' is not running and failed to restart"
                )

        if self.process is None or self.process.returncode is not None:
            raise RuntimeError(f"Server '{self.name}' is not running")

        # Serialize access to prevent race conditions on stdin/stdout
        async with self._lock:
            request = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            }

            logger.debug(f"[CALL_TOOL_SEND] Sending request to {self.name}")
            await self._send_message(request)

            # Use longer timeout for long-running tools like backtest (300s)
            # Standard tools complete in <5s, backtests can take 2-5 minutes
            timeout_seconds = 350  # 5+ minutes to allow full async polling
            logger.debug(
                f"[CALL_TOOL_WAIT] Waiting for response from {self.name} (timeout={timeout_seconds}s)"
            )
            try:
                response = await asyncio.wait_for(
                    self._read_message(), timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                logger.error(
                    f"[CALL_TOOL_TIMEOUT] Tool call timed out after {timeout_seconds}s: {tool_name}"
                )
                raise RuntimeError(
                    f"Tool call timed out after {timeout_seconds} seconds: {tool_name}"
                )

            if response is None:
                logger.error(
                    f"[CALL_TOOL_NO_RESPONSE] No response from server '{self.name}'"
                )
                raise RuntimeError(f"No response from server '{self.name}'")

            if "error" in response:
                error_details = response.get("error", {})
                logger.error(
                    f"[CALL_TOOL_REMOTE_ERROR] tool={tool_name} error={error_details}"
                )
                raise RuntimeError(f"Tool call failed: {error_details}")

            logger.info(f"[CALL_TOOL_SUCCESS] tool={tool_name}")
            return response.get("result", {})

    async def _discover_tools(self) -> None:
        """Discover available tools from the server."""
        async with self._lock:
            request = {"jsonrpc": "2.0", "id": 3, "method": "tools/list"}

            await self._send_message(request)
            response = await asyncio.wait_for(self._read_message(), timeout=30)

            if response and "result" in response and "tools" in response["result"]:
                self.tools = response["result"]["tools"]
                logger.debug(f"Discovered {len(self.tools)} tools from '{self.name}'")
            else:
                logger.warning(
                    f"Failed to discover tools from '{self.name}': {response}"
                )
                self.tools = []

    async def _send_message(self, message: Dict[str, Any]) -> None:
        """Send a JSON-RPC message to the server."""
        if self.process is None or self.process.stdin is None:
            raise RuntimeError(f"Server '{self.name}' is not running")

        data = json.dumps(message) + "\n"
        self.process.stdin.write(data.encode())
        await self.process.stdin.drain()

    async def _read_message(self) -> Optional[Dict[str, Any]]:
        """Read a JSON-RPC message from the server with robust error handling.

        Handles:
        - Empty lines (common during npx package downloads)
        - Multi-line JSON responses
        - Server-side error messages
        - Malformed responses gracefully
        """
        if self.process is None or self.process.stdout is None:
            raise RuntimeError(f"Server '{self.name}' is not running")

        buffer = ""
        max_lines = 100  # Prevent infinite loops
        line_count = 0

        try:
            while line_count < max_lines:
                try:
                    line = await asyncio.wait_for(
                        self.process.stdout.readline(),
                        timeout=1.0,  # Short timeout to check for more data
                    )
                except asyncio.TimeoutError:
                    # No more data available
                    if buffer:
                        break
                    continue

                line_count += 1

                if not line:
                    # EOF reached
                    if buffer:
                        break
                    return None

                line_str = line.decode("utf-8", errors="replace").strip()

                # Skip empty lines (common from npx during downloads)
                if not line_str:
                    continue

                # Check for known server-side error patterns
                if "chunk" in line_str.lower() and "limit" in line_str.lower():
                    logger.warning(f"Server '{self.name}' error: {line_str[:200]}")
                    return None

                # Skip non-JSON lines (server logs, npm output, etc.)
                # JSON-RPC messages start with '{' or '['
                if not line_str.startswith(("{", "[")):
                    # Check for npm/npx progress output
                    if line_str.startswith(
                        ("npm ", "npx ", "added", "changed", "removed")
                    ):
                        logger.debug(
                            f"Skipping npm output from '{self.name}': {line_str[:50]}..."
                        )
                    else:
                        logger.debug(
                            f"Skipping non-JSON line from '{self.name}': {line_str[:100]}..."
                        )
                    continue

                # Accumulate buffer
                if buffer:
                    buffer += "\n"
                buffer += line_str

                # Try to parse as JSON
                try:
                    result = json.loads(buffer)
                    logger.debug(
                        f"Successfully parsed JSON from '{self.name}' after {line_count} line(s)"
                    )
                    return result
                except json.JSONDecodeError:
                    # Partial JSON, need more lines
                    continue

            # Max lines reached without valid JSON
            if buffer:
                logger.error(
                    f"Failed to parse JSON from '{self.name}' after {line_count} lines. Buffer: {buffer[:500]}"
                )
            else:
                logger.error(
                    f"No data received from '{self.name}' after {line_count} lines"
                )
            return None

        except Exception as e:
            logger.error(f"Error reading message from '{self.name}': {e}")
            return None


class ServerManager:
    """Manages multiple MCP server processes."""

    def __init__(
        self,
        config: Dict[str, Any],
        on_server_ready: Optional[Callable[[str, int], None]] = None,
    ):
        """Initialize server manager with configuration.

        Args:
            config: Configuration dictionary with 'servers' key
            on_server_ready: Optional callback(server_name, tool_count) when server starts
        """
        self.config = config
        self.servers: Dict[str, ServerProcess] = {}
        self._on_server_ready = on_server_ready

    async def spawn_servers(self) -> None:
        """Start all enabled servers from configuration with staggered startup."""
        servers_config = self.config.get("servers", [])

        logger.info(f"Starting {len(servers_config)} servers with staggered startup...")

        for i, server_config in enumerate(servers_config):
            if not server_config.get("enabled", True):
                logger.info(f"Skipping disabled server '{server_config['name']}'")
                continue

            # Stagger startup: 0.5s delay between servers to avoid resource contention
            if i > 0:
                await asyncio.sleep(0.5)

            server = ServerProcess(
                name=server_config["name"],
                command=server_config["command"],
                args=server_config.get("args", []),
                env=server_config.get("env", {}),
                timeout=server_config.get("timeout", 60),  # Default 60s for npx
            )

            # Store config for potential restart
            server.set_config(
                command=server_config["command"],
                args=server_config.get("args", []),
                env=server_config.get("env", {}),
                timeout=server_config.get("timeout", 60),
            )

            self.servers[server.name] = server

            # Start in background - don't let one failure break others
            asyncio.create_task(self._start_server(server))

    async def _start_server(self, server: ServerProcess) -> None:
        """Start a server and handle failures gracefully."""
        try:
            success = await server.start()
            if success and self._on_server_ready:
                self._on_server_ready(server.name, len(server.tools))
            elif not success:
                logger.error(f"Server '{server.name}' failed to start")
        except Exception as e:
            logger.error(f"Error starting server '{server.name}': {e}")

    async def stop_all(self) -> None:
        """Stop all running servers."""
        logger.info(f"Stopping {len(self.servers)} servers")

        # Stop all servers concurrently
        await asyncio.gather(
            *[server.stop() for server in self.servers.values()], return_exceptions=True
        )

    def get_all_tools(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get tools from all running servers.

        Returns:
            Dict mapping server name to list of tools
        """
        tools: Dict[str, List[Dict[str, Any]]] = {}

        for name, server in self.servers.items():
            if server.process is not None and server.process.returncode is None:
                tools[name] = server.tools

        return tools

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: Dict[str, Any]
    ) -> Any:
        """Route a tool call to the appropriate server with automatic restart."""
        if server_name not in self.servers:
            raise ValueError(f"Unknown server: {server_name}")

        server = self.servers[server_name]

        # Check if server crashed and try to restart
        if not server.is_running():
            success = await server.restart_if_needed()
            if not success:
                raise RuntimeError(
                    f"Server '{server_name}' is not running and failed to restart"
                )

        return await server.call_tool(tool_name, arguments)

    async def update_config(self, new_config: Dict[str, Any]) -> None:
        """Update configuration and restart affected servers.

        Args:
            new_config: New configuration dictionary
        """
        # TODO: Implement hot-reload logic
        # For MVP, just log that config changed
        logger.info(
            "Config update detected - restart required for changes to take effect"
        )
