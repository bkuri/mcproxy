# MCProxy - Agent Guidelines

> **Status**: v4.2 - Security Hardening  
> **MCProxy** is a lightweight MCP gateway that aggregates multiple stdio MCP servers through namespaced SSE endpoints.

## Quick Reference

### IMPORTANT: MCP Protocol

MCProxy uses MCP (JSON-RPC 2.0), **not REST**:

| Endpoint | Type | Purpose |
|----------|------|---------|
| `GET /health` | REST | Health check |
| `POST /sse` | MCP | Main endpoint |
| `POST /sse/{namespace}` | MCP | Namespaced endpoint |

### Code Mode

Single tool: `mcproxy(action='execute'|'search'|'inspect', ...)`

```python
# Execute
mcproxy(action='execute', code='api.server("wikipedia").search(query="python")', namespace='dev')

# Search
mcproxy(action='search', query='wikipedia')

# Inspect
mcproxy(action='inspect', server='wikipedia', tool='search')
```

### Authentication

```bash
# Get token
curl -X POST http://192.168.50.71:12010/oauth/token \
  -d "grant_type=client_credentials" \
  -d "client_id=YOUR_ID" \
  -d "client_secret=YOUR_SECRET"

# Use token
curl -X POST http://192.168.50.71:12010/sse \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Namespace: dev" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## Code Mode API

### Actions

| Action | Purpose |
|--------|---------|
| `execute` | Run Python code with tool access |
| `search` | Find tools by query |
| `inspect` | Get tool schemas |

### Usage

```python
# Execute code
result = mcproxy(action='execute', code='...', namespace='dev')

# Search tools
results = mcproxy(action='search', query='wikipedia')

# Inspect schema
schema = mcproxy(action='inspect', server='wikipedia', tool='search')
```

### Parallel Execution

```python
results = parallel([
    lambda: api.server('s1').tool1(),
    lambda: api.server('s2').tool2(),
])
```

### Response Types

Auto-unwrapped - no need for `result['content'][0]['text']`:
- **String**: Direct file contents, messages
- **List**: Direct iteration
- **Dict**: Direct key access

## Authentication (v4.1)

JWT-based authentication with encrypted credential storage:

```
Agent → JWT Token → MCProxy → Credential → Tool Execution
         (scopes)             (injected)
```

### Config

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

### Agent Management

```python
from auth import AgentRegistry
registry = AgentRegistry("data/agents.db")

# Register
creds = registry.register(name="agent", allowed_scopes=["scope"], namespace="dev")

# Update
registry.update_scopes("agent_id", ["scope1", "scope2"])

# Rotate
new_creds = registry.rotate_secret("agent_id")
```

## Security Hardening (v4.2)

Defense-in-depth with blocklist validation and container hardening.

### Blocklist

Servers are validated at startup:

- **Blocked**: Critical risk servers cannot start
- **Risky**: Elevated privilege servers require acknowledgment
- **Unclassified**: Warnings logged

### Configuration

```json
{
  "security": {
    "blocklist_enabled": true,
    "blocklist_url": "https://raw.githubusercontent.com/mcproxy/blocklist/main/blocklist.json",
    "blocklist_sync_interval": 3600,
    "allow_risky_servers": false,
    "risky_server_acknowledgments": {
      "playwright": "Required for browser automation"
    }
  }
}
```

### For Agents

- **Shell access disabled** - No sh/bash/python in sandbox
- **Blocklist enforced** - MCProxy exits if blocked servers detected
- **Credentials isolated** - API keys injected at execution, never exposed
- **Namespace isolation** - Access limited to assigned namespace

## Namespaces

### Configuration

```json
{
  "namespaces": {
    "dev": {"servers": ["wikipedia", "llms_txt"], "isolated": false},
    "home": {"servers": ["home_assistant"], "isolated": true}
  },
  "groups": {
    "full": {"namespaces": ["dev", "docs"]}
  }
}
```

### Access

| Endpoint | Servers |
|----------|---------|
| `/sse` | Unnamespaced + non-isolated |
| `/sse/dev` | dev namespace only |
| `/sse/home` | home (isolated) only |

Use `X-Namespace: dev` header to override endpoint.

## Project Structure

```
mcproxy/
├── main.py              # Entry point
├── server.py            # FastAPI SSE
├── server_manager.py    # MCP server management
├── config_watcher.py    # Config loading
├── blocklist.py         # Security blocklist
├── auth/                # Authentication
│   ├── credential_store.py
│   ├── jwt_keys.py
│   └── agent_registry.py
└── mcproxy.json         # Configuration
```

## Key Constraints

- **Python 3.11+** required
- **Port 12010** (hardcoded)
- **Memory**: <100MB target
- **Reload**: 1-2 seconds acceptable

## Issue Tracking

Uses **bd (beads)**:

```bash
bd ready              # Find unblocked work
bd create "Title"     # Create issue
bd close <id>        # Complete work
bd dolt push         # Push to remote
```

## References

- [docs/EXAMPLES.md](docs/EXAMPLES.md) - Detailed examples
- [docs/HISTORY.md](docs/HISTORY.md) - Archived features
- [ROADMAP.md](ROADMAP.md) - Future plans
- [README.md](README.md) - Overview
