# MCProxy Documentation

## Directory Structure

```
docs/
├── README.md (this file)
└── requirements/
    ├── INDEX.md                      - Documentation index & quick start
    ├── START_HERE_MCPROXY.txt        - Plain text quick start guide
    ├── MCPROXY_SESSION_CONTEXT.md    - Quick reference & 4-phase approach
    ├── MCPROXY_DEBUG_GUIDE.md        - Detailed technical debugging guide
    └── WORK_SUMMARY.md               - Complete project history
```

## Purpose

These documents provide comprehensive guidance for debugging and fixing MCProxy's integration with jesse-mcp. The issue: MCProxy HTTP gateway cannot forward tool calls to jesse-mcp subprocess (returns empty error messages).

## Quick Start

1. **Start here:** `docs/requirements/START_HERE_MCPROXY.txt`
2. **Full context:** `docs/requirements/INDEX.md`
3. **Quick reference:** `docs/requirements/MCPROXY_SESSION_CONTEXT.md`
4. **Detailed guide:** `docs/requirements/MCPROXY_DEBUG_GUIDE.md`
5. **Project context:** `docs/requirements/WORK_SUMMARY.md`

**Estimated time:** 45 minutes to read, 2-3 hours to implement fix

## Status

- ✅ Jesse-MCP code: Production-ready (81 tests pass)
- ❌ MCProxy integration: Needs debugging
- 📋 Documentation: Complete and comprehensive

## Key Files to Edit

**Primary:** `/srv/containers/mcproxy/server.py`
- Add debug logging to `handle_tools_call()` function
- Verify subprocess communication

**Secondary:** `/srv/containers/mcproxy/main.py`  
- Check environment variable passing

## Next Steps

1. Read the quick start guide
2. Follow the 4-phase debugging approach
3. Implement fixes as identified
4. Test and verify with the provided checklist

---

**Created:** February 20, 2026
**Status:** Ready for next debugging session
