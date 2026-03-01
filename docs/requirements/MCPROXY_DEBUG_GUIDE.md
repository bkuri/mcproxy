# MCProxy Integration Issues - Debug & Fix Guide

## Current Status

**jesse-mcp integration with mcproxy is NOT working properly.**

The MCP server (jesse-mcp) starts successfully and initializes all modules correctly, but when mcproxy attempts to forward tool calls to jesse-mcp via HTTP, it returns generic error responses:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32000,
    "message": "Tool call failed: "
  }
}
```

## Problem Symptoms

### What Works ✅
- jesse-mcp process starts without errors
- All 81 unit tests pass locally
- Jesse framework integration successful (REST API connection confirmed)
- All 61 MCP tools register successfully
- `/tools` endpoint returns full tool list with correct definitions

### What Doesn't Work ❌
- Tool execution via HTTP returns empty error message
- Even simple tools like `jesse__jesse_status` fail
- The error message is blank - no debugging info provided
- No stderr/logging output from tool execution in mcproxy logs

## Architecture

```
User (curl/client)
    ↓
mcproxy HTTP server (port 12010)
    ├─ Configuration: /srv/containers/mcproxy/config/mcp-servers.json
    ├─ Code: /srv/containers/mcproxy/server.py
    └─ Main: /srv/containers/mcproxy/main.py
    ↓
jesse-mcp (stdio MCP server)
    ├─ Location: /srv/mcp-sources/jesse-mcp
    ├─ Entry: /srv/containers/mcproxy/venv/bin/jesse-mcp
    └─ Running as child process (PID: varies)
```

## Key Files & Locations

### Server2 Configuration
```
/srv/containers/mcproxy/config/mcp-servers.json    # mcproxy server config
/srv/containers/mcproxy/main.py                     # mcproxy startup
/srv/containers/mcproxy/server.py                   # mcproxy HTTP API
/srv/containers/mcproxy/venv/bin/jesse-mcp          # jesse-mcp executable
/srv/mcp-sources/jesse-mcp/                         # source code (git repo)
```

### Jesse Service
```
Jesse API: http://localhost:9100
Jesse container: /srv/containers/apps/jesse/
Jesse .env: /srv/containers/apps/jesse/.env
```

### Logs
```
/tmp/jesse-mcp-fresh.log        # Recent jesse-mcp startup log
journalctl -u mcproxy -n 50     # mcproxy systemd logs (service is failing)
ps aux | grep jesse-mcp         # Check if process running
```

## Root Cause Analysis

### Hypothesis 1: Tool Handler Error (Most Likely)
The mcproxy `server.py` has a `handle_tools_call()` function that catches all exceptions:

```python
async def handle_tools_call(msg_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        # ... tool execution code ...
    except Exception as e:
        logger.error(f"Tool call error: {e}")  # Logs error
        return {"success": False, "error": str(e)}  # Returns error to client
```

**The problem:** If `str(e)` is empty (exception message is blank), the client sees `"error": ""`.

### Hypothesis 2: IPC Communication Issue
The jesse-mcp process might be:
- Crashing on tool invocation
- Hanging/deadlocking
- Not reading input properly from mcproxy
- Not writing output properly to mcproxy

### Hypothesis 3: Environment Variables Not Passed
Tool execution might fail because:
- `JESSE_URL` or `JESSE_PASSWORD` not in subprocess environment
- Different environment when executed by mcproxy vs manually

## Investigation Steps

### Step 1: Check mcproxy Logs
```bash
# On server2
journalctl -u mcproxy -n 100 --no-pager

# Or if systemd service is failing, check manual process:
tail -100 /tmp/jesse-mcp-fresh.log
```

**What to look for:**
- Any error messages from jesse-mcp subprocess
- Communication errors between mcproxy and jesse-mcp
- Tool invocation failures
- Environment variable issues

### Step 2: Test jesse-mcp Directly (Bypass mcproxy)
```bash
# On server2, test stdio MCP communication directly
python3 << 'SCRIPT'
import json
import subprocess
import time

# Start jesse-mcp process
proc = subprocess.Popen(
    ["/srv/containers/mcproxy/venv/bin/jesse-mcp"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    env={
        "JESSE_URL": "http://localhost:9100",
        "JESSE_PASSWORD": "jessesecurepassword2025",
        "PATH": "/usr/bin:/usr/local/bin:/bin"
    }
)

# Send initialize request
init_msg = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {}
}

proc.stdin.write(json.dumps(init_msg) + "\n")
proc.stdin.flush()

# Read response
time.sleep(1)
response = proc.stdout.readline()
print("Initialize response:", response)

# Send tools/call request
call_msg = {
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
        "name": "jesse_status",
        "arguments": {}
    }
}

