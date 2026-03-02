"""Proxy classes for sandbox API access."""

from typing import Any, Dict

from sandbox.access_control import NamespaceAccessControl


class ProxyAPI:
    """API injected into sandbox for accessing MCP servers.

    Usage in sandbox code:
        api.server("playwright").navigate("https://example.com")
        api.call_tool("playwright", "navigate", {"url": "..."})
        manifest = api.manifest()
    """

    def __init__(
        self,
        namespace: str,
        access_control: NamespaceAccessControl,
        tool_executor: Any,
    ):
        """Initialize ProxyAPI.

        Args:
            namespace: The namespace context for access control
            access_control: Access control checker
            tool_executor: Callable to execute tools (async)
        """
        self._namespace = namespace
        self._access_control = access_control
        self._tool_executor = tool_executor
        self._manifest = access_control.manifest

    def server(self, name: str) -> "DynamicProxy":
        """Get a typed proxy to a server.

        Args:
            name: Server name

        Returns:
            DynamicProxy that forwards calls as tool invocations

        Raises:
            PermissionError: If namespace cannot access server
        """
        can_access, error = self._access_control.can_access(self._namespace, name)
        if not can_access:
            raise PermissionError(error)

        return DynamicProxy(
            server_name=name,
            namespace=self._namespace,
            access_control=self._access_control,
            tool_executor=self._tool_executor,
        )

    def call_tool(self, server: str, tool: str, args: dict) -> Any:
        """Directly call a tool on a server.

        Args:
            server: Server name
            tool: Tool name
            args: Tool arguments

        Returns:
            Tool result

        Raises:
            PermissionError: If namespace cannot access server
        """
        can_access, error = self._access_control.can_access(self._namespace, server)
        if not can_access:
            raise PermissionError(error)

        return self._tool_executor(server, tool, args)

    def manifest(self) -> Dict[str, Any]:
        """Get the current capability manifest.

        Returns:
            Dict with servers and namespace permissions (sanitized)
        """
        allowed_servers = self._access_control._resolve_allowed_servers(self._namespace)

        return {
            "namespace": self._namespace,
            "allowed_servers": sorted(allowed_servers),
            "servers": {
                name: self._manifest.get_server(name)
                for name in allowed_servers
                if self._manifest.get_server(name)
            },
        }


class DynamicProxy:
    """Dynamic proxy that converts attribute access to tool calls."""

    def __init__(
        self,
        server_name: str,
        namespace: str,
        access_control: NamespaceAccessControl,
        tool_executor: Any,
    ):
        self._server_name = server_name
        self._namespace = namespace
        self._access_control = access_control
        self._tool_executor = tool_executor

    def __getattr__(self, tool_name: str) -> Any:
        """Convert attribute access to a callable tool invocation."""

        def _call(**kwargs: Any) -> Any:
            return self._tool_executor(self._server_name, tool_name, kwargs)

        return _call

    def __repr__(self) -> str:
        return f"<DynamicProxy server='{self._server_name}'>"
