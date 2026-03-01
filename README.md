# MCProxy v2.0 - MCP Gateway with Code Mode

A lightweight MCP gateway that aggregates multiple stdio MCP servers through a single SSE endpoint. **v2.0 introduces Code Mode** — a Forgemax-inspired architecture that reduces context window usage by ~90% (15K → 1K tokens).

**Status**: v2.0.0 - Code Mode Release  
**Python**: 3.11+ | **Memory**: <512MB | **Port**: 12010

---

## Features

### v2.0 Code Mode (New)

- ✅ **Code Mode**: Tool discovery + execution via `search` and `execute` meta-tools
- ✅ **Namespace Isolation**: Group servers by privilege level with inheritance
- ✅ **Sandboxed Execution**: uv subprocess with memory limits, network controls
- ✅ **Event-Driven Manifest**: Reactive refresh on config/health changes
- ✅ **Typed Stubs**: Auto-generate TypeScript/Python stubs for IDE autocomplete

### Core Features

- ✅ **Dual Mode**: HTTP/SSE endpoint OR native MCP server over stdio
- ✅ **Auto-Restart**: Crashed servers auto-recover (max 3 attempts)
- ✅ **Hot-Reload**: Zero-downtime config changes
- ✅ **Environment Interpolation**: `${VAR_NAME}` in JSON configs
- ✅ **Docker/Podman Ready**: Containerized deployment

---

## Quick Start

```bash
# Setup
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp mcp-servers.v2.example.json config/mcp-servers.json

# Start server
python main.py --config config/mcp-servers.json --log
```

### Code Mode: Search for Tools

```bash
curl -X POST http://localhost:12010/message \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"search","arguments":{"query":"github","namespace":"public"}}}'
```

### Code Mode: Execute Code

```bash
curl -X POST http://localhost:12010/message \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"execute","arguments":{"namespace":"public","code":"async def run():\n    return await api.server(\"github\").repos.list(owner=\"octocat\")"}}}'
```

---

## Code Mode Architecture

### The Problem

60+ tools = ~15K tokens of schemas, consuming most context before any work begins.

### The Solution: Meta-Tools

| Tool | Purpose | Context |
|------|---------|---------|
| `search` | Discover tools by query/namespace | ~500 tokens |
| `execute` | Run Python with discovered tools | ~500 tokens |

**Total**: ~1K tokens (~90% reduction)

### Performance Comparison: V1 vs V2

| Metric | V1 (Traditional) | V2 (Code Mode) | Improvement |
|--------|------------------|----------------|-------------|
| **Initial tools/list** | 108KB (~27K tokens) | 1KB (~250 tokens) | **99% smaller** |
| **Tool execution** | 1.9ms | 0.9ms | **2x faster** |
| **Discoverability** | Must dump all schemas | Progressive discovery | **On-demand** |

### Progressive Discovery (V2 Only)

```python
# max_depth=0: Server names only (~300 bytes)
search(query="", max_depth=0)

# max_depth=1: Server + category info (~2KB)
search(query="github", max_depth=1)

# max_depth=2: Tool names (~14KB)
search(query="github", max_depth=2)

# max_depth=3: Full schemas (only for specific tools)
search(query="github.repos.list", max_depth=3)
```

This means the LLM can start with lightweight queries and fetch detailed schemas only when needed - achieving the ~90% context reduction target.

### API Reference

```python
# Get manifest (all available tools)
api.manifest()

# Call tool directly
await api.call_tool("server_name", "tool_name", {"arg": "value"})

# Use typed proxy (if stubs generated)
await api.server("github").repos.list(owner="octocat")
```

---

## Namespace Configuration

### Hierarchy Example

```
system (isolated, requires auth)
   └── supabase, postgres

crypto (extends public)
   └── covalent, coinmarketcap

public (default, no auth)
   └── playwright, wikipedia, github
```

### Config Example

