"""Runtime classes for sandbox execution.

These classes are injected into the sandbox subprocess as code strings.
They cannot import from the parent process - all classes must be self-contained.

The classes work with JSON-serialized manifest data (not live objects) and use
_IPCClient for synchronous tool execution via Unix Domain Socket IPC.

Sync-Only Execution:
- All tool calls execute immediately via Unix Domain Socket IPC
- Results are available inline during code execution
- Parent process executes tools and returns results to subprocess

Tool Inspection:
- Use .inspect() to get tool schema and metadata
- Example: schema = api.server("name").tool.inspect()
- Returns: server, name, description, inputSchema
"""

RUNTIME_CLASSES = """
import json
import os
import socket


class _IPCClient:
    def __init__(self):
        self._sock_path = os.environ.get("MCPROXY_IPC_SOCK")
        self._call_id = 0

    def call(self, server, tool, args):
        if not self._sock_path:
            raise RuntimeError(
                "IPC socket not available. MCPROXY_IPC_SOCK environment variable not set."
            )

        self._call_id += 1
        request = {
            "call_id": self._call_id,
            "server": server,
            "tool": tool,
            "args": args,
        }

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            sock.connect(self._sock_path)
            sock.sendall(json.dumps(request).encode("utf-8"))
            sock.shutdown(socket.SHUT_WR)

            response_data = b""
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                response_data += chunk

            response = json.loads(response_data.decode("utf-8"))

            if response.get("status") == "error":
                raise RuntimeError(response.get("error", "Unknown IPC error"))

            return response.get("result")
        finally:
            sock.close()


class _Manifest:
    def __init__(self, data):
        self._data = data

    @property
    def servers(self):
        return self._data.get("servers", {})

    @property
    def namespaces(self):
        return self._data.get("namespaces", {})

    @property
    def groups(self):
        return self._data.get("groups", {})


class _CapabilityRegistry:
    def __init__(self, manifest):
        self.servers = manifest.servers
        self.namespaces = manifest.namespaces
        self.groups = manifest.groups

    def get_server(self, name):
        return self.servers.get(name)

    def get_namespace(self, name):
        return self.namespaces.get(name)

    def get_group(self, name):
        return self.groups.get(name)

    def get_tools_for_server(self, server_name):
        server = self.get_server(server_name)
        if not server:
            return []
        return server.get("tools", [])


class _NamespaceAccessControl:
    def __init__(self, manifest):
        self.manifest = manifest

    def can_access(self, namespace, target_server):
        allowed = self._resolve_allowed_servers(namespace)
        if target_server in allowed:
            return True, ""
        return False, f"Access denied to '{target_server}'"

    def _resolve_allowed_servers(self, namespace_or_group):
        resolved = set()
        visited = set()

        def _resolve_namespace(ns):
            if ns in visited:
                return
            visited.add(ns)
            ns_config = self.manifest.get_namespace(ns)
            if not ns_config:
                return
            resolved.update(ns_config.get("servers", []))
            for parent in ns_config.get("extends", []):
                _resolve_namespace(parent)

        group_config = self.manifest.get_group(namespace_or_group)
        if group_config:
            for ns_ref in group_config.get("namespaces", []):
                actual_ns = ns_ref[1:] if ns_ref.startswith("!") else ns_ref
                _resolve_namespace(actual_ns)
        else:
            _resolve_namespace(namespace_or_group)

        return resolved


class _ToolProxy:
    '''Proxy for a single tool, providing both call and inspect capabilities.'''
    
    def __init__(self, server_name, tool_name, ipc_client, manifest):
        self._server_name = server_name
        self._tool_name = tool_name
        self._ipc_client = ipc_client
        self._manifest = manifest
    
    def __call__(self, **kwargs):
        '''Execute the tool with given arguments.'''
        return self._ipc_client.call(self._server_name, self._tool_name, kwargs)
    
    def inspect(self):
        '''Get tool schema and metadata without executing.
        
        Returns:
            Dict with tool information including:
            - server: Server name
            - name: Tool name
            - description: Tool description
            - inputSchema: JSON Schema for tool parameters
        '''
        server_info = self._manifest.servers.get(self._server_name, {})
        tools = server_info.get("tools", [])
        
        for tool in tools:
            if tool.get("name") == self._tool_name:
                return {
                    "server": self._server_name,
                    "name": self._tool_name,
                    "description": tool.get("description", ""),
                    "inputSchema": tool.get("inputSchema", {})
                }
        
        return {
            "server": self._server_name,
            "name": self._tool_name,
            "error": f"Tool '{self._tool_name}' not found in server '{self._server_name}'",
            "available_tools": [t.get("name") for t in tools]
        }


class _DynamicProxy:
    def __init__(self, server_name, namespace, access_control, ipc_client, manifest):
        self._server_name = server_name
        self._namespace = namespace
        self._access_control = access_control
        self._ipc_client = ipc_client
        self._manifest = manifest

    def __getattr__(self, tool_name):
        return _ToolProxy(self._server_name, tool_name, self._ipc_client, self._manifest)


class _APIProxy:
    def __init__(self, namespace, access_control, ipc_client, manifest):
        self._namespace = namespace
        self._access_control = access_control
        self._ipc_client = ipc_client
        self._manifest = manifest

    def server(self, name):
        can_access, error = self._access_control.can_access(self._namespace, name)
        if not can_access:
            raise PermissionError(error)
        return _DynamicProxy(name, self._namespace, self._access_control, self._ipc_client, self._manifest)

    def call_tool(self, server, tool, args):
        can_access, error = self._access_control.can_access(self._namespace, server)
        if not can_access:
            raise PermissionError(error)
        return self._ipc_client.call(server, tool, args)

    def manifest(self):
        allowed = self._access_control._resolve_allowed_servers(self._namespace)
        return {
            "namespace": self._namespace,
            "allowed_servers": sorted(allowed),
            "servers": {n: _registry.get_server(n) for n in allowed if _registry.get_server(n)},
        }


class _StashProxy:
    def __init__(self, initial_data=None):
        self._data = initial_data or {}
        self._updates = []

    def get(self, key, default=None):
        return self._data.get(key, default)

    def put(self, key, value, ttl_seconds=None):
        self._data[key] = value
        self._updates.append({"op": "put", "key": key, "value": value, "ttl_seconds": ttl_seconds})
        return value

    def has(self, key):
        return key in self._data

    def delete(self, key):
        if key in self._data:
            del self._data[key]
            self._updates.append({"op": "delete", "key": key})
            return True
        return False

    def clear(self):
        self._data.clear()
        self._updates.append({"op": "clear"})

    def keys(self):
        return list(self._data.keys())

    def _get_updates(self):
        return self._updates


def parallel(callables):
    '''Execute multiple tool calls concurrently (synchronous).
    
    Args:
        callables: List of callable functions returning tool results
    
    Returns:
        List of results in same order as input callables
    
    Note:
        max_concurrency is configured in mcproxy.json, not adjustable per-call
    
    Example:
        results = parallel([
            lambda: api.server('s1').tool1(),
            lambda: api.server('s2').tool2(),
        ])
    '''
    import asyncio

    # max_concurrency is injected by executor from mcproxy.json config
    _max_concurrency = _PARALLEL_MAX_CONCURRENCY

    async def _run_async():
        semaphore = asyncio.Semaphore(_max_concurrency)

        async def run_with_limit(coro_func):
            async with semaphore:
                try:
                    result = coro_func()
                    if asyncio.iscoroutine(result):
                        result = await result
                    return {"status": "fulfilled", "result": result}
                except Exception as e:
                    return {"status": "rejected", "error": f"{type(e).__name__}: {str(e)}"}

        tasks = [run_with_limit(c) for c in callables]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        final = []
        for r in results:
            if isinstance(r, dict):
                final.append(r)
            elif isinstance(r, Exception):
                final.append({"status": "rejected", "error": f"{type(r).__name__}: {str(r)}"})
            else:
                final.append({"status": "fulfilled", "result": r})

        return final

    return asyncio.run(_run_async())
"""
