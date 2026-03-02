# MCProxy Session Stash Architecture Analysis

## Current Session Handling Status

### 1. Request/Connection Tracking

**Current Approach:**
- Line 26 in `server.py`: `_connection_namespaces: Dict[int, str] = {}`
  - This dict is defined but **NOT CURRENTLY USED** anywhere in the code
  - Intended to track namespace per connection, but never populated or referenced
  - Could use `id(request)` as key, but request objects are ephemeral

**Request Identification:**
- Each FastAPI request has `request.client` (tuple of IP:port)
- SSE connections are long-lived but individual POST messages are stateless
- No persistent session identifier exists currently
- Namespace is passed per-request via:
  - URL path parameter: `/sse/{namespace}`
  - Header: `X-Namespace`
  - Effective namespace resolved in `handle_message()` (line 297)

**Key Limitation:** SSE is streaming with GET connection + stateless POST messages
- GET stream is connection-oriented (can track via `request.client`)
- POST messages are request-scoped (ephemeral)
- No built-in session token or ID mechanism

### 2. Execution Context & Subprocess Isolation

**Sandbox Execution (api_sandbox.py):**
- Each `execute()` call (line 434) spawns a NEW uv subprocess
- Subprocess receives manifest + access control injected into wrapped code
- User code executes in isolation with access to `api` object
- **Results are NOT persisted** - each subprocess is ephemeral

**Current State Management in Wrapped Code:**
- Lines 577-742: `_wrap_code()` injects infrastructure
- `_ToolExecutor` class (line 581): Tracks pending tool calls during execution
  - `self._pending = []` - stores tool calls to be executed by server.py
  - These are returned as `pending_calls` in output (line 738)
- `_APIProxy` class (line 689): Provides `api.server()`, `api.call_tool()`, `api.manifest()`
- **No persistent stash** - everything is local to the subprocess execution

### 3. Current Data Flow

```
Client
  ↓
FastAPI POST /sse or /sse/{namespace}
  ↓
handle_message() → resolve effective namespace
  ↓
handle_execute()
  ↓
SandboxExecutor.execute()
  ├─ validate_code()
  ├─ _wrap_code() → inject infrastructure + user code
  ├─ _run_uv_subprocess() → spawn new process
  │   └─ subprocess outputs JSON with result + pending_calls
  ├─ Parse output → extract result, traceback, pending_calls
  ├─ Execute pending_calls via tool_executor
  └─ Return combined result

Result returned to client (no state persisted)
```

### 4. Constraints & Opportunities

**Subprocess Model Issues:**
- Each execute() call spawns fresh subprocess with no prior state
- No inter-subprocess communication
- No persistent storage mechanism

**HTTP Protocol Issues:**
- SSE GET stream is long-lived but read-only
- POST messages are independent
- No built-in mechanism to correlate consecutive POST calls to same "session"

**Positive Factors:**
- Namespace already provides access control scope
- Request headers allow metadata passing
- Server.py has global component references (capability_registry, sandbox_executor)
- Could leverage async context variables or request scoping

## Proposed Session Stash Architecture

### Design Goals
1. **Session Scoping**: Cache data for agent within a single conversation/interaction
2. **Isolation**: Each session (agent) has isolated stash
3. **Simplicity**: In-memory only (no Redis needed)
4. **Namespace-Aware**: Respect namespace access control
5. **TTL Support**: Configurable expiration
6. **Non-Intrusive**: Minimal changes to existing code

### Proposed Architecture

#### 1. Session Identification

**Key Decision: Use request headers for session ID**

```python
# Proposed header: X-Session-ID
# Example: X-Session-ID: agent-claude-session-123
# If not provided: generate UUID or use client IP + timestamp

# Implementation location: server.py _get_session_id()
def _get_session_id(request: Request) -> str:
    """Extract or generate session ID from request."""
    session_id = request.headers.get("X-Session-ID")
    if session_id:
        return session_id
    # Fallback: client IP + request path (less reliable)
    ip = request.client[0] if request.client else "unknown"
    return f"anon-{ip}-{int(time.time())}"
```

**Why Headers?**
- Clients (Claude Desktop, agents) can set explicit session ID
- Correlates multiple consecutive execute() calls
- Survives SSE streaming model
- Backward compatible (optional)

#### 2. Session Stash Storage

**Location: Global SessionManager in server.py**

