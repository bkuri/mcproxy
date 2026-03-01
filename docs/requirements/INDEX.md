# Jesse-MCP & MCProxy Integration - Documentation Index

All documents are in `/tmp/` and ready for your next OpenCode session.

## Quick Start

**You are here:** End of session 1
**Goal for session 2:** Fix MCProxy HTTP gateway to properly forward tool calls

```
Next OpenCode Session:
1. Read this file
2. Read /tmp/MCPROXY_SESSION_CONTEXT.md (5 min)
3. Follow Phase 1 in /tmp/MCPROXY_DEBUG_GUIDE.md (30 min)
4. Implement fixes from Phase 2-4 (2-3 hours)
```

## Documents Available

### 1. **WORK_SUMMARY.md** - Complete Project History
**When to read:** Start here for full context
**Contains:**
- What was accomplished (Jesse-MCP fix)
- What still needs fixing (MCProxy integration)
- Commits made and test results
- Architecture diagrams
- Known issues and recommendations
- Questions for next maintainer

**Key section:** "Known Issues" - explains MCProxy problem clearly

---

### 2. **MCPROXY_SESSION_CONTEXT.md** - Quick Reference
**When to read:** Before starting debugging work
**Contains:**
- What to do in each phase (4 phases, 2-3 hours total)
- SSH commands for server2
- File locations you'll need to edit
- Success indicators and test checklist
- Escalation guidance

**Key section:** "Recommended Approach" - 4-phase plan

---

### 3. **MCPROXY_DEBUG_GUIDE.md** - Detailed Technical Guide
**When to read:** During actual debugging/fixing
**Contains:**
- 4 hypotheses about root cause (ranked by likelihood)
- 5 investigation steps with code examples
- 4 fixes to try (in priority order)
- Testing procedures and validation
- Success criteria

**Key sections:**
- "Investigation Steps" - How to diagnose the problem
- "Fixes to Try" - Code changes to implement
- "Testing Checklist" - How to verify your fix works

---

## The Problem (One Page Summary)

### Current Status
- ✅ **Jesse-MCP code:** Working perfectly (81 tests pass)
- ❌ **MCProxy gateway:** Cannot forward tool calls to subprocess

### What's Broken
```
User → curl → mcproxy → jesse-mcp
         ↓
       Returns: {"error": ""}  ← Empty error message!
```

### Why It Matters
- Users can't call trading tools via HTTP
- Backtest results are mock data instead of real
- LLM agents can't interact with jesse-mcp

### What You Need To Do
1. Identify why MCProxy subprocess communication is failing
2. Fix the communication issue
3. Test that tools work end-to-end
4. Verify backtest results are real (not mock)

---

## Architecture Quick Reference

### Jesse-MCP (✅ Working)
```
FastMCP Server (61 tools)
↓
Jesse Framework (trading)
↓
Jesse REST API (http://localhost:9100)
```

### MCProxy (❌ Broken)
```
HTTP Client (curl/LLM)
↓
MCProxy HTTP Server (port 12010)
- /tools endpoint ✅ works
- /message endpoint ❌ fails
↓
jesse-mcp subprocess (stdio MCP)
- Process starts ✅
- Tool execution ❌ fails
```

---

## Key Locations on Server2

```
/srv/containers/mcproxy/
  ├── server.py            ← PRIMARY FILE TO EDIT
  ├── main.py              ← Secondary file
  ├── config/
  │   └── mcp-servers.json ← Configuration
  └── venv/                ← Python environment

/srv/mcp-sources/jesse-mcp/
  ├── jesse_mcp/           ← DO NOT EDIT (already working)
  ├── tests/               ← Reference only
  └── .git/                ← Source code

/srv/containers/apps/jesse/
  └── .env                 ← Jesse config
```

---

## Investigation Checklist

Before you edit code, answer these questions:

- [ ] Is jesse-mcp subprocess currently running?
- [ ] Can I list tools with `/tools` endpoint?
- [ ] What does mcproxy log say when I try to call a tool?
- [ ] Can jesse-mcp work with direct stdio MCP messages (bypass mcproxy)?
- [ ] Are environment variables (JESSE_URL, JESSE_PASSWORD) being passed?

If you can answer these, you'll know exactly what to fix.

---

## Expected Outcome

When you're done, this should work:

```bash
curl -X POST http://localhost:12010/message \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "backtest",
      "arguments": {
        "strategy": "SMACrossover",
        "symbol": "BTC-USDT",
        "timeframe": "1h",
        "start_date": "2024-01-01",
        "end_date": "2024-02-01"
      }
    }
  }' | jq '.result.structuredContent.total_return'

# Should return:
# 0.0990 (NOT 0.1248 - that's mock data)
```

