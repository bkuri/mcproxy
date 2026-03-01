# MCProxy - Agent Guidelines

> **Status**: Phase 3 - Namespace-Aware Routing
> 
> MCProxy is a lightweight MCP gateway that aggregates multiple stdio MCP servers through namespaced SSE endpoints.

## Build & Test Commands

```bash
# Setup (one-time)
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run development server
python main.py --log

# Run with custom config
python main.py --config mcproxy.json --port 12009

# Run as native MCP server (stdio mode)
python main.py --stdio --config mcproxy.json

# Test SSE endpoint (default namespace)
curl -N http://localhost:12009/sse

# Test namespaced SSE endpoint
curl -N http://localhost:12009/sse/dev

# Test tools list
curl -X POST http://localhost:12009/sse \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# Test with namespace header
curl -X POST http://localhost:12009/sse \
  -H "Content-Type: application/json" \
  -H "X-Namespace: dev" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# Validate JSON config
python -m json.tool mcproxy.json

# Build container
docker build -t localhost/mcproxy:latest .

# Run container locally
docker run -d --name mcproxy \
  -p 12009:12009 \
  -v $(pwd)/config:/app/config:Z \
  -v $(pwd)/.env:/app/.env:ro \
  localhost/mcproxy:latest

# Deploy (on server2)
sudo cp mcproxy.container /etc/containers/systemd/
sudo systemctl daemon-reload
sudo systemctl start mcproxy.service
sudo journalctl -u mcproxy.service -f
```

## Code Style Guidelines

### Python Style
- **Type hints**: Required on all functions and class methods
- **Docstrings**: Google-style for all public classes/functions
- **Line length**: 88 characters (Black default)
- **Imports**: Sort with isort (stdlib → third-party → local)
- **Naming**:
  - `snake_case` for variables/functions
  - `PascalCase` for classes
  - `SCREAMING_SNAKE_CASE` for constants
  - `__dunder__` for private methods

### Error Handling
- Use specific exceptions, never bare `except:`
- Always log errors with context before raising
- Graceful degradation: one bad server shouldn't break gateway
- Handle subprocess timeouts explicitly

### Async Patterns
- All I/O operations must be async (asyncio)
- Use `async def` for server communication
- Never block the event loop with sync calls
- Proper cleanup in `finally` blocks

### Logging Standards
```python
# Use module-level logger
import logging
logger = logging.getLogger(__name__)

# Log levels:
# DEBUG: Detailed debug info (tool calls, responses)
# INFO: Lifecycle events (server start/stop, config reload)
# WARNING: Recoverable issues (server restart, timeout)
# ERROR: Failures requiring attention
```

### Configuration
- All values from `mcproxy.json` - no hardcoding
- Environment variable interpolation: `${VAR_NAME}`
- Validate JSON schema on load
- Hot-reload without dropping connections
- Namespace-based access control for server isolation

### Tool Naming Convention
```python
# Format: {server_name}__{tool_name}
tool_name = f"{server_name}__{original_tool_name}"

# Example: playwright__navigate_page
```

## Project Structure

```
/srv/containers/mcproxy/
├── main.py              # Entry point, argument parsing
├── server.py            # FastAPI SSE server
├── server_manager.py    # Spawn/manage stdio processes
├── config_watcher.py    # Config loading & validation
├── config_reloader.py   # Hot-reload watcher
├── tool_aggregator.py   # Prefix & aggregate tools
├── api_manifest.py      # Capability registry, namespaces, groups
├── api_sandbox.py       # Sandbox executor with namespace access control
├── logging_config.py    # Syslog + stdout setup
├── requirements.txt     # Python dependencies
├── mcproxy.json         # Server, namespace, and group configuration
├── Dockerfile           # Container image
├── mcproxy.container    # Systemd quadlet file
├── .env                 # Environment variables
└── start.sh             # Startup script
```

## Testing Strategy

```bash
# Unit tests (when added)
pytest tests/

# Manual testing
# 1. Start server: python main.py --log
# 2. Test SSE: curl -N http://localhost:12009/sse
# 3. Connect Claude Desktop to http://localhost:12009/sse
# 4. Execute tools, verify aggregation
```

## Key Constraints

- **Python 3.11+** required
- **Port 12009** (hardcoded in spec)
- **Memory**: <100MB total
- **Reload latency**: 1-2 seconds acceptable
- **No authentication** (internal use only)

## Common Pitfalls

1. Blocking calls → Always use async/await
2. Zombie processes → Proper signal handling + cleanup
3. Tool prefixes → Ensure consistent `{server}__{tool}` format
4. Environment vars → Validate exists before interpolation
5. SSE connections → Keep alive during config reloads

## New Features (Phase 2)

### Hot-Reload Configuration
- **Automatic detection** of mcproxy.json changes
- **Zero-downtime reload** - SSE connections stay alive
- **Smart diffing** - Only changed servers are restarted
- **Validation** - Invalid configs are rejected with error logging

### Auto-Restart Failed Servers
- **Automatic recovery** when servers crash
- **Max 3 restart attempts** to prevent restart loops
- **2-second delay** between restart attempts
- **Health monitoring** before each tool call

### Robust Error Handling
- **Empty line filtering** - Handles npx package download output
- **Multi-line JSON** support for large responses
- **Server-side error detection** - "chunk exceed limit" etc.
- **Graceful degradation** - One bad server doesn't break gateway

### Command-Line Options
```bash
--log              # Log to stdout instead of syslog
--port PORT        # Port to listen on (default: 12009)
--config PATH      # Path to config file
--host HOST        # Host to bind to (default: 0.0.0.0)
--no-reload        # Disable hot-reload
--reload-interval  # Config check interval in seconds (default: 1.0)
```

## Namespace-Aware Routing (Phase 3)

### Configuration Schema

```json
{
  "servers": [...],
  "namespaces": {
    "dev": {
      "servers": ["sequential_thinking", "wikipedia", "llms_txt"],
      "isolated": false,
      "extends": []
    },
    "home": {
      "servers": ["home_assistant"],
      "isolated": true
    }
  },
  "groups": {
    "dev_full": {
      "namespaces": ["dev", "docs"]
    },
    "everything": {
      "namespaces": ["dev", "!home"]
    }
  }
}
```

### Namespace Properties
- **servers**: List of server names accessible in this namespace
- **isolated**: If `true`, namespace requires explicit endpoint (not included in default)
- **extends**: Optional list of parent namespaces to inherit servers from

### Group Properties
- **namespaces**: List of namespace names to merge
- Use `!prefix` (e.g., `!home`) to force-include isolated namespaces (with warning)

### Endpoint Behavior

| Endpoint | Servers Visible |
|----------|-----------------|
| `/sse` | Unnamespaced + all non-isolated namespaces |
| `/sse/dev` | Only servers in `dev` namespace |
| `/sse/home` | Only servers in `home` namespace (isolated) |
| `/sse/dev_full` | Merged servers from group's namespaces |
| `/sse/unknown` | 404 error |

### Header Support
- `X-Namespace` header can override/specify namespace on any request
- Header takes precedence over URL path parameter

## Dependencies

```
fastapi==0.104.0
uvicorn==0.24.0
python-json-logger==2.0.7
```

## References

- `mcproxy_spec.md` - Technical specification
- `mcproxy_implementation_guide.md` - Implementation phases
- `README.md` - Project overview
