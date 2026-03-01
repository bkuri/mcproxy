# MCProxy ↔ Jesse-MCP Integration Status

**Last Updated:** February 20, 2026

---

## 📋 Summary

**Jesse-MCP:** ✅ Production-ready (all 81 tests pass)
**MCProxy Integration:** ❌ Needs debugging (subprocess communication broken)

---

## 🎯 Issue

MCProxy HTTP gateway cannot forward tool calls to jesse-mcp subprocess. Returns empty error messages:

```json
{
  "error": {
    "code": -32000,
    "message": "Tool call failed: "  ← Empty!
  }
}
```

---

## 📚 Documentation

**Start here:** `docs/requirements/00_READ_ME_FIRST.md`

Complete debugging guide in: `docs/requirements/`

```
docs/requirements/
├── 00_READ_ME_FIRST.md           ← START HERE
├── START_HERE_MCPROXY.txt        ← Quick overview (5 min)
├── MCPROXY_SESSION_CONTEXT.md    ← Quick reference (10 min)
├── MCPROXY_DEBUG_GUIDE.md        ← Detailed guide (30 min)
└── WORK_SUMMARY.md               ← Full context (20 min)
```

---

## 🚀 Quick Start

```bash
# Read the entry point
cat docs/requirements/00_READ_ME_FIRST.md

# Or if you prefer plain text
cat docs/requirements/START_HERE_MCPROXY.txt
```

---

## 🔧 What Needs Fixing

**Primary File:** `/srv/containers/mcproxy/server.py`
- Add detailed error logging to `handle_tools_call()` function
- Verify subprocess communication

**Secondary File:** `/srv/containers/mcproxy/main.py`
- Check environment variable passing to subprocess

---

## ✅ What's Working

- ✅ Jesse-MCP code (81/81 tests passing)
- ✅ MCP tool registration (61 tools)
- ✅ Jesse framework integration
- ✅ `/tools` endpoint
- ✅ Code deployment

---

## ❌ What's Broken

- ❌ Tool execution via HTTP
- ❌ Error messages (empty strings)
- ❌ Subprocess communication

---

## 📊 Estimated Effort

| Phase | Task | Time |
|-------|------|------|
| 1 | Understand docs | 45-60 min |
| 2 | Investigate | 30 min |
| 3 | Identify root cause | 30 min |
| 4 | Implement fix | 1 hour |
| 5 | Test & verify | 30 min |
| **Total** | **Complete debugging** | **2.5-3.5 hours** |

---

## 🔍 Investigation Checklist

Before editing code, confirm:

- [ ] Can SSH to server2: `ssh server2-auto`
- [ ] Jesse API reachable: `curl http://localhost:9100/health`
- [ ] MCProxy running: `curl http://localhost:12010/tools`
- [ ] Jesse-mcp subprocess: `ps aux | grep jesse-mcp`
- [ ] Read all docs: `cat docs/requirements/00_READ_ME_FIRST.md`

---

## 🎬 Next Steps

1. **Read documentation** → `docs/requirements/00_READ_ME_FIRST.md`
2. **Follow 4-phase approach** → `docs/requirements/MCPROXY_SESSION_CONTEXT.md`
3. **Implement fixes** → `docs/requirements/MCPROXY_DEBUG_GUIDE.md`
4. **Test and verify** → Use checklist in debugging guide

---

## 📝 Context

### Jesse-MCP Session (Completed ✅)
- Fixed backtest polling timeout: 60s → 300s
- Added 3 comprehensive timeout tests
- All 81 tests passing
- Code committed and deployed

### MCProxy Session (Pending ❌)
- Debug subprocess communication issue
- Implement fix based on root cause
- Test with real backtest data
- Verify `_mock_data: false` in results

---

## 📞 Reference

- **MCProxy source:** `~/source/mcproxy/`
- **Documentation:** `~/source/mcproxy/docs/requirements/`
- **Jesse-MCP source:** `~/source/jesse-mcp/` (already fixed)
- **Server2 config:** `/srv/containers/mcproxy/`

---

## 🎓 Success Criteria

When fixed:
- ✅ Tools return proper responses (not empty errors)
- ✅ `jesse_status` tool works
- ✅ `strategy_list` tool works
- ✅ `backtest` tool returns real data
- ✅ `_mock_data: false` in results
- ✅ Backtest takes 2-3 minutes (async polling)

---

## 📋 Session Notes

**Session 1 (Feb 20, 2026):** Jesse-MCP fix complete
- Problem: 60-second polling timeout too short
- Solution: Increased to 300 seconds
- Tests: 81/81 passing
- Deployment: Complete

**Session 2 (Pending):** MCProxy integration debugging
- Problem: Subprocess communication broken
- Solution: TBD (4 hypotheses documented)
- Duration: 2-3 hours
- Status: Ready for debugging

---

**Next Action:** Read `docs/requirements/00_READ_ME_FIRST.md`

**Status:** Documentation complete, ready for debugging
