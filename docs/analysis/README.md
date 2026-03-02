# MCProxy Session Stash Architecture Analysis

This directory contains a comprehensive analysis of implementing a session-scoped key-value store (stash) for MCProxy to enable agents to cache data between consecutive `execute()` calls.

## Documents in This Analysis

### 1. **EXECUTIVE_SUMMARY.md** - START HERE
**Length:** 224 lines | **Time to read:** 10 minutes

High-level overview for decision makers:
- Problem statement and solution overview
- Key architecture decisions and rationale
- What files change and how much
- Usage patterns with examples
- Risk assessment and mitigations
- Implementation roadmap with phases
- Success criteria

**Best for:** Understanding the big picture, making go/no-go decisions, high-level planning

---

### 2. **SESSION_STASH_SUMMARY.txt** - QUICK REFERENCE
**Length:** 262 lines | **Time to read:** 8 minutes

Condensed technical summary for developers:
- Current session handling status (what exists now)
- Proposed design architecture
- Integration points (3 files to modify)
- Key decisions with rationale
- Challenges and mitigations
- Files to modify with line counts
- Implementation phases (Phase 1-3)
- Advantages vs disadvantages
- Testing strategy
- Reference points in codebase

**Best for:** Implementation planning, code review prep, quick lookup during coding

---

### 3. **session_stash_design.md** - TECHNICAL SPECIFICATION
**Length:** 433 lines | **Time to read:** 20 minutes

Complete technical design document:
- Detailed current state analysis
  - Request/connection tracking
  - Execution context & subprocess isolation
  - Current data flow diagram
  - Constraints & opportunities
- Proposed architecture sections
  - Session identification strategy
  - Storage architecture (SessionStash & SessionManager classes)
  - Integration points in detail
  - Data flow with stash diagram
  - Usage examples
  - Configuration options
- Files to modify with details
- Advantages and disadvantages
- Potential challenges with solutions
- Implementation phases
- Reference points in codebase

**Best for:** Code implementation, detailed design review, solving integration challenges

---

### 4. **IMPLEMENTATION_SNIPPETS.md** - READY-TO-USE CODE
**Length:** 620 lines | **Time to read:** 30 minutes

Production-ready code snippets organized by file:

1. **server.py changes:**
   - SessionStash class (full implementation with docstrings)
   - SessionManager class (full implementation with docstrings)
   - _get_session_id() helper function
   - Global components update
   - handle_execute() modifications

2. **api_sandbox.py changes:**
   - execute() method signature update
   - _wrap_code() method updates
   - _Stash class in wrapped code
   - _APIProxy class updates

3. **Usage examples:**
   - Cache search results
   - Cache database schema
   - Multi-call session pattern
   - HTTP client code example

**Best for:** Direct copy-paste implementation, code review, integration testing

---

## How to Use This Analysis

### If you're a Project Manager or Decision Maker:
1. Read **EXECUTIVE_SUMMARY.md** (10 min)
2. Review the "Risks & Mitigations" table
3. Check the "Implementation Roadmap" for effort estimates
4. Approve or ask clarifying questions

### If you're implementing Phase 1 (MVP):
1. Read **SESSION_STASH_SUMMARY.txt** (8 min) for overview
2. Skim **IMPLEMENTATION_SNIPPETS.md** for SessionStash/SessionManager (10 min)
3. Code using snippets as template
4. Run tests from testing strategy

### If you're implementing Phase 2+ (Full Feature):
1. Read **session_stash_design.md** carefully (20 min)
2. Review **IMPLEMENTATION_SNIPPETS.md** in detail (30 min)
3. Reference code implementation guidance
4. Implement full test suite
5. Handle TTL and concurrent access concerns

### If you're doing code review:
1. Start with **SESSION_STASH_SUMMARY.txt** for context
2. Use **IMPLEMENTATION_SNIPPETS.md** to verify code matches design
3. Cross-reference **session_stash_design.md** for detailed requirements
4. Check test coverage against testing strategy

### If you're troubleshooting an issue:
1. Consult **SESSION_STASH_SUMMARY.txt** "Challenges & Mitigation" section
2. Review **session_stash_design.md** "Potential Challenges & Solutions"
3. Check integration points in relevant file (server.py, api_sandbox.py, main.py)
4. Verify test coverage in your scenario

## Key Files in MCProxy Codebase (Referenced in Analysis)

```
/home/bk/source/mcproxy/
├── server.py               # Main FastAPI server, session tracking
│   ├─ Line 26: _connection_namespaces (unused, for context)
│   ├─ Line 96-105: _get_namespace_from_request()
│   ├─ Line 473-568: handle_execute() (integration point)
│   └─ Line 20-24: Global components
├── api_sandbox.py          # Sandbox execution, code wrapping
│   ├─ Line 434-545: execute() method
│   ├─ Line 547-742: _wrap_code() method (injection point)
│   └─ Line 156-242: ProxyAPI class
├── main.py                 # Application entry point
│   └─ init_v2_components() function
├── api_manifest.py         # Capability registry (reference)
└── docs/analysis/          # This analysis
```

## Current State (No Session Support)

```
Client Request 1 → execute(code) → Subprocess → Result ⚠️ No state saved
Client Request 2 → execute(code) → Subprocess → Result (redundant lookups)
```

## Proposed State (With Session Stash)

