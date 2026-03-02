# MCProxy Session Stash Architecture - Executive Summary

## Problem Statement

MCProxy agents need to cache data (search results, tool metadata, database schemas) between consecutive `execute()` calls within a single session. Currently, each execution is isolated with no persistent inter-call state mechanism.

## Solution Overview

Implement a **session-scoped key-value store** (stash) that allows agents to:
1. Cache expensive results (search, schema discovery) 
2. Share data across multiple execute() calls in the same session
3. Automatically expire old entries via TTL
4. Respect namespace-based access control

## Key Architecture Decisions

| Decision | Rationale |
|----------|-----------|
| **Header-based Session ID** (`X-Session-ID`) | Survives SSE streaming model, client-controlled, correlates multiple POST calls |
| **In-memory storage** | No external dependencies, suitable for single-process gateway |
| **Per-key TTL** | Fine-grained control (search results 1h, schema 4h) |
| **Server-side coordination** | Subprocess gets stash data, puts changes back via response |
| **Simple async-safe API** | Four methods: `get()`, `put()`, `has()`, `clear()` |

## What Changes

### Files Modified: 3 (mostly additive)

**server.py** (~200 lines added)
- Add `SessionStash` class: Per-session key-value store with TTL
- Add `SessionManager` class: Manages all active sessions
- Add `_get_session_id()` helper: Extract/generate session ID from request
- Update `handle_execute()`: Get stash, pass to executor, return in response
- Add cleanup task initialization

**api_sandbox.py** (~80 lines added)  
- Update `execute()` signature: Accept optional `stash` parameter
- Update `_wrap_code()`: Inject stash into wrapped code
- Add `_Stash` class in wrapped code: Simple data container
- Update `_APIProxy`: Add stash access methods (get/put/has/clear)

**main.py** (~10 lines)
- Initialize `SessionManager` 
- Start cleanup task in async main
- Cleanup on shutdown

### Files Created: 1

**tests/test_session_stash.py** (~500 lines)
- SessionStash unit tests (get/put/delete/clear/has/keys/expire)
- SessionManager tests (creation, cleanup, concurrency)
- Stash injection integration tests
- TTL expiration tests
- Namespace isolation tests

## Usage Pattern

### From Client Code

```python
# Set explicit session ID
headers = {"X-Session-ID": "agent-claude-session-xyz"}

# Execute 1: Search and cache
response1 = requests.post(
    "/sse",
    json={
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "execute",
            "arguments": {
                "code": "results = api.server('search').find_tools(...)\napi.put_stash('tools', results)",
                "namespace": "dev",
                "session_id": "agent-claude-session-xyz"
            }
        }
    },
    headers=headers
)

# Execute 2: Use cached data (same session_id)
response2 = requests.post(
    "/sse",
    json={
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "execute",
            "arguments": {
                "code": "tools = api.get_stash('tools')\napi.call_tool(tools[0]['server'], tools[0]['name'], {})",
                "namespace": "dev",
                "session_id": "agent-claude-session-xyz"
            }
        }
    },
    headers=headers
)
```

### From Sandbox Code

```python
# Check and populate cache
if not api.has_stash("db_schema"):
    schema = api.server("database").get_schema()
    api.put_stash("db_schema", schema, ttl_secs=7200)
else:
    schema = api.get_stash("db_schema")

# Use cached schema
tables = schema.get("tables", [])
```

## Response Format Enhancement

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [...],
    "session_stash": {
      "keys": ["search_results", "db_schema", "tool_metadata"],
      "updated_at": 1709268890.5
    }
  }
}
```

## Performance Impact

### Gains
- **Avoid redundant searches**: Cache results for 1 hour, use in multiple calls
- **Reduce I/O**: Database schema lookup happens once per session
- **Faster agent execution**: Cached data retrieval is instant

### Costs  
- **Memory**: ~1-10 KB per cached item (minimal for typical queries/schemas)
- **CPU**: Negligible (dict lookups, TTL checking)
- **Latency**: None (in-memory, no I/O)

## Deployment Characteristics

- **Backward Compatible**: Existing code works without changes (optional feature)
- **Single-Process**: In-memory only, works in current deployment model
- **Stateless Gateway**: MCProxy doesn't maintain global state (per-session stash)
- **No Infrastructure**: No Redis, database, or other dependencies
- **Zero Configuration**: Works out-of-box, optional tuning via mcproxy.json

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| **Session ID not provided** | Auto-generate from IP+timestamp, log warning |
| **Cross-namespace access** | Can enforce namespaced keys (future enhancement) |
| **Memory exhaustion** | Per-key TTL, session cleanup task, max size limits |
| **Concurrent access race** | asyncio.Lock in SessionManager |
| **Subprocess updates lost** | Return stash delta in response, server applies |

## Implementation Roadmap

### Phase 1: MVP (100 lines, 1-2 hours)
✓ SessionStash and SessionManager in server.py
✓ Read-only stash injection (api.get_stash(), api.has_stash())
✓ Basic integration tests
- No write support yet
- No TTL yet

### Phase 2: Full Feature (300 lines, 4-6 hours)
- Write support (api.put_stash(), api.delete_stash(), api.clear_stash())
- TTL per key (ttl_secs parameter)
- Subprocess returns stash updates
- Configuration in mcproxy.json
- Comprehensive tests

### Phase 3: Production (200 lines, 4-8 hours)
- Namespace isolation enforcement
- Max size limits and metrics
- Admin endpoints for inspection
- Optional persistence (checkpoint stashes)

## Testing Strategy

| Test Type | Coverage |
|-----------|----------|
| **Unit** | SessionStash ops, TTL logic, expiration |
| **Integration** | Stash injection, multi-execute calls, response format |
| **Concurrency** | Multiple requests to same session, cleanup during requests |
| **Edge Cases** | Missing session ID, expired keys, large values |

## Success Criteria

- Agents can cache search results and reuse across execute() calls
- TTL automatically expires stale data (no memory leaks)
- Multiple concurrent sessions isolated (no cross-contamination)
- Response includes stash metadata (observable)
- Backward compatible (no breaking changes)
- < 10ms overhead per execute() call

## Comparison to Alternatives

| Approach | Pros | Cons |
|----------|------|------|
| **Session Stash (Proposed)** | Simple, in-memory, no deps | Subprocess updates need coordination |
| **Redis** | Distributed, persistent | Extra dependency, deployment complexity |
| **SQLite** | Local persistence | Overkill for session caching |
| **Global Variables** | Simplest | Not namespace-isolated, race conditions |
| **Request Context** | Per-request isolation | Doesn't span multiple POST calls |

## Next Steps

1. **Review** this analysis (EXECUTIVE_SUMMARY.md)
2. **Detail** implementation plan from SESSION_STASH_SUMMARY.txt
3. **Code** Phase 1 MVP using IMPLEMENTATION_SNIPPETS.md
4. **Test** with unit and integration tests
5. **Merge** and document in AGENTS.md

## Files to Review

- `docs/analysis/session_stash_design.md` - Full technical specification
- `docs/analysis/SESSION_STASH_SUMMARY.txt` - Quick reference
- `docs/analysis/IMPLEMENTATION_SNIPPETS.md` - Ready-to-use code
- This document - Executive overview