```python
import asyncio
import time
from typing import Any, Dict, Optional

class SessionStash:
    """Per-session key-value store with TTL."""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self._data: Dict[str, Any] = {}
        self._ttl_map: Dict[str, float] = {}  # key -> expiration_time
        self._created_at = time.time()
    
    def put(self, key: str, value: Any, ttl_secs: Optional[int] = None) -> None:
        """Store value with optional TTL."""
        self._data[key] = value
        if ttl_secs:
            self._ttl_map[key] = time.time() + ttl_secs
        else:
            self._ttl_map.pop(key, None)  # No expiration
    
    def get(self, key: str) -> Optional[Any]:
        """Retrieve value if exists and not expired."""
        if key not in self._data:
            return None
        
        expiration = self._ttl_map.get(key)
        if expiration and time.time() > expiration:
            self._data.pop(key)
            self._ttl_map.pop(key)
            return None
        
        return self._data[key]
    
    def has(self, key: str) -> bool:
        """Check if key exists and not expired."""
        return self.get(key) is not None
    
    def delete(self, key: str) -> bool:
        """Remove key from stash."""
        if key in self._data:
            self._data.pop(key)
            self._ttl_map.pop(key, None)
            return True
        return False
    
    def clear(self) -> None:
        """Clear all data in stash."""
        self._data.clear()
        self._ttl_map.clear()
    
    def keys(self) -> List[str]:
        """List all non-expired keys."""
        # Filter out expired keys
        now = time.time()
        active_keys = [
            k for k in self._data.keys()
            if k not in self._ttl_map or self._ttl_map[k] > now
        ]
        return active_keys
    
    def is_expired(self) -> bool:
        """Check if session itself is stale (no activity, long time)."""
        # Sessions expire after 1 hour of no updates
        return time.time() - self._created_at > 3600


class SessionManager:
    """Manages stashes for all active sessions."""
    
    def __init__(self):
        self._sessions: Dict[str, SessionStash] = {}
        self._lock = asyncio.Lock()  # For thread-safety
    
    async def get_stash(self, session_id: str) -> SessionStash:
        """Get or create stash for session."""
        async with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionStash(session_id)
            return self._sessions[session_id]
    
    async def cleanup_expired(self) -> None:
        """Remove expired sessions (runs periodically)."""
        async with self._lock:
            expired = [
                sid for sid, stash in self._sessions.items()
                if stash.is_expired()
            ]
            for sid in expired:
                del self._sessions[sid]
            if expired:
                logger.info(f"[SESSION_CLEANUP] Removed {len(expired)} expired sessions")
```

#### 3. Integration Points

**Location: api_sandbox.py - _APIProxy class**

Add stash access to injected API:

```python
class _APIProxy:
    def __init__(self, namespace, access_control, tool_executor, manifest, stash):
        # ... existing init ...
        self.stash = stash
    
    # Methods for stash in wrapped code:
    def get_stash(self, key):
        """Get value from session stash."""
        return self.stash.get(key)
    
    def put_stash(self, key, value, ttl=None):
        """Store value in session stash."""
        self.stash.put(key, value, ttl)
    
    def has_stash(self, key):
        """Check if key exists in stash."""
        return self.stash.has(key)
    
    def clear_stash(self):
        """Clear all data in stash."""
        self.stash.clear()
```

#### 4. Execution Flow Integration

**Location: server.py - handle_execute()**

```python
async def handle_execute(
    msg_id: Any, params: Dict, connection_namespace: Optional[str] = None
) -> Dict[str, Any]:
    """..."""
    
    # Extract session ID from request (passed as param or header)
    session_id = params.get("session_id") or _get_session_id(request)
    
    # Get session stash
    stash = await session_manager.get_stash(session_id)
    
    # Pass stash to sandbox executor
    result = sandbox_executor.execute(
        code, 
        namespace=effective_namespace, 
        timeout_secs=timeout_secs,
        session_id=session_id,
        stash=stash
    )
    
    # Return updated stash state to client
    result["session_stash"] = {
        "keys": stash.keys(),
        "updated_at": time.time()
    }
```

#### 5. Data Flow with Stash

```
Client (e.g., Claude Agent)
  │
  ├─ Request 1: execute(code, X-Session-ID: agent-123)
  │   ├─ SessionManager gets stash for "agent-123"
  │   ├─ execute() returns result + stash metadata
  │   ├─ Agent caches search results in stash
  │   └─ Client receives response with stash keys
  │
  ├─ Request 2: execute(code, X-Session-ID: agent-123)
  │   ├─ SessionManager retrieves same stash
  │   ├─ User code accesses cached search results via api.get_stash()
  │   └─ Avoids redundant lookups
  │
  └─ Request 3 (later): SSE disconnects
      └─ SessionManager marks session stale, cleans up after TTL
```

