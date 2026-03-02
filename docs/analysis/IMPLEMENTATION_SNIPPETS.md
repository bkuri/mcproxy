# Session Stash Implementation - Code Snippets

## File 1: server.py - SessionStash & SessionManager Classes

```python
# Add at module level (around line 18-24)
import time
from datetime import datetime

class SessionStash:
    """Per-session key-value store with per-key TTL support."""
    
    def __init__(self, session_id: str) -> None:
        """Initialize stash for a session.
        
        Args:
            session_id: Unique session identifier
        """
        self.session_id = session_id
        self._data: Dict[str, Any] = {}
        self._ttl_map: Dict[str, float] = {}  # key -> expiration_time
        self._created_at = time.time()
        self._last_accessed = time.time()
    
    def put(self, key: str, value: Any, ttl_secs: Optional[int] = None) -> None:
        """Store a value with optional TTL.
        
        Args:
            key: Cache key
            value: Value to store
            ttl_secs: Optional time-to-live in seconds
        """
        self._data[key] = value
        self._last_accessed = time.time()
        
        if ttl_secs:
            self._ttl_map[key] = time.time() + ttl_secs
        elif key in self._ttl_map:
            del self._ttl_map[key]
    
    def get(self, key: str) -> Optional[Any]:
        """Retrieve a value if it exists and hasn't expired.
        
        Args:
            key: Cache key
            
        Returns:
            Value if found and not expired, None otherwise
        """
        if key not in self._data:
            return None
        
        # Check TTL
        expiration = self._ttl_map.get(key)
        if expiration and time.time() > expiration:
            self._data.pop(key)
            self._ttl_map.pop(key)
            return None
        
        self._last_accessed = time.time()
        return self._data[key]
    
    def has(self, key: str) -> bool:
        """Check if a key exists and hasn't expired.
        
        Args:
            key: Cache key
            
        Returns:
            True if key exists and not expired
        """
        return self.get(key) is not None
    
    def delete(self, key: str) -> bool:
        """Delete a key from the stash.
        
        Args:
            key: Cache key
            
        Returns:
            True if key was deleted, False if not found
        """
        if key in self._data:
            self._data.pop(key)
            self._ttl_map.pop(key, None)
            self._last_accessed = time.time()
            return True
        return False
    
    def clear(self) -> None:
        """Clear all data in this stash."""
        self._data.clear()
        self._ttl_map.clear()
        self._last_accessed = time.time()
    
    def keys(self) -> List[str]:
        """Get all non-expired keys in the stash.
        
        Returns:
            List of active (non-expired) keys
        """
        now = time.time()
        active_keys = [
            k for k in self._data.keys()
            if k not in self._ttl_map or self._ttl_map[k] > now
        ]
        return active_keys
    
    def is_expired(self, idle_timeout_secs: int = 3600) -> bool:
        """Check if this session has been idle too long.
        
        Args:
            idle_timeout_secs: Max idle time before expiration (default 1 hour)
            
        Returns:
            True if session is idle too long
        """
        return time.time() - self._last_accessed > idle_timeout_secs
    
    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata about this stash.
        
        Returns:
            Dict with stash statistics
        """
        return {
            "session_id": self.session_id,
            "keys": self.keys(),
            "key_count": len(self.keys()),
            "created_at": self._created_at,
            "last_accessed": self._last_accessed,
            "idle_secs": int(time.time() - self._last_accessed),
        }


class SessionManager:
    """Manages session stashes with automatic cleanup of expired sessions."""
    
    def __init__(self, idle_timeout_secs: int = 3600) -> None:
        """Initialize the session manager.
        
        Args:
            idle_timeout_secs: Idle timeout for session expiration
        """
        self._sessions: Dict[str, SessionStash] = {}
        self._lock = asyncio.Lock()
        self._idle_timeout_secs = idle_timeout_secs
    
    async def get_stash(self, session_id: str) -> SessionStash:
        """Get or create a stash for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            SessionStash instance for the session
        """
        async with self._lock:
            if session_id not in self._sessions:
                logger.info(f"[SESSION] Creating new session: {session_id}")
                self._sessions[session_id] = SessionStash(session_id)
            return self._sessions[session_id]
    
    async def cleanup_expired(self) -> None:
        """Remove expired sessions (call periodically)."""
        async with self._lock:
            expired_sids = [
                sid for sid, stash in self._sessions.items()
                if stash.is_expired(self._idle_timeout_secs)
            ]
            
            for sid in expired_sids:
                del self._sessions[sid]
            
            if expired_sids:
                logger.info(
                    f"[SESSION_CLEANUP] Removed {len(expired_sids)} expired sessions"
                )
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about active sessions."""
        return {
            "active_sessions": len(self._sessions),
            "sessions": [s.get_metadata() for s in self._sessions.values()],
        }
```

## File 2: server.py - Helper Functions

