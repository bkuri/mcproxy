# MCProxy Documentation Index

## 🎯 Quick Access

### Start Here (First Time)
**File:** `docs/requirements/00_READ_ME_FIRST.md`
- Overview of the issue
- Step-by-step fix process
- Success criteria
- Time estimates

### Status Overview
**File:** `MCPROXY_INTEGRATION_STATUS.md`
- Current integration status
- What's working/broken
- Next steps
- Quick checklist

### During Debugging
**File:** `docs/requirements/MCPROXY_SESSION_CONTEXT.md`
- Quick reference commands
- 4-phase approach
- File locations to edit
- Troubleshooting tips

### Detailed Technical Guide
**File:** `docs/requirements/MCPROXY_DEBUG_GUIDE.md`
- 4 hypotheses (ranked by likelihood)
- 5 investigation steps with code examples
- 4 fixes to try (in priority order)
- Complete testing checklist

### Full Project Context
**File:** `docs/requirements/WORK_SUMMARY.md`
- Complete project history
- Architecture diagrams
- All accomplishments
- Technical details

### Plain Text Quick Start
**File:** `docs/requirements/START_HERE_MCPROXY.txt`
- Plain text version
- For terminal viewing
- Same content as 00_READ_ME_FIRST.md

---

## 📂 Directory Structure

```
~/source/mcproxy/
├── DOCUMENTATION_INDEX.md         ← You are here
├── MCPROXY_INTEGRATION_STATUS.md  ← Status overview
├── docs/
│   ├── README.md                  ← Docs directory overview
│   └── requirements/
│       ├── 00_READ_ME_FIRST.md    ← START HERE
│       ├── START_HERE_MCPROXY.txt ← Plain text version
│       ├── INDEX.md               ← Docs index
│       ├── MCPROXY_SESSION_CONTEXT.md
│       ├── MCPROXY_DEBUG_GUIDE.md
│       └── WORK_SUMMARY.md
```

---

## 🚀 Getting Started

### Step 1: Understand the Problem (5 min)
```bash
cat MCPROXY_INTEGRATION_STATUS.md
```

### Step 2: Read the Entry Point (10 min)
```bash
cat docs/requirements/00_READ_ME_FIRST.md
```

### Step 3: Choose Your Path

**If you want a quick overview:**
```bash
cat docs/requirements/START_HERE_MCPROXY.txt
```

**If you want to start debugging immediately:**
```bash
cat docs/requirements/MCPROXY_SESSION_CONTEXT.md
# Follow Phase 1 (Investigation)
```

**If you want the complete technical details:**
```bash
cat docs/requirements/MCPROXY_DEBUG_GUIDE.md
```

---

## ⏱️ Time Breakdown

| Activity | Time |
|----------|------|
| Read all documentation | 45-60 min |
| Phase 1: Investigate | 30 min |
| Phase 2: Identify root cause | 30 min |
| Phase 3: Implement fix | 1 hour |
| Phase 4: Test & verify | 30 min |
| **Total** | **2.5-3.5 hours** |

---

## 🎯 Problem Summary

**Issue:** MCProxy HTTP gateway cannot forward tool calls to jesse-mcp subprocess

**Symptom:** Tool calls return empty error messages
```json
{"error": {"message": "Tool call failed: "}}
```

**Root Cause:** TBD (4 hypotheses documented in MCPROXY_DEBUG_GUIDE.md)

**Solution:** 2-3 hour debugging and fix process (fully documented)

---

## ✅ Success Criteria

When fixed, all these will be true:
- ✅ Tool calls return proper JSON responses
- ✅ `jesse_status` tool returns data
- ✅ `backtest` tool returns real metrics
- ✅ `_mock_data: false` in results
- ✅ Backtest takes 2-3 minutes (async polling works)

---

## 📝 Session Context

**Jesse-MCP (Completed ✅)**
- Fixed polling timeout: 60s → 300s
- Added 3 tests, all 81 tests pass
- Code deployed to server2

**MCProxy (Pending ❌)**
- Debug subprocess communication
- Implement fix (4 hypotheses documented)
- Test with real Jesse API

---

## 🔧 Files to Edit

**Primary:** `/srv/containers/mcproxy/server.py`
- Start by adding debug logging to `handle_tools_call()` function

**Secondary:** `/srv/containers/mcproxy/main.py`
- Verify environment variable passing

---

## 🎓 Document Purposes

| Document | Purpose | Best For |
|----------|---------|----------|
| MCPROXY_INTEGRATION_STATUS.md | Quick status | Getting oriented |
| 00_READ_ME_FIRST.md | Complete entry point | First-time readers |
| START_HERE_MCPROXY.txt | Quick overview | Terminal viewing |
| MCPROXY_SESSION_CONTEXT.md | Quick reference | While debugging |
| MCPROXY_DEBUG_GUIDE.md | Technical details | Implementation |
| WORK_SUMMARY.md | Full context | Understanding background |
| INDEX.md | Doc index | Finding specific info |

---

## 🔍 Quick Decision Tree

```
Need to debug MCProxy?
├─ Yes, quickly
│  └─ Read: MCPROXY_SESSION_CONTEXT.md
│     Start: Phase 1 (Investigation)
├─ Yes, thoroughly
│  ├─ Read: 00_READ_ME_FIRST.md
│  ├─ Then: MCPROXY_SESSION_CONTEXT.md
│  └─ Then: MCPROXY_DEBUG_GUIDE.md
└─ Just want status
   └─ Read: MCPROXY_INTEGRATION_STATUS.md
```

---

## 💡 Pro Tips

1. **Read 00_READ_ME_FIRST.md first** - It has the clearest explanation
2. **Keep MCPROXY_SESSION_CONTEXT.md open** - You'll reference it constantly
3. **Follow the 4-phase approach** - Don't skip any phase
4. **Use the quick commands** - They're provided for a reason
5. **Check success criteria** - You'll know when it's fixed

---

## 📞 Questions?

All documentation is self-contained and comprehensive. If you're stuck:

1. Check the relevant section in MCPROXY_DEBUG_GUIDE.md
2. Review the hypotheses section
3. Follow the investigation steps exactly
4. Check the troubleshooting section

---

## 🎬 Next Action

**→ Open and read:** `docs/requirements/00_READ_ME_FIRST.md`

**Estimated time:** 5-10 minutes

**Then:** Follow the 4-phase approach documented there

---

**Status:** ✅ Documentation complete and organized
**Location:** `~/source/mcproxy/docs/requirements/`
**Backup:** `/tmp/` (original files still available)
**Ready for:** Next debugging session