### 6. Usage Example in User Code

```python
# Search and cache results
query = "web browsing tools"
if not api.has_stash("search_results"):
    results = api.server("search").find_tools(query=query)
    api.put_stash("search_results", results, ttl=3600)
else:
    results = api.get_stash("search_results")

# Execute the found tool without re-searching
tool = results[0]
api.call_tool(tool["server"], tool["name"], {"url": "..."})
```

### 7. Configuration & Defaults

**In mcproxy.json (optional):**
```json
{
  "session": {
    "enabled": true,
    "ttl_secs": 3600,
    "max_sessions": 1000,
    "cleanup_interval_secs": 60
  }
}
```

**In api_sandbox.py (defaults):**
```python
SESSION_STASH_ENABLED = True
SESSION_TTL_SECS = 3600
SESSION_CLEANUP_INTERVAL = 60.0
SESSION_MAX_SIZE = 10 * 1024 * 1024  # 10MB per session
```

## Files to Modify

1. **server.py**
   - Add SessionManager global
   - Add _get_session_id() helper
   - Modify handle_execute() to get/use stash
   - Add cleanup background task

2. **api_sandbox.py**
   - Modify SandboxExecutor.execute() signature to accept stash
   - Modify _wrap_code() to inject stash
   - Add stash to wrapped code _APIProxy class
   - Add stash_json serialization

3. **main.py**
   - Initialize SessionManager
   - Start cleanup task in main()
   - Clean up on shutdown

4. **tests/** (new)
   - Test SessionStash operations
   - Test SessionManager concurrency
   - Test stash injection in sandbox
   - Test TTL expiration
   - Test namespace isolation (no cross-session access)

5. **mcproxy.json** (optional)
   - Add session configuration section

## Advantages of This Design

1. **Minimal Changes**: Mostly additive, doesn't break existing API
2. **Namespace-Aware**: Can respect existing access control
3. **Simple**: In-memory dict + TTL, no external dependencies
4. **Stateless Gateway**: MCProxy stays stateless (stash managed per-session, not globally)
5. **Client-Controlled**: Clients explicitly identify sessions (X-Session-ID header)
6. **Safe**: Expired sessions automatically cleaned up
7. **Observable**: Stash keys returned in response metadata
8. **Backward Compatible**: Optional, existing code works without it

## Potential Challenges & Solutions

### Challenge 1: Session Identification Reliability
- Problem: Relying on client headers is fragile
- Solution: Clients should use UUIDs; fallback to auto-generation but warn in logs

### Challenge 2: Cross-Namespace Access
- Problem: One namespace shouldn't access another session's stash
- Solution: Namespace passed to SessionManager; could enforce namespaced stash keys

### Challenge 3: Memory Leaks
- Problem: Long-lived sessions accumulate data
- Solution: 
  - TTL-based cleanup per key
  - Session-level TTL (expire unused sessions)
  - Max size limits per session
  - Periodic garbage collection

### Challenge 4: Concurrent Access
- Problem: Multiple requests in same session could race
- Solution: Use asyncio.Lock in SessionManager

### Challenge 5: Subprocess Doesn't Persist Updates
- Problem: Stash changes in subprocess don't auto-save
- Solution: Return stash updates in output, server.py applies them before cleanup

## Implementation Phases

### Phase 1: Core (MVP)
- SessionManager + SessionStash in server.py
- Inject into api_sandbox.py (read-only initially)
- Basic tests
- No configuration needed

### Phase 2: Full Integration
- Write support in sandbox (put/delete/clear)
- Update mechanism (subprocess returns new state)
- TTL support
- Configuration in mcproxy.json

### Phase 3: Advanced
- Namespace isolation enforcement
- Max size limits
- Detailed logging/metrics
- Admin endpoints (cleanup, inspection)

## References in Codebase

- Session tracking attempt: `server.py:26` (_connection_namespaces)
- Namespace context: `server.py:96-105` (_get_namespace_from_request)
- Sandbox execution: `api_sandbox.py:434-545` (execute method)
- Wrapped code injection: `api_sandbox.py:577-742` (_wrap_code)
- Global components: `server.py:20-24` (global variables)