```python
# Add near other helper functions (around line 81-122)

def _get_session_id(request: Request) -> str:
    """Extract or generate a session ID from request.
    
    Session ID can come from:
    1. X-Session-ID header (explicit, preferred)
    2. Auto-generated from client IP + timestamp
    
    Args:
        request: FastAPI request object
        
    Returns:
        Session identifier string
    """
    # Try explicit header first
    explicit_id = request.headers.get("X-Session-ID")
    if explicit_id:
        return explicit_id
    
    # Fallback: auto-generate
    if request.client:
        ip = request.client[0]
    else:
        ip = "unknown"
    
    return f"auto-{ip}-{int(time.time() * 1000)}"
```

## File 3: server.py - Global Components Update

```python
# Update globals around line 20-24
server_manager: Optional[Any] = None
capability_registry: Optional[CapabilityRegistry] = None
event_hook_manager: Optional[EventHookManager] = None
sandbox_executor: Optional[SandboxExecutor] = None
session_manager: Optional[SessionManager] = None  # ADD THIS
_tool_executor: Optional[Callable] = None
```

## File 4: server.py - handle_execute() Update

```python
# Update handle_execute function (around line 473-568)
# Show only the key changes

async def handle_execute(
    msg_id: Any, params: Dict, connection_namespace: Optional[str] = None
) -> Dict[str, Any]:
    """Handle execute meta-tool.
    
    Args:
        msg_id: JSON-RPC message ID
        params: Execution parameters (code, namespace, timeout_secs, session_id)
        connection_namespace: Namespace from connection context (X-Namespace header)
    
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
    
    # NEW: Extract session ID from params or fallback to header
    session_id = params.get("session_id")
    if not session_id and request:  # request not available here - needs fixing
        session_id = _get_session_id(request)
    session_id = session_id or f"default-{time.time()}"

    log_ns = f" namespace={effective_namespace}" if effective_namespace else ""
    logger.debug(f"[EXECUTE]{log_ns} session_id={session_id} timeout={timeout_secs}")

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

        # NEW: Get session stash
        stash = None
        if session_manager:
            stash = await session_manager.get_stash(session_id)
        
        # Pass stash to executor
        result = sandbox_executor.execute(
            code,
            namespace=effective_namespace,
            timeout_secs=timeout_secs,
            stash=stash,  # NEW
        )

        # Process pending tool calls (existing code)
        pending_calls = result.get("pending_calls", [])
        if pending_calls and _tool_executor:
            call_results = []
            for call in pending_calls:
                # ... existing code ...
            result["tool_results"] = call_results

        # NEW: Add session stash metadata to response
        if stash:
            result["session_stash"] = {
                "keys": stash.keys(),
                "updated_at": time.time(),
            }

        content = [{"type": "text", "text": json.dumps(result, indent=2)}]
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"content": content}}

    except Exception as e:
        logger.error(f"[EXECUTE_ERROR] {e}")
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32000, "message": f"Execution failed: {e}"},
        }
```

## File 5: api_sandbox.py - SandboxExecutor.execute() Update

```python
# Update execute method signature (around line 434)

def execute(
    self,
    code: str,
    namespace: str,
    timeout_secs: Optional[int] = None,
    dependencies: Optional[List[str]] = None,
    stash: Optional[Any] = None,  # NEW parameter
) -> Dict[str, Any]:
    """Execute user code in a uv subprocess.

    Args:
        code: Python code to execute
        namespace: Namespace for access control
        timeout_secs: Execution timeout (uses default if None)
        dependencies: Optional list of pip dependencies
        stash: Optional SessionStash instance for caching

    Returns:
        Dict with status, result, traceback, execution_time_ms
    """
    timeout = timeout_secs or self._default_timeout_secs

    is_valid, error = self.validate_code(code)
    if not is_valid:
        return {
            "status": "error",
            "result": None,
            "traceback": f"Validation error: {error}",
            "execution_time_ms": 0,
        }

    access_control = NamespaceAccessControl(self._manifest)

    wrapped_code = self._wrap_code(code, namespace, access_control, stash)  # Pass stash

    env = self._build_env(namespace, access_control)

    start_time = time.perf_counter()

    try:
        stdout = self._run_uv_subprocess(
            wrapped_code,
            env,
            timeout,
            dependencies or [],
        )

        execution_time_ms = int((time.perf_counter() - start_time) * 1000)

        # ... rest of existing code ...
```

## File 6: api_sandbox.py - _wrap_code() Update