proc.stdin.write(json.dumps(call_msg) + "\n")
proc.stdin.flush()

# Read response
time.sleep(2)
response = proc.stdout.readline()
print("Tool call response:", response[:200])

proc.terminate()
SCRIPT
```

### Step 3: Enable Debug Logging
In mcproxy, add verbose logging to understand where the failure occurs:

**File:** `/srv/containers/mcproxy/server.py`

Find this function:
```python
async def handle_tools_call(msg_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
```

Add detailed logging:
```python
async def handle_tools_call(msg_id: Any, params: Dict[str, Any]) -> Dict[str, Any]:
    try:
        tool_name = params.get("name")
        logger.info(f"[TOOL_CALL] Starting: {tool_name}")
        
        # Get tool
        available_tools = server_manager.list_tools()
        logger.info(f"[TOOL_CALL] Available tools: {len(available_tools)}")
        
        # Find tool
        tool = next((t for t in available_tools if t.name == tool_name), None)
        if not tool:
            logger.error(f"[TOOL_CALL] Tool not found: {tool_name}")
            return {"success": False, "error": f"Tool not found: {tool_name}"}
        
        logger.info(f"[TOOL_CALL] Found tool, calling...")
        
        # Call tool
        result = await server_manager.call_tool(tool_name, params.get("arguments", {}))
        logger.info(f"[TOOL_CALL] Success: {tool_name}")
        return result
        
    except Exception as e:
        import traceback
        logger.error(f"[TOOL_CALL_ERROR] {tool_name}: {str(e)}")
        logger.error(f"[TOOL_CALL_TRACEBACK] {traceback.format_exc()}")
        return {"success": False, "error": str(e)}
```

### Step 4: Check Tool Server Manager
The `ServerManager` in mcproxy handles subprocess communication. Issues might be:

1. **Subprocess not responding** - jesse-mcp crashed or hung
2. **Message format issue** - mcproxy sends malformed MCP messages
3. **Timeout** - tool takes too long to respond
4. **Environment issue** - subprocess doesn't have required env vars

**Check in server.py:**
```python
class ServerManager:
    async def call_tool(self, tool_name: str, arguments: dict):
        # This method communicates with jesse-mcp subprocess
        # Potential issues:
        # - Does it pass JESSE_URL and JESSE_PASSWORD?
        # - Does it handle subprocess timeouts?
        # - Does it handle stderr properly?
```

### Step 5: Verify Subprocess Communication
Check if mcproxy correctly spawns jesse-mcp with environment variables:

```bash
# On server2, check the mcproxy config
cat /srv/containers/mcproxy/config/mcp-servers.json | python3 -m json.tool

# Should show:
{
    "servers": [
        {
            "name": "jesse",
            "command": "/srv/containers/mcproxy/venv/bin/jesse-mcp",
            "env": {
                "JESSE_URL": "http://localhost:9100",
                "JESSE_PASSWORD": "jessesecurepassword2025"
            }
        }
    ]
}

# Verify these env vars exist
echo $JESSE_URL
echo $JESSE_PASSWORD
```

## Fixes to Try (In Order of Likelihood)

### Fix 1: Add Error Message Logging to mcproxy
**Priority:** HIGH
**Effort:** 5 minutes

Edit `/srv/containers/mcproxy/server.py` and add detailed error logging (see Step 3 above).

Then restart mcproxy:
```bash
systemctl restart mcproxy
# OR if using manual process:
pkill -f mcproxy
/srv/containers/mcproxy/main.py --log --port 12010 --config /srv/containers/mcproxy/config/mcp-servers.json
```

Test and check logs:
```bash
journalctl -u mcproxy -n 50 -f  # Follow logs
# Make a test request
curl -X POST http://localhost:12010/message \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"jesse_status","arguments":{}}}'
```

### Fix 2: Verify Environment Variables Passed to Subprocess
**Priority:** HIGH
**Effort:** 10 minutes

Check if mcproxy's ServerManager correctly passes env vars to subprocess.

Look for where it spawns jesse-mcp:
```python
# Likely in ServerManager or HotReloadServerManager
process = subprocess.Popen(
    [command] + args,
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    env={...}  # <- Check this
)
```

Ensure it includes:
```python
env = os.environ.copy()  # Start with current env
env.update(server_config.get("env", {}))  # Add config env vars
# Then use this env in Popen
```

### Fix 3: Check for Subprocess Crashes
**Priority:** MEDIUM
**Effort:** 10 minutes

Add subprocess health check to mcproxy:

```python
async def call_tool(self, tool_name: str, arguments: dict):
    # Before calling tool, check if subprocess is alive
    if not self.process.is_running():
        logger.error(f"Subprocess crashed for {tool_name}")
        # Try to restart it
        self.restart_subprocess()
    
    # Call tool...
```

Check jesse-mcp stderr for crashes:
```bash
# If mcproxy has subprocess, check its stderr
# Add to mcproxy: logger.error(f"jesse-mcp stderr: {proc.stderr.read()}")
```

### Fix 4: Handle Tool Call Timeouts
**Priority:** MEDIUM
**Effort:** 15 minutes

The `call_tool` method might be timing out. Add timeout handling:

```python
async def call_tool(self, tool_name: str, arguments: dict, timeout: int = 350):
    try:
        result = await asyncio.wait_for(
            self._call_tool_internal(tool_name, arguments),
            timeout=timeout
        )
        return result
    except asyncio.TimeoutError:
        logger.error(f"Tool call timed out after {timeout}s: {tool_name}")
        return {"success": False, "error": f"Tool call timed out after {timeout}s"}
```

## Testing Checklist

Once fixes are applied:

```bash
# Test 1: Simple tool (no dependencies)
curl -X POST http://localhost:12010/message \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "jesse_status",
      "arguments": {}
    }
  }'

# Expected: Successful response with Jesse status

# Test 2: Strategy list tool
curl -X POST http://localhost:12010/message \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "strategy_list",
      "arguments": {}
    }
  }'

# Expected: List of available strategies

# Test 3: Backtest tool (uses new timeout)
timeout 400 curl -X POST http://localhost:12010/message \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
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
  }'

# Expected: Real backtest results (not mock), with proper metrics
```

## Success Criteria

✅ All tool calls return proper responses (not empty error messages)
✅ `/tools` endpoint still returns tool list
✅ Tool execution completes without timeouts
✅ Backtest tool returns real data (check `_mock_data: false`)
✅ Error messages are descriptive and helpful

## Additional Resources

- **MCProxy source:** `/srv/containers/mcproxy/`
- **Jesse MCP source:** `/srv/mcp-sources/jesse-mcp/`
- **Jesse API docs:** http://localhost:9100/docs (if available)
- **MCP spec:** https://spec.modelcontextprotocol.io/

## Notes

- The jesse-mcp code is working perfectly (81 tests pass)
- The issue is in the mcproxy aggregator layer
- The timeout fix we implemented is good regardless - it allows longer backtests
- Once mcproxy is fixed, backtest results should show real data instead of mock
