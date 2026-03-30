# Jesse MCP Issues via MCProxy

> **Status**: ✅ RESOLVED (v4.3+)  
> **MCProxy** is a lightweight MCP gateway that aggregates multiple stdio MCP servers through namespaced SSE endpoints.

**Update (v4.3)**: Both timeout and serialization issues documented below have been resolved in mcproxy v4.3+.

## Resolution Summary

| Issue | Resolution | Status |
|------|------------|--------|
| Timeout on long-running tools | Per-server `tool_timeout` and per-tool `tool_timeouts` config | ✅ Fixed |
| Circular reference on complex dicts | `_sanitize_for_json()` validation before serialization | ✅ Fixed |

## Environment

| Component | Host | Address |
|-----------|------|---------|
| mcproxy | server2 (192.168.50.71) | port 12010 |
| jesse (REST API) | server2 | port 9100 |
| jesse-mcp | server2 | via mcproxy SSE |
| maxitrader | workstation | calls mcproxy over LAN |

## Working: Direct MCP Server (stdio)

When `jesse-mcp` is used directly via stdio (not through mcproxy), all tools work correctly:

```
# opencode.json configuration
{
  "mcpServers": {
    "jesse": {
      "command": "ssh",
      "args": ["server2-auto", "cd /srv/containers/jesse-mcp && .venv/bin/python -m jesse_mcp"],
      "timeout": 600000
    }
  }
}
```

**Verified working tools via direct stdio:**

- `jesse_status()` - Returns version, strategy count, exchange list
- `strategy_list()` - Returns all 11 strategies
- `backtest()` - *Intermittent* - Sometimes completes, often times out
- `get_exchanges()` - Returns exchange configs
- `cache_stats()` - Returns cache hit/miss ratios
- `candles_import()` - Returns 422 error (Jesse API issue, not MCP)

The key difference: direct stdio maintains a persistent connection with no serialization overhead. Tools that return quickly (< 10s) work reliably. Long-running tools like `backtest()` are unreliable.

## Broken: jesse-mcp via mcproxy

When the same `jesse-mcp` server is accessed through mcproxy's SSE/HTTP bridge, several categories of issues appear.

### Issue 1: "No response from server" on Long-Running Tools

**Symptom:** Calling `backtest()` through mcproxy returns:
```
Error: No response from server 'jesse'
```

**Root cause:** mcproxy has a default timeout that is too short for backtest operations. Jesse backtests take 30-300 seconds depending on strategy complexity and date range. The mcproxy SSE connection times out before the backtest completes.

**Evidence:**
- `jesse_status()` works fine through mcproxy (returns in < 1s)
- `strategy_list()` works fine through mcproxy (returns in < 2s)
- `backtest()` consistently fails through mcproxy regardless of date range or strategy
- The same `backtest()` call works via direct stdio ~50% of the time

**Workaround:** Call Jesse REST API directly via HTTP, bypassing mcproxy entirely:
```python
import requests, uuid

session = requests.Session()
resp = session.post(f"{JESSE_URL}/auth/login", json={"password": "..."}, timeout=10)
token = resp.json()["auth_token"]
session.headers["Authorization"] = token

payload = {
    "id": str(uuid.uuid4()),
    "exchange": "Binance Spot",
    "routes": [{"strategy": "SMACrossover", "symbol": "BTC-USDT", "timeframe": "1h"}],
    "data_routes": [],
    "config": {
        "warm_up_candles": 240,
        "exchanges": {"Binance Spot": {"name": "Binance Spot", "balance": 10000, "fee": 0.001}},
    },
    "start_date": "2025-11-28",
    "finish_date": "2026-02-26",
    "debug_mode": False, "export_csv": False, "export_json": False,
    "export_chart": False, "export_tradingview": False, "fast_mode": True, "benchmark": False,
}

resp = session.post(f"{JESSE_URL}/backtest", json=payload, timeout=15)

# Poll for completion
for attempt in range(60):
    time.sleep(5)
    resp = session.post(f"{JESSE_URL}/backtest/sessions/{backtest_id}", json={}, timeout=15)
    data = resp.json()
    session_data = data.get("session") or data
    if session_data.get("status") in ("finished", "stopped", "cancelled", "failed"):
        break
```

### Issue 2: "Circular reference detected" on Monte Carlo

**Symptom:** Calling `monte_carlo()` through mcproxy with a backtest result dict:
```
Circular reference detected
```

**Root cause:** When mcproxy serializes tool arguments to send to the MCP server, it uses `repr()` to build a code string:
```python
# mcproxy's execution pattern
code = f"api.server('jesse').monte_carlo({repr(backtest_result)})"
```

The backtest result dict from the direct API contains values that `repr()` cannot serialize cleanly, or the dict has circular references introduced during Jesse's session object processing.

**Evidence:**
- The error occurs *only* when the backtest result dict is passed as an argument
- Simple dicts (e.g., `{"simulations": 5000}`) work fine
- The sanitized backtest result (only primitive values, no nested objects) also works

