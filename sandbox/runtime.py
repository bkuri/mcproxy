"""Runtime classes for sandbox execution.

These classes are injected into the sandbox subprocess as code strings.
They cannot import from the parent process - all classes must be self-contained.

The classes work with JSON-serialized manifest data (not live objects) and use
_ToolExecutor that collects pending calls instead of executing tools directly.
"""

RUNTIME_CLASSES = """
class _ToolExecutor:
    def __init__(self):
        self._pending = []
    
    def __call__(self, server, tool, args):
        self._pending.append({"server": server, "tool": tool, "args": args})
        return {"_pending_call": True, "server": server, "tool": tool, "args": args}
    
    def get_pending(self):
        return self._pending


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
        
        # Check if it's a group first
        group_config = self.manifest.get_group(namespace_or_group)
        if group_config:
            # It's a group - resolve all namespaces in the group
            for ns_ref in group_config.get("namespaces", []):
                # Strip ! prefix if present (force-include isolated)
                actual_ns = ns_ref[1:] if ns_ref.startswith("!") else ns_ref
                _resolve_namespace(actual_ns)
        else:
            # It's a namespace
            _resolve_namespace(namespace_or_group)
        
        return resolved


class _PendingCall(dict):
    def __init__(self, executor, server, tool, args):
        self._executor = executor
        self._server = server
        self._tool = tool
        self._args = args
        receipt = executor(server, tool, args)
        receipt["_awaited"] = True
        super().__init__(receipt)
    
    def __await__(self):
        async def _noop():
            return dict(self)
        return _noop().__await__()


class _DynamicProxy:
    def __init__(self, server_name, namespace, access_control, tool_executor):
        self._server_name = server_name
        self._namespace = namespace
        self._access_control = access_control
        self._tool_executor = tool_executor
    
    def __getattr__(self, tool_name):
        def _call(**kwargs):
            return _PendingCall(
                self._tool_executor,
                self._server_name,
                tool_name,
                kwargs
            )
        return _call


class _APIProxy:
    def __init__(self, namespace, access_control, tool_executor, manifest):
        self._namespace = namespace
        self._access_control = access_control
        self._tool_executor = tool_executor
        self._manifest = manifest
    
    def server(self, name):
        can_access, error = self._access_control.can_access(self._namespace, name)
        if not can_access:
            raise PermissionError(error)
        return _DynamicProxy(name, self._namespace, self._access_control, self._tool_executor)
    
    def call_tool(self, server, tool, args):
        can_access, error = self._access_control.can_access(self._namespace, server)
        if not can_access:
            raise PermissionError(error)
        return _PendingCall(self._tool_executor, server, tool, args)
    
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


class _ParallelResult:
    def __init__(self, status, result=None, error=None):
        self.status = status
        self.result = result
        self.error = error
    
    def to_dict(self):
        return {"status": self.status, "result": self.result, "error": self.error}


class _ForgeProxy:
    def __init__(self, max_concurrency=5):
        self._max_concurrency = max_concurrency
    
    async def parallel(self, callables, max_concurrency=None):
        import asyncio
        limit = max_concurrency if max_concurrency is not None else self._max_concurrency
        semaphore = asyncio.Semaphore(limit)
        
        async def run_with_limit(coro_func):
            async with semaphore:
                try:
                    result = await coro_func()
                    return _ParallelResult(status="fulfilled", result=result)
                except Exception as e:
                    return _ParallelResult(status="rejected", error=f"{type(e).__name__}: {str(e)}")
        
        tasks = [run_with_limit(c) for c in callables]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        final = []
        for r in results:
            if isinstance(r, _ParallelResult):
                final.append(r)
            elif isinstance(r, Exception):
                final.append(_ParallelResult(status="rejected", error=f"{type(r).__name__}: {str(r)}"))
            else:
                final.append(_ParallelResult(status="fulfilled", result=r))
        
        return [f.to_dict() for f in final]
"""