```
Client Request 1 (Session: abc-123)
  ↓
  execute(code, session_id="abc-123")
  ↓
  SessionManager.get_stash("abc-123") → SessionStash created
  ↓
  Subprocess runs, caches results via api.put_stash()
  ↓
  Response returns with stash metadata

Client Request 2 (Session: abc-123)
  ↓
  execute(code, session_id="abc-123")
  ↓
  SessionManager.get_stash("abc-123") → Same SessionStash retrieved
  ↓
  Subprocess accesses cached data via api.get_stash()
  ↓
  No redundant lookups, 100x faster ✓
```

## Quick Facts

| Metric | Value |
|--------|-------|
| **Files to modify** | 3 (server.py, api_sandbox.py, main.py) |
| **Lines of new code** | ~300-500 for full feature |
| **Lines of tests** | ~500 |
| **External dependencies** | None (in-memory only) |
| **Backward compatibility** | 100% (optional feature) |
| **Expected speedup** | 10-100x for repeated queries |
| **Memory overhead** | ~1-10 KB per cached item |
| **API complexity** | Very simple (get, put, has, clear) |
| **Implementation time (Phase 1)** | 1-2 hours |
| **Implementation time (Phase 2-3)** | 8-16 hours total |

## Architecture at a Glance

```python
# SessionManager (global in server.py)
├─ get_stash(session_id) → SessionStash
├─ cleanup_expired() → removes idle sessions
└─ get_stats() → session statistics

# SessionStash (one per session)
├─ put(key, value, ttl_secs=None)
├─ get(key) → value or None if expired
├─ has(key) → bool
├─ delete(key) → bool
├─ clear() → None
├─ keys() → List[str] of non-expired keys
└─ is_expired(idle_timeout_secs=3600) → bool

# Injected API in sandbox (api_sandbox.py wrapped code)
├─ api.get_stash(key)
├─ api.put_stash(key, value)
├─ api.has_stash(key)
└─ api.clear_stash()
```

## Session Identification Strategy

**Header-based (Recommended):**
```
Request: POST /sse
Header: X-Session-ID: agent-claude-abc-123
Body: {"method": "tools/call", "params": {...}}
```

**Param-based (Fallback):**
```
Body: {
  "method": "tools/call", 
  "params": {
    "name": "execute",
    "arguments": {
      "code": "...",
      "session_id": "agent-claude-abc-123"
    }
  }
}
```

**Auto-generated (Last resort):**
- Client doesn't provide session ID
- MCProxy generates: `auto-{client_ip}-{timestamp}`
- Logged as warning for client awareness

## Testing Checklist

- [ ] SessionStash.get() returns correct values
- [ ] SessionStash.get() returns None for missing keys
- [ ] SessionStash.get() expires keys after TTL
- [ ] SessionStash.put() stores values correctly
- [ ] SessionStash.has() works correctly
- [ ] SessionStash.delete() removes keys
- [ ] SessionStash.clear() clears all data
- [ ] SessionManager creates stashes on-demand
- [ ] SessionManager cleanup removes expired sessions
- [ ] Multiple execute() calls with same session_id share stash
- [ ] Stash injected correctly in wrapped code
- [ ] api.get_stash() works in sandbox
- [ ] api.put_stash() works in sandbox
- [ ] api.has_stash() works in sandbox
- [ ] api.clear_stash() works in sandbox
- [ ] Stash metadata in response
- [ ] Different sessions have isolated stashes
- [ ] Concurrent requests don't race
- [ ] Session ID header works
- [ ] Session ID param works
- [ ] Auto-generation works

## Validation Checklist (Before Merge)

- [ ] All tests passing (unit + integration + concurrency)
- [ ] No breaking changes to existing API
- [ ] Backward compatible (code works without stash)
- [ ] Memory usage reasonable (no leaks)
- [ ] Concurrency safe (no race conditions)
- [ ] Documentation updated (AGENTS.md)
- [ ] Code follows project style (type hints, docstrings)
- [ ] Logging appropriate (info, debug, errors)
- [ ] Edge cases handled (None, empty, expired)
- [ ] Performance acceptable (< 10ms overhead)

## Recommendations for Next Steps

1. **Review cycle:**
   - Maintainer reviews EXECUTIVE_SUMMARY.md
   - Tech lead reviews SESSION_STASH_SUMMARY.txt + session_stash_design.md
   - Implementation team reviews IMPLEMENTATION_SNIPPETS.md

2. **Planning:**
   - Decide on Phase 1 vs Phase 1+2 implementation
   - Assign implementation and test writing
   - Set code review schedule

3. **Implementation:**
   - Start with server.py (SessionStash + SessionManager)
   - Follow with api_sandbox.py changes
   - Finish with main.py initialization

4. **Testing:**
   - Write unit tests first (SessionStash operations)
   - Write integration tests (stash in wrapped code)
   - Add concurrency tests
   - Manual testing with client code

5. **Documentation:**
   - Update AGENTS.md with session stash section
   - Add examples to QUICK_START_CHAT.md
   - Document X-Session-ID header requirement

## Questions or Clarifications?

Refer to the relevant document:
- **"How does this work?"** → EXECUTIVE_SUMMARY.md
- **"What's the quick overview?"** → SESSION_STASH_SUMMARY.txt
- **"Show me the details"** → session_stash_design.md
- **"Give me the code"** → IMPLEMENTATION_SNIPPETS.md

---

**Analysis Date:** March 1, 2025  
**MCProxy Version:** v2.0  
**Status:** Ready for implementation approval