**Workaround:** Sanitize the backtest result before passing to MCP tools:
```python
def sanitize_for_mcp(result):
    safe_keys = ["id", "status", "success", "total_return", "sharpe_ratio",
                 "max_drawdown", "win_rate", "total_trades"]
    clean = {}
    for key in safe_keys:
        value = result.get(key)
        if value is not None:
            json.dumps({key: value})  # verify serializable
            clean[key] = value
    return clean
```

### Issue 3: Empty Metrics Causes Mock Data Fallback

**Symptom:** When a backtest completes with 0 trades (e.g., strategy that never triggers), `get_backtest_session_result()` in jesse-mcp returns:
```
Error: Empty metrics
```

This then triggers mock data generation in downstream code, masking the real issue.

**Root cause:** jesse-mcp's `get_backtest_session_result()` expects the `metrics` key in the session to be non-empty. When a strategy produces 0 trades, Jesse still returns a valid session but with empty/null metrics.

**Workaround:** Handle the "stopped" status explicitly in the polling loop:
```python
if status in ("stopped", "cancelled"):
    metrics = session_data.get("metrics", {})
    result = {
        "id": backtest_id,
        "status": status,
        "total_return": metrics.get("net_profit_percentage", 0),
        "total_trades": metrics.get("total", 0),
        "success": True,
    }
    return result
```

### Issue 4: Candle Import Returns 422

**Symptom:** `candles_import()` always returns HTTP 422:
```
422 Client Error: Unprocessable Entity for url: http://localhost:9100/candles/import
```

**Root cause:** This is a Jesse API bug, not an mcproxy issue. The candle import endpoint has been broken in the Jesse version deployed. Since candle data already exists for BTC-USDT (2022-2026) and ETH-USDT (2024-2026), this is non-blocking.

**Workaround:** Made candle import non-fatal (warning only, does not block backtest execution).

## Summary of Tool Reliability

| Tool | Direct stdio | Via mcproxy | Notes |
|------|-------------|-------------|-------|
| `jesse_status()` | Works | Works | Fast, no issues |
| `strategy_list()` | Works | Works | Fast, no issues |
| `get_exchanges()` | Works | Works | Fast, no issues |
| `cache_stats()` | Works | Works | Fast, no issues |
| `candles_import()` | 422 error | 422 error | Jesse API bug |
| `backtest()` | Intermittent | Always fails | Timeout issue |
| `monte_carlo()` | Untested | Circular ref | Serialization issue |
| `analyze_results()` | Untested | Untested | Likely timeout |
| `optimize()` | Untested | Likely fails | Long-running |
| `walk_forward()` | Untested | Likely fails | Very long-running |

## Recommendations

1. **Fast tools via mcproxy.** Use mcproxy for status checks, strategy listing, and metadata queries. These complete in < 2s and work reliably.

2. **Long-running tools via mcproxy with timeouts.** As of v4.3, mcproxy supports per-server and per-tool timeout configuration. Configure the jesse server with appropriate timeouts:
   ```json
   {
     "name": "jesse",
     "timeout": 350,
     "tool_timeout": 600,
     "tool_timeouts": {
       "backtest": 900,
       "optimize": 1200,
       "walk_forward": 1800
     }
   }
   ```

3. **Sanitize complex dicts before MCP.** As of v4.3, mcproxy automatically validates and sanitizes arguments before passing to to MCP servers. If a circular reference or non-serializable type is detected, a helpful error message is returned:
   ```
   ValueError: Circular reference detected at root.metrics. Pass only primitive values (str, int, float, bool, list, dict) to MCP tools.
   ```

4. **Consider a hybrid approach (optional).** The ideal architecture can now use mcproxy for all operations with proper timeout configuration:
   ```
   mcproxy → jesse_status(), strategy_list()     (discovery)
   mcproxy → backtest() with 900s timeout       (execution)
   mcproxy → monte_carlo() with sanitized data     (analysis)
   ```

## v4.3 Fixes (2026-03-29)

### Configurable Timeouts

Added per-server and per-tool timeout configuration in `server_manager.py`:

**Configuration options:**
- `tool_timeout`: Default timeout for all tools on this server (seconds)
- `tool_timeouts`: Per-tool timeout overrides (seconds)

**Example:**
```json
{
  "name": "jesse",
  "timeout": 350,
  "tool_timeout": 600,
  "tool_timeouts": {
    "backtest": 900,
    "optimize": 1200,
    "walk_forward": 1800
  }
}
```

**Timeout selection order:**
1. Per-tool override: `tool_timeouts.get(tool_name)`
2. Server default: `tool_timeout`
3. Global fallback: 350 seconds

### Improved Serialization

Added `_sanitize_for_json()` in `sandbox/runtime.py` to validate arguments before serialization.

**Features:**
- Detects circular references with path information
- Validates dict keys are strings
- Identifies non-serializable types
- Returns clear error messages guiding users

**Error example:**
```
ValueError: Circular reference detected at root.metrics. Pass only primitive values (str, int, float, bool, list, dict) to MCP tools.
```
   mcproxy → jesse_status(), strategy_list()     (discovery)
   direct HTTP → backtest(), session polling       (execution)
   mcproxy → monte_carlo() with sanitized data     (analysis, optional)
   ```