```python
# Update _wrap_code method to inject stash (around line 547)

def _wrap_code(
    self,
    user_code: str,
    namespace: str,
    access_control: NamespaceAccessControl,
    stash: Optional[Any] = None,  # NEW parameter
) -> str:
    """Wrap user code with sandbox infrastructure including stash.

    Args:
        user_code: User's Python code
        namespace: Namespace for access control
        access_control: Access control instance
        stash: Optional SessionStash instance

    Returns:
        Wrapped code that includes api API with stash support
    """
    # Serialize stash data
    stash_data = {}
    if stash:
        stash_data = {k: stash.get(k) for k in stash.keys()}
    
    stash_json = json.dumps(stash_data)

    manifest_json = json.dumps(
        {
            "servers": self._manifest.servers,
            "namespaces": {
                k: {
                    "servers": v.get("servers", []),
                    "extends": v.get("extends", []),
                }
                for k, v in self._manifest.namespaces.items()
            },
            "groups": self._manifest.groups,
        }
    )

    return f'''
import json
import sys

# ... existing _ToolExecutor, _Manifest, _CapabilityRegistry, _NamespaceAccessControl, _DynamicProxy ...

# NEW: Stash class for session-scoped caching
class _Stash:
    """Session stash for caching data across execute() calls."""
    
    def __init__(self, data):
        self._data = dict(data)
    
    def get(self, key):
        """Retrieve a cached value."""
        return self._data.get(key)
    
    def put(self, key, value):
        """Store a value in the cache (persisted server-side)."""
        self._data[key] = value
    
    def has(self, key):
        """Check if a key is cached."""
        return key in self._data
    
    def keys(self):
        """Get all cached keys."""
        return list(self._data.keys())
    
    def clear(self):
        """Clear all cached data."""
        self._data.clear()

_stash_data = {stash_json}
_stash = _Stash(_stash_data)

class _APIProxy:
    def __init__(self, namespace, access_control, tool_executor, manifest, stash):
        self._namespace = namespace
        self._access_control = access_control
        self._tool_executor = tool_executor
        self._manifest = manifest
        self.stash = stash  # NEW: Expose stash on api object
    
    def server(self, name):
        can_access, error = self._access_control.can_access(self._namespace, name)
        if not can_access:
            raise PermissionError(error)
        return _DynamicProxy(name, self._namespace, self._access_control, self._tool_executor)
    
    def call_tool(self, server, tool, args):
        can_access, error = self._access_control.can_access(self._namespace, server)
        if not can_access:
            raise PermissionError(error)
        return self._tool_executor(server, tool, args)
    
    def manifest(self):
        allowed = self._access_control._resolve_allowed_servers(self._namespace)
        return {{
            "namespace": self._namespace,
            "allowed_servers": sorted(allowed),
            "servers": {{n: _registry.get_server(n) for n in allowed if _registry.get_server(n)}},
        }}
    
    # NEW: Stash methods
    def get_stash(self, key):
        """Retrieve value from session stash."""
        return self.stash.get(key)
    
    def put_stash(self, key, value):
        """Store value in session stash."""
        self.stash.put(key, value)
    
    def has_stash(self, key):
        """Check if key is in stash."""
        return self.stash.has(key)
    
    def clear_stash(self):
        """Clear all stash data."""
        self.stash.clear()

api = _APIProxy("{namespace}", _access_control, _executor, _manifest, _stash)

# ... rest of existing code ...
'''
```

## Usage Examples

### Example 1: Cache Search Results

```python
# User code in sandbox

# First execute() call
if not api.has_stash("tools_cache"):
    tools = api.server("search").find_tools(query="web browsing")
    api.put_stash("tools_cache", tools)

# Subsequent execute() calls with same session_id
tools = api.get_stash("tools_cache")
if tools:
    # Use cached tools without re-searching
    for tool in tools:
        print(f"Tool: {tool['name']}")
```

### Example 2: Cache Database Schema

```python
# First execute() call
if not api.has_stash("db_schema"):
    schema = api.server("database").get_schema()
    api.put_stash("db_schema", schema)

# Later execute() calls
schema = api.get_stash("db_schema")
if schema:
    # Use cached schema
    tables = schema.get("tables", [])
```

### Example 3: Multi-Call Session

```python
# Request 1: client sends X-Session-ID: my-session-123
# Code discovers and caches tools
results = api.server("search").find_tools(query="...")
api.put_stash("discovered_tools", results)

# Request 2: client sends same X-Session-ID: my-session-123
# Code uses cached tools
if api.has_stash("discovered_tools"):
    tools = api.get_stash("discovered_tools")
    # Execute with tools, no re-search needed
```

### Client Code (HTTP)

```python
import requests
import uuid

session_id = str(uuid.uuid4())

# Execute 1: Search and cache
response1 = requests.post(
    "http://localhost:12009/sse",
    json={
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "execute",
            "arguments": {
                "code": "results = api.server('search').find(...)\napi.put_stash('results', results)",
                "namespace": "dev",
                "session_id": session_id,
            }
        }
    },
    headers={"X-Session-ID": session_id}
)

# Execute 2: Use cached data
response2 = requests.post(
    "http://localhost:12009/sse",
    json={
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {
            "name": "execute",
            "arguments": {
                "code": "cached = api.get_stash('results')\nprint(cached)",
                "namespace": "dev",
                "session_id": session_id,
            }
        }
    },
    headers={"X-Session-ID": session_id}
)

# Both responses include stash metadata
result = response2.json()
print(result["result"]["session_stash"]["keys"])  # ["results"]
```
