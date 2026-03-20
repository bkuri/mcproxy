# MCProxy - Agent Guidelines

> **Status**: v3.1 - Single Tool API
> 
> MCProxy is a lightweight MCP gateway that aggregates multiple stdio MCP servers through namespaced SSE endpoints.

## ⚠️ IMPORTANT: MCProxy uses MCP Protocol, not REST

**Do NOT try to use REST endpoints** - MCProxy implements the MCP (Model Context Protocol) over SSE using JSON-RPC.

### ❌ Wrong Approach
```bash
curl http://192.168.50.71:12010/tools  # 404 Not Found
curl http://192.168.50.71:12010/execute  # 404 Not Found
```

### ✅ Correct Approach
```bash
# Health check (this IS a REST endpoint - works!)
curl http://192.168.50.71:12010/health

# List tools (MCP protocol)
curl -X POST http://192.168.50.71:12010/sse \
  -H "Content-Type: application/json" \
  -H "X-Namespace: dev" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# Execute code (MCP protocol)
curl -X POST http://192.168.50.71:12010/sse \
  -H "Content-Type: application/json" \
  -H "X-Namespace: dev" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "execute",
      "arguments": {"code": "1+2+3"}
    }
  }'
```

### Available Endpoints

| Endpoint | Type | Purpose |
|----------|------|---------|
| `GET /health` | REST | Health check with protocol info |
| `POST /sse` | MCP (JSON-RPC) | Main MCP protocol endpoint |
| `POST /sse/{namespace}` | MCP (JSON-RPC) | Namespaced MCP endpoint |

### Single Tool API

Only **1 meta-tool** is exposed via MCP:

**mcproxy** - Unified interface with actions: execute, search, inspect

All tools are accessed via `execute` action:

```python
# Inside execute code
mcproxy(action='execute', code='api.server("wikipedia").search(query="topic")')
```

### Quick Protocol Reference

**MCP Protocol uses JSON-RPC 2.0:**

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list" | "tools/call",
  "params": {...}
}
```

**For more details:**
- Check health endpoint: `curl http://192.168.50.71:12010/health`
- See `/tmp/MCPROXY_MCP_ACCESS_GUIDE.md` for detailed examples

## Build & Test Commands

```bash
# Setup with uv (recommended)
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"

# Setup with pip (traditional)
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run development server
python main.py --log

# Run with custom config
python main.py --config mcproxy.json --port 12010

# Run as native MCP server (stdio mode)
python main.py --stdio --config mcproxy.json

# Test SSE endpoint (default namespace)
curl -N http://localhost:12010/sse

# Test namespaced SSE endpoint
curl -N http://localhost:12010/sse/dev

# Test tools list
curl -X POST http://localhost:12010/sse \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# Test with namespace header
curl -X POST http://localhost:12010/sse \
  -H "Content-Type: application/json" \
  -H "X-Namespace: dev" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'

# Validate JSON config
python -m json.tool mcproxy.json

# Build container
docker build -t localhost/mcproxy:latest .

# Run container locally
docker run -d --name mcproxy \
  -p 12010:12010 \
  -v $(pwd)/config:/app/config:Z \
  -v $(pwd)/.env:/app/.env:ro \
  localhost/mcproxy:latest

# Deploy (on server2)
# Initial setup only - deployment is now automatic via git pre-push hook
sudo cp mcproxy.container /etc/containers/systemd/
sudo systemctl daemon-reload
sudo systemctl start mcproxy.service
sudo journalctl -u mcproxy.service -f

# After initial setup, just push to main - auto-deploys to server2!
# The pre-push hook automatically:
# 1. Detects pushes to origin/main
# 2. Waits for push to complete
# 3. SSHs to server2, pulls changes, restarts service
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

### Internal Tool Naming (v1 only)
```python
# Legacy v1 format: {server_name}__{tool_name}
# NOTE: v2 API uses api.server("name").tool() instead
tool_name = f"{server_name}__{original_tool_name}"
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
# 2. Test SSE: curl -N http://localhost:12010/sse
# 3. Connect Claude Desktop to http://localhost:12010/sse
# 4. Execute tools, verify aggregation
```

## Key Constraints

- **Python 3.11+** required
- **Port 12010** (hardcoded in spec)
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
--port PORT        # Port to listen on (default: 12010)
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

## Code Mode API

Single tool: `mcproxy(action='execute'|'search'|'inspect', ...)`

### Actions

**execute** - Run Python code with tool access
- Parameters: `code` (required), `namespace` (required), `timeout_secs` (optional)
- Response: `{status, result, stdout, traceback, execution_time_ms}`
  - `result`: Tool return value (auto-unwrapped, directly usable)
  - `stdout`: Captured print() output
  - `traceback`: Error details if execution failed
- Tools: `api.server('name').tool(args)`
- Results auto-unwrapped (string/list/dict)
- stdout captures print() output
- Example: `data = api.server("wikipedia").search(...)` returns string directly

**search** - Find tools by query
- Parameters: `query`, `namespace`, `max_depth`
- Empty query returns server list

**inspect** - Get tool schemas
- Parameters: `server` (required), `tool` (optional)
- Returns schema without executing

### Usage

```python
# Execute (most common)
mcproxy(action='execute', code='api.server("wikipedia").search(query="python")', namespace='dev')

# Read-modify-write pattern
mcproxy(action='execute', code="""
  data = api.server('s').read_file(path='f.yaml')
  config = json.loads(data)
  config['key'] = 'value'
  api.server('s').write_file(path='f.yaml', content=json.dumps(config))
""", namespace='dev')