```json
{
  "namespaces": {
    "public": ["playwright", "wikipedia"],
    
    "crypto": {
      "extends": "public",
      "sandbox": { "memory_mb": 512 },
      "rate_limit": { "requests_per_minute": 60 },
      "servers": ["covalent"]
    },
    
    "system": {
      "extends": null,
      "require_auth": true,
      "allowed_origins": ["localhost"],
      "servers": ["supabase"]
    }
  }
}
```

**Inheritance**: `server > namespace > parent_namespace > sandbox_defaults`

---

## Sandbox Security

```json
{
  "sandbox": {
    "timeout_secs": 30,
    "memory_mb": 256,
    "env_isolation": true,
    "network": {
      "enabled": true,
      "allowed_hosts": ["api.github.com"]
    },
    "filesystem": {
      "read_only": ["/etc/ssl"],
      "denied": ["/home", "/root"]
    }
  }
}
```

### Blocked Imports

`subprocess`, `os.system`, `socket` (raw), `pickle`, `marshal`, `importlib`

---

## Configuration Reference

```json
{
  "manifests": {
    "startup_dwell_secs": 2,
    "refresh_event_hooks": {
      "pre_refresh": ["health_check_all"],
      "post_refresh": ["restart_failed"]
    },
    "typed_stub_generation": {
      "enabled": false,
      "output_dir": "./stubs"
    }
  },
  
  "namespaces": { /* see above */ },
  "sandbox": { /* see above */ },
  
  "servers": {
    "github": {
      "command": "docker",
      "args": ["run", "--rm", "-i", "-e", "GITHUB_TOKEN", "ghcr.io/github/github-mcp-server"],
      "env": { "GITHUB_TOKEN": "${GITHUB_TOKEN}" },
      "namespace": "public",
      "enabled": true
    }
  }
}
```

---

## Migration from v1.x

### Breaking Changes

| v1.x | v2.0 |
|------|------|
| `servers` array | `servers` object (keyed by name) |
| Flat tool list | Namespaced tools |
| Direct tool calls | `search` + `execute` meta-tools |

### Migration Steps

```json
// v1.x
"servers": [{ "name": "github", ... }]

// v2.0
"servers": { "github": { ... } }
```

v1.x configs work with automatic migration. New sections are optional.

---

## CLI Options

```bash
python main.py [OPTIONS]

  --stdio              Native MCP server over stdio
  --log                Log to stdout (debugging)
  --port PORT          Port (default: 12010)
  --config PATH        Config file path
  --no-reload          Disable hot-reload
```

---

## Deployment

```bash
# Podman Compose
cp .env.example .env
cp mcp-servers.v2.example.json config/mcp-servers.json
podman-compose up -d

# Quadlet (Systemd)
sudo cp mcproxy.container /etc/containers/systemd/
sudo systemctl enable --now mcproxy.service
```

---

## Troubleshooting

```bash
# Test search
curl -X POST http://localhost:12010/message \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"search","arguments":{"query":"test"}}}'

# Check sandbox logs
journalctl -u mcproxy | grep -i "sandbox\|blocked"

# Validate config
python -m json.tool config/mcp-servers.json
```

---

## Architecture

```
mcp-servers.v2.json
        │
        ▼
  [Manifests] → Event hooks, TTL, stubs
        │
        ▼
 [Namespaces] → Inheritance, access control
        │
        ▼
   [Sandbox] → Resource limits
        │
        ▼
 [Code Mode] → search + execute
        │
        ▼
[Server Manager] → uv subprocesses
```

---

## Dependencies

```
fastapi==0.104.0
uvicorn==0.24.0
python-json-logger==2.0.7
```

---

## Support

**GitHub**: https://github.com/bkuri/mcproxy  
**Issues**: https://github.com/bkuri/mcproxy/issues

---

## Acknowledgments

MCProxy v2.0's Code Mode architecture was inspired by **[Forgemax](https://github.com/postrv/forgemax)** — a Rust-based MCP gateway that introduced the concept of collapsing N servers × M tools into just 2 meta-tools (`search` + `execute`) for massive context reduction.

Key concepts adopted from Forgemax:
- Progressive tool discovery via searchable capability manifest
- Sandboxed code execution for tool composition
- Context window reduction (15K → 1K tokens)
