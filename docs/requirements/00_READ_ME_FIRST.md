# MCProxy Integration Debugging - READ ME FIRST

## Current Situation

**Jesse-MCP is production-ready.** All 81 unit tests pass. The code has been fixed and deployed.

**MCProxy integration needs debugging.** The HTTP gateway cannot forward tool calls to the jesse-mcp subprocess.

---

## What's Wrong

When you call a tool via HTTP:
```bash
curl -X POST http://localhost:12010/message \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"jesse_status","arguments":{}}}'
```

You get back an empty error:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32000,
    "message": "Tool call failed: "  ← Notice the empty message!
  }
}
```

---

## What's Working

✅ Jesse-MCP process starts successfully
✅ All 61 MCP tools register properly  
✅ `/tools` endpoint returns full tool list
✅ Jesse framework initializes correctly
✅ Code is tested and deployed

❌ Tool execution via HTTP fails
❌ Error messages are empty/blank
❌ Subprocess communication broken

---

## How to Fix It

### Step 1: Understand the Documents (20 minutes)

Read in this order:
1. **START_HERE_MCPROXY.txt** - Overview
2. **MCPROXY_SESSION_CONTEXT.md** - Quick reference
3. **MCPROXY_DEBUG_GUIDE.md** - Detailed instructions

### Step 2: Investigate (30 minutes)

Follow Phase 1 in MCPROXY_SESSION_CONTEXT.md:
- Check if jesse-mcp subprocess is running
- Check mcproxy logs for errors
- Test subprocess directly
- Enable debug logging

### Step 3: Identify Root Cause (30 minutes)

Based on investigation, determine which is the issue:
1. Subprocess crashing silently
2. Message format problem
3. Environment variables not passed
4. Timeout on communication

### Step 4: Implement Fix (1 hour)

Apply the appropriate fix from MCPROXY_DEBUG_GUIDE.md:
- Fix 1: Add error logging (HIGH PRIORITY)
- Fix 2: Verify env vars (HIGH PRIORITY)
- Fix 3: Check for crashes (MEDIUM)
- Fix 4: Handle timeouts (MEDIUM)

### Step 5: Test & Verify (30 minutes)

Use the testing checklist to confirm:
- Tools return proper responses
- Backtest returns real data (not mock)
- No timeout errors

---

## File Guide

| File | Purpose | Read Time | When |
|------|---------|-----------|------|
| START_HERE_MCPROXY.txt | Quick overview | 5 min | First |
| INDEX.md | Doc index & overview | 5 min | Second |
| MCPROXY_SESSION_CONTEXT.md | Quick reference & phases | 10 min | While debugging |
| MCPROXY_DEBUG_GUIDE.md | Detailed technical guide | 30 min | For specifics |
| WORK_SUMMARY.md | Full project history | 20 min | For context |

---

## Key Commands

```bash
# SSH to server2
ssh server2-auto

# Check if jesse-mcp is running
ps aux | grep jesse-mcp | grep -v grep

# Test /tools endpoint
curl http://localhost:12010/tools | python3 -m json.tool | head -20

# Try a tool call (will fail currently)
curl -X POST http://localhost:12010/message \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"jesse_status","arguments":{}}}'

# Check mcproxy logs
journalctl -u mcproxy -n 50 --no-pager
```

---

## Primary File to Edit

**`/srv/containers/mcproxy/server.py`**

Find the `handle_tools_call()` function and add detailed error logging:

```python
async def handle_tools_call(msg_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        tool_name = params.get("name")
        logger.info(f"[TOOL_CALL] Starting: {tool_name}")
        # ... rest of code ...
    except Exception as e:
        import traceback
        logger.error(f"[TOOL_CALL_ERROR] {tool_name}: {str(e)}")
        logger.error(f"[TOOL_CALL_TRACEBACK] {traceback.format_exc()}")
        return {"success": False, "error": str(e)}
```

See MCPROXY_DEBUG_GUIDE.md Step 3 for exact code.

---

## Success Criteria

You'll know it's fixed when:
- ✅ Tool calls return proper responses (not empty errors)
- ✅ `jesse_status` tool returns data
- ✅ `backtest` tool returns real metrics
- ✅ `_mock_data: false` in results (not true)
- ✅ Backtest takes 2-3 minutes (async polling works)

---

## Quick Decision Tree

```
Can I SSH to server2?
├─ No  → Use: ssh server2-auto (no YubiKey touch)
└─ Yes → Continue

Is jesse-mcp subprocess running?
├─ No  → Start it: /srv/containers/mcproxy/venv/bin/jesse-mcp
└─ Yes → Continue

Does /tools endpoint work?
├─ No  → MCProxy HTTP server is down (restart it)
└─ Yes → Continue

Can I call tools?
├─ Yes → Great! MCProxy is fixed. Test with backtest tool.
└─ No  → Follow the 4-phase debugging approach in MCPROXY_SESSION_CONTEXT.md
         Start with: Adding debug logging to server.py
```

---

## Time Estimate

- **Reading docs:** 45-60 minutes
- **Phase 1 (Investigate):** 30 minutes  
- **Phase 2 (Identify):** 30 minutes
- **Phase 3 (Implement):** 1 hour
- **Phase 4 (Test):** 30 minutes

**Total:** 2.5-3.5 hours

---

## Where to Go Next

1. Open: `START_HERE_MCPROXY.txt`
2. Then: `MCPROXY_SESSION_CONTEXT.md`
3. Then: `MCPROXY_DEBUG_GUIDE.md`

All documents in: `~/source/mcproxy/docs/requirements/`

---

**Status:** Ready for debugging
**Next Action:** Read START_HERE_MCPROXY.txt
**Difficulty:** Moderate (well-documented)

Good luck! 🚀
