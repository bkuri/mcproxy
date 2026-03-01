# MCProxy Session Context & Priorities

## What Was Accomplished (Jesse-MCP Side) ✅

1. **Identified Root Cause:** 60-second polling timeout was too short
2. **Implemented Fix:** Increased to 300 seconds (5 minutes)
3. **Added Tests:** 3 new comprehensive timeout tests (all passing)
4. **Verified Code:** 81/81 unit tests pass
5. **Deployed:** Code pushed to GitHub and pulled to server2
6. **Status:** jesse-mcp code is production-ready and working correctly

## What Needs Fixing (MCProxy Side) ❌

The HTTP gateway (mcproxy) cannot communicate with jesse-mcp subprocess properly. When clients call tools via HTTP:
1. Request comes to mcproxy
2. mcproxy tries to forward to jesse-mcp subprocess
3. Something fails and returns empty error message
4. Client gets: `{"error": ""}`

## Quick Diagnosis Flowchart

```
Is /tools endpoint working?
├─ YES → mcproxy can list tools
├─ NO  → mcproxy aggregator is down
        
Can I call tools via curl?
├─ YES, with data → mcproxy+jesse-mcp working (DONE)
├─ NO, empty error → subprocess communication broken
└─ NO, timeout    → subprocess is hanging/slow
```

## SSH Commands for Server2

```bash
# Connect to server2
ssh server2-auto

# Check if jesse-mcp process exists
ps aux | grep jesse-mcp | grep -v grep

# Check if mcproxy is running
ps aux | grep mcproxy | grep -v grep

# Check mcproxy config
cat /srv/containers/mcproxy/config/mcp-servers.json

# View mcproxy systemd logs
journalctl -u mcproxy -n 50 --no-pager

# Test /tools endpoint
curl http://localhost:12010/tools | python3 -m json.tool | head -20

# Test tool call (will fail currently)
curl -X POST http://localhost:12010/message \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"jesse_status","arguments":{}}}'
```

## Files You'll Need to Modify

### Primary Target: `/srv/containers/mcproxy/server.py`

This is the HTTP API handler. Key functions to investigate:

1. `handle_tools_call()` - Main entry point for tool execution
2. `ServerManager.call_tool()` - Communicates with subprocess
3. Environment variable setup for subprocess

### Secondary: `/srv/containers/mcproxy/main.py`

Process startup and subprocess management.

### Reference: `/srv/containers/mcproxy/config/mcp-servers.json`

Verify env vars are configured correctly.

## Recommended Approach

### Phase 1: Gather Information (30 minutes)
- [ ] Check if jesse-mcp subprocess is running
- [ ] Check mcproxy logs for errors
- [ ] Test jesse-mcp with direct stdio MCP messages (bypass mcproxy)
- [ ] Enable debug logging in mcproxy server.py
- [ ] Make a test call and capture the error details

### Phase 2: Identify Failure Point (30 minutes)
Based on error messages, determine:
- Is subprocess crashing?
- Is it a message format issue?
- Is it an environment variable issue?
- Is it a timeout issue?

### Phase 3: Implement Fix (1 hour)
Apply fix based on root cause identified in Phase 2.

### Phase 4: Verify & Test (30 minutes)
- Restart mcproxy
- Run test checklist from MCPROXY_DEBUG_GUIDE.md
- Confirm real backtest data (not mock)

## Expected Outcome

When complete, this curl command should work:

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
  }' | jq '.result.structuredContent | {total_return, _mock_data}'

# Should output:
# {
#   "total_return": 0.0990,
#   "_mock_data": false
# }
```

Note the `"_mock_data": false` - that means real Jesse backtest results, not mock fallback.

## Important Notes

1. **Environment Variables:** Make sure JESSE_URL and JESSE_PASSWORD are passed to subprocess
2. **Timeout:** With our 300s fix, long backtests should work (previously would timeout at 60s)
3. **Test Locally First:** Use the stdio MCP test in Step 2 of the guide to verify subprocess works
4. **Logging:** Adding detailed logging is essential - the current error message is too vague
5. **Don't Edit jesse-mcp Code:** It's working perfectly. Focus only on mcproxy.

## Success Indicators

- [ ] jesse_status tool returns data
- [ ] strategy_list tool returns list
- [ ] backtest tool returns non-empty results
- [ ] `_mock_data` is false (not true)
- [ ] Error messages are descriptive (not empty strings)
- [ ] No timeout errors on reasonable backtests

## Questions to Answer

Before you start, confirm:
1. Is the jesse-mcp process currently running?
   - `ps aux | grep jesse-mcp`
2. Is Jesse API reachable?
   - `curl http://localhost:9100/health`
3. Is mcproxy HTTP server running?
   - `curl http://localhost:12010/tools`
4. Do we have logs for mcproxy?
   - `journalctl -u mcproxy -n 20`

Once you answer these, you'll know exactly where to focus.

## Useful Debugging Tools

```bash
# Monitor logs in real-time
journalctl -u mcproxy -f

# Check process details
ps -ef | grep -E "jesse|mcproxy"

# Network connections
netstat -tlnp | grep -E "12010|9100"

# Test JSON payload
curl -v http://localhost:12010/message -d '{...}'
```

## Files to Reference

- `/tmp/MCPROXY_DEBUG_GUIDE.md` - Detailed troubleshooting guide
- `/srv/containers/mcproxy/` - Main mcproxy directory
- `/srv/mcp-sources/jesse-mcp/` - Jesse MCP source (don't modify)
- `/srv/containers/apps/jesse/` - Jesse service files

## Contact/Escalation

If you get completely stuck:
1. Check that JESSE_URL = `http://localhost:9100` (not 9000 or 8000)
2. Check that Jesse process is actually running (`docker ps` or `ps aux`)
3. Verify env vars are set: `echo $JESSE_PASSWORD`
4. Review the complete MCP spec at https://spec.modelcontextprotocol.io/

## Next Session Handoff

When you're done, provide:
1. Summary of what you found
2. Root cause identified
3. Fixes applied
4. Test results (did it work?)
5. Any remaining issues

Good luck! The debugging guide has all the steps. Start with Phase 1.