The key is: `"_mock_data": false` instead of `true`.

---

## Time Estimates

- **Reading documentation:** 15-20 minutes
- **Phase 1 (Investigation):** 30 minutes
- **Phase 2 (Identify issue):** 30 minutes
- **Phase 3 (Implement fix):** 1 hour
- **Phase 4 (Test & verify):** 30 minutes
- **Total:** 2.5-3.5 hours

---

## Common Issues & Troubleshooting

### "I can't SSH to server2"
```bash
# Use the auto version (no YubiKey touch needed)
ssh server2-auto
```

### "Jesse API is not responding"
```bash
# Check if Jesse container is running
docker ps | grep jesse
# Or check if service is on port 9100
curl http://localhost:9100/health
```

### "I don't know where to start"
1. Read MCPROXY_SESSION_CONTEXT.md (Quick reference)
2. Read MCPROXY_DEBUG_GUIDE.md (Detailed guide)
3. Follow Phase 1 investigation steps
4. Answer the Investigation Checklist questions
5. Implement appropriate fix from Phase 3

### "The error message is still empty"
That's the exact problem we're trying to solve! See MCPROXY_DEBUG_GUIDE.md:
- "Fix 1: Add Error Message Logging to mcproxy"
- "Step 3: Enable Debug Logging"

---

## Success Criteria

- [ ] Tools return proper responses (not empty errors)
- [ ] `jesse_status` tool works
- [ ] `strategy_list` tool works
- [ ] `backtest` tool returns real data
- [ ] `_mock_data` is false, not true
- [ ] Backtest takes 2-3 minutes (async polling works)
- [ ] No timeout errors on reasonable requests

---

## Files to Reference (Don't Edit)

- `/srv/mcp-sources/jesse-mcp/` - Jesse-MCP source (working perfectly)
- `/srv/containers/apps/jesse/` - Jesse service (external dependency)
- `/home/bk/source/jesse-mcp/` - GitHub repo (reference)

## Files to Edit (MCProxy Only)

- `/srv/containers/mcproxy/server.py` - Main fix needed here
- `/srv/containers/mcproxy/main.py` - Secondary file if needed
- `/srv/containers/mcproxy/config/mcp-servers.json` - Check/verify config

---

## Questions Before You Start

1. **What do I edit first?**
   - Follow MCPROXY_SESSION_CONTEXT.md Phase 1
   - Add debug logging to server.py
   - Test and see what errors you get

2. **How do I know if my fix worked?**
   - Run the Testing Checklist in MCPROXY_DEBUG_GUIDE.md
   - Verify `_mock_data` is false
   - Check backtest execution time (should be 2-3 min, not instant)

3. **What if I get stuck?**
   - Check Hypothesis 1, 2, 3 in MCPROXY_DEBUG_GUIDE.md
   - Re-read Investigation Steps carefully
   - Try the fixes in order of likelihood

4. **Can I break something?**
   - Jesse-MCP code is read-only (already working)
   - Your changes are isolated to MCProxy
   - Worst case: restart mcproxy and try again

---

## Contact & Escalation

If completely stuck:
1. Check all 4 hypotheses in MCPROXY_DEBUG_GUIDE.md
2. Verify Jesse API is actually running
3. Verify env variables are set
4. Review MCP specification: https://spec.modelcontextprotocol.io/

---

## Session 1 Summary (What Was Done)

✅ Fixed Jesse-MCP polling timeout: 60s → 300s
✅ Added 3 comprehensive timeout tests  
✅ All 81 unit tests passing
✅ Code deployed to server2
✅ Documentation prepared for next session

❌ MCProxy HTTP gateway still broken
❌ Tool calls return empty error messages
❌ Subprocess communication not working

**Status:** Ready for Session 2 MCProxy debugging

---

**Location:** `/tmp/`
**Total Files:** 4 documents
**Total Size:** ~15KB
**Format:** Markdown (easy to read in terminal)

**Last Updated:** February 20, 2026, 16:59 UTC

---

## File Manifest

```
/tmp/
├── README.md                      ← You are here
├── WORK_SUMMARY.md                (Project history, 500+ lines)
├── MCPROXY_SESSION_CONTEXT.md     (Quick reference, 300+ lines)
└── MCPROXY_DEBUG_GUIDE.md         (Technical guide, 400+ lines)
```

**Total Documentation:** ~1500 lines
**Time to read all:** 45-60 minutes
**Time to implement fixes:** 2-3 hours

---

Good luck! Start with `MCPROXY_SESSION_CONTEXT.md` for the quick overview, then dive into `MCPROXY_DEBUG_GUIDE.md` for detailed steps.

The code is ready, the docs are prepared, and the problem is well-understood.

You've got this! 🚀