# Search for tools
mcproxy(action='search', query='wikipedia')

# Inspect tool schema
mcproxy(action='inspect', server='wikipedia', tool='search')
```

### Response Types

Auto-unwrapped from MCP protocol:
- **String**: File contents, error messages
- **List**: Files, entities, collections
- **Dict**: Structured data

No need for: `result['content'][0]['text']` or manual JSON parsing.

### Parallel Execution

```python
results = parallel([
    lambda: api.server('s1').tool1(),
    lambda: api.server('s2').tool2(),
])
# Returns: [{"status": "fulfilled", "result": ...}, ...]
```

### Namespaces

Use `X-Namespace: dev` header or `/sse/dev` endpoint to control server access.

## Authentication (v4.1)

MCProxy v4.1 includes JWT-based authentication for agents with encrypted credential storage.

### Architecture

```
Agent → JWT Token → MCProxy → Credential → Tool Execution
         (scopes)             (injected)
```

Agents never see actual API keys. Credentials are:
- Encrypted at rest (AES-256-GCM)
- Injected at execution time
- Scoped by permission level

### Quick Setup

**1. Set encryption key:**
```bash
export MCPROXY_CREDENTIAL_KEY=$(python -c "import os; print(os.urandom(32).hex())")
```

**2. Enable in config:**
```json
{
  "auth": {
    "enabled": true,
    "jwt": {"default_ttl": 1, "min_ttl": 5, "max_ttl": 24},
    "credentials_db": "data/credentials.db",
    "agents_db": "data/agents.db",
    "keys_dir": "keys/"
  }
}
```

**3. Register agent:**
```python
from auth import AgentRegistry
registry = AgentRegistry("data/agents.db")
creds = registry.register(
    name="dev-assistant",
    allowed_scopes=["github:read", "perplexity:search"],
    namespace="dev"
)
# Returns: {"agent_id": "...", "client_id": "...", "client_secret": "..."}
```

**4. Store credentials:**
```python
from auth import CredentialStore
store = CredentialStore("data/credentials.db")
store.store(service="github", value="ghp_xxx", permission="read")
store.store(service="perplexity", value="pplx-xxx")
```

**5. Configure scope mapping:**
```json
{
  "credentials": {
    "github": {"keys": {"default": "github_read", "write": "github_write"}}
  },
  "scopes": {
    "github:read": "github:default",
    "github:write": "github:write"
  },
  "tool_scopes": {
    "github.repos.list": "github:read",
    "github.repos.create": "github:write"
  }
}
```

### OAuth Token Endpoint

```bash
# Get token
curl -X POST http://localhost:12010/oauth/token \
  -d "grant_type=client_credentials" \
  -d "client_id=agent_xxx" \
  -d "client_secret=yyy" \
  -d "scope=github:read"

# Response: {"access_token": "eyJ...", "token_type": "Bearer", "expires_in": 3600}

# Use token
curl -X POST http://localhost:12010/sse \
  -H "Authorization: Bearer eyJ..." \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{...}}'
```

### Credential Injection

Credentials are injected into tool execution context:

```json
{
  "credentials": {
    "github": {
      "keys": {
        "default": {
          "credential_id": "github_key",
          "inject_as": "GITHUB_TOKEN",
          "inject_type": "env"
        }
      }
    },
    "coinmarketcap": {
      "keys": {
        "default": {
          "credential_id": "cmc_key",
          "inject_as": "X-CMC_PRO_API_KEY",
          "inject_type": "header"
        }
      }
    }
  }
}
```

### Agent Management

```python
from auth import AgentRegistry
registry = AgentRegistry("data/agents.db")

# List agents
registry.list_agents(namespace="dev")

# Update scopes
registry.update_scopes("agent_id", ["github:read", "github:write"])

# Rotate secret (invalidates old credentials immediately)
new_creds = registry.rotate_secret("agent_id")

# Disable/enable
registry.disable("agent_id")
registry.enable("agent_id")
```

### Module Reference

```python
from auth import (
    CredentialStore,    # Encrypted credential storage
    AgentRegistry,      # Agent client management
    JWTIssuer,          # Token issuance
    JWTValidator,       # Token validation
    ScopeResolver,      # Scope → credential mapping
    OAuthHandler,       # OAuth endpoint handler
    AuditLogger,        # Credential access logging
)
```

### Files

```
auth/
├── __init__.py           # Module exports
├── credential_store.py   # AES-256-GCM encrypted storage
├── jwt_keys.py           # RSA key management, JWT issuance
├── agent_registry.py     # Agent client registry
├── scope_resolver.py     # Scope → credential mapping
├── oauth.py              # OAuth handler, auth context
└── audit_logger.py       # Structured audit logging

server/
└── auth_routes.py        # OAuth token endpoint

tests/
└── test_auth.py          # Integration tests
```

## Issue Tracking

This project uses **bd (beads)** for issue tracking.
Run `bd prime` for workflow context, or install hooks (`bd hooks install`) for auto-injection.

**Quick reference:**
- `bd ready` - Find unblocked work
- `bd create "Title" --type task --priority 2` - Create issue
- `bd close <id>` - Complete work
- `bd dolt push` - Push beads to remote

For full workflow details: `bd prime`

## References

- `mcproxy_spec.md` - Technical specification
- `mcproxy_implementation_guide.md` - Implementation phases
- `README.md` - Project overview
