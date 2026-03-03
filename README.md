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
- ✅ **Config Hot-Reload**: Add/remove/modify servers without dropping connections
- ✅ **Environment Interpolation**: `${VAR_NAME}` in JSON configs
- ✅ **Docker/Podman Ready**: Containerized deployment

**Note on Hot-Reload**: Only applies to config changes (add/remove servers, namespaces, groups). Code changes (Python files, TypeScript generators, tool descriptions) require server restart. This is standard for Python applications.

---

## Hot Reload Behavior

### What Gets Hot-Reloaded (No Restart)

**Config changes only** (`mcproxy.json`):
- ✅ Add new servers (starts automatically)
- ✅ Remove servers (stops automatically)
- ✅ Modify server config (command, args, env, timeout)
- ✅ Add/remove/modify namespaces (endpoints update immediately)
- ✅ Add/remove/modify groups (namespace merging updates)
- ✅ Zero downtime (SSE connections preserved)

```bash
# Edit config
vim config/mcproxy.json

# Changes detected within 1 second
# Servers start/stop/restart as needed
# Namespaces/groups update dynamically
# No manual restart required
```

**Example - Add New Namespace Without Restart:**
```bash
# 1. Add to config
cat > mcproxy.json << 'EOF'
{
  "servers": [...],
  "namespaces": {
    "home": {
      "servers": ["home_assistant"],
      "isolated": true
    }
  }
}
EOF

# 2. New namespace immediately accessible!
curl http://localhost:12010/sse/home

# No restart needed! 🎉
```

### What Requires Restart

**All code changes**:
- ❌ Python files (`*.py`)
- ❌ TypeScript generator changes
- ❌ Tool descriptions
- ❌ Error messages
- ❌ Sandbox behavior

```bash
# After code changes
sudo systemctl restart mcproxy

# Client will auto-reconnect and re-initialize
# New instructions/descriptions loaded
```

### Why This Limitation?

**Python module loading**: Modules load once at startup. Reloading modules at runtime (`importlib.reload()`) risks:
- State corruption
- Memory leaks
- Unpredictable behavior

**Industry standard**: Most Python applications require restart for code changes:
- Django: `runserver` has auto-reload for dev, but not production
- Flask: Same approach
- FastAPI: Requires restart
- Forgemax (Rust): Requires recompilation for code changes

### Development Workflow

```bash
# 1. Make code changes
vim sandbox/proxy.py

# 2. Restart server (required)
sudo systemctl restart mcproxy

# 3. Client auto-reconnects
# 4. Changes reflected
```

For **operational changes** (add/remove servers in production), hot-reload works seamlessly. For **development changes** (code updates), restart is required.

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

### Agent Setup (Important!)

For best performance, add this to your agent's `CLAUDE.md` or `AGENTS.md`:

```markdown
## MCProxy Tools

Skip search for known tools - call execute directly:
- perplexity_sonar, wikipedia, playwright, think_tool
- sequential_thinking, fear_greed_index, coincap, asset_price

Example:
mcproxy_execute(code='api.server("perplexity_sonar").perplexity_search_web(query="news")')
```

See [docs/AGENT_SETUP.md](docs/AGENT_SETUP.md) for full setup guide.

### Code Mode: Direct Execution (Recommended)

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

**MCP Tools** (exposed to clients like opencode):
- `mcproxy_search` - Discover tools by query (namespace optional)
- `mcproxy_execute` - Run code with tool access (namespace required)
- `mcproxy_sequence` - Read-modify-write in single call (for file/config edits)

**Sandbox API** (inside execute):

**⚠️ IMPORTANT: Use only servers from the MCP instructions**

Server names vary by environment. Check the "Available servers and tools" section in the MCP instructions when you connect. Do NOT guess names like `playwright` or `pure_md`.

```python
# CORRECT: Use servers from the instructions
api.server("wikipedia").search(query="python")

# WRONG: Guessing server names
api.server("playwright").navigate(...)  # Error: may not exist in this environment
```

**For read-modify-write patterns, use `mcproxy_sequence`:**
```python
mcproxy_sequence(
    read={"server": "home_assistant", "tool": "ha_read_file", "args": {"path": "config.yaml"}},
    transform='''
    config = json.loads(data)
    config['new_key'] = 'new_value'
    result = {"path": "config.yaml", "content": json.dumps(config)}
    ''',
    write={"server": "home_assistant", "tool": "ha_write_file"}
)
```

```python
# Optional: Get full tool details
api.manifest()                          # All servers/tools with schemas
api.manifest().servers                  # Server configs with tool definitions

# Call tools via fluent proxy
api.server("github").repos.list(owner="octocat")
api.server("wikipedia").search(query="python")

# Or direct
api.call_tool("github", "repos.list", {"owner": "octocat"})

# Parallel execution
results = await forge.parallel([
    lambda: api.server("github").repos.list(),
    lambda: api.server("wikipedia").search("python"),
])

# Session stash (caching across calls)
stash.put("search_results", data, ttl=3600)
results = stash.get("search_results")
```

Namespaces control access. Use `X-Namespace: dev` header or `/sse/dev` endpoint.

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

### Key Concepts Adopted from Forgemax

**1. TypeScript Definitions in MCP Instructions**

Forgemax serves TypeScript definitions (`forge.d.ts`) in the MCP `initialize` response's `instructions` field, giving LLMs full type awareness without requiring a discovery step. We adapted this by:
- Creating `manifest/typescript_gen.py` to auto-generate TypeScript-style type hints from JSON Schema
- Embedding rich type information in every `initialize` response
- Including parameter types, optional parameters, enums, and return types
- Example: `api.server("perplexity_sonar").perplexity_search_web(query: string, search_recency_filter?: "day"|"week"): Promise<any>`

**2. Eliminating Unnecessary Discovery**

Forgemax's approach showed that with proper upfront documentation, agents can skip the search step entirely for common operations. We implemented:
- Tool descriptions that explicitly mark `search` as **OPTIONAL**
- MCP instructions that list common servers and usage examples
- Direct execution pattern: `api.server("name").tool(args)` without prior discovery
- Result: ~50% latency reduction (1 round-trip instead of 2)

**3. Progressive Discovery Pattern**

Forgemax's layered manifest approach (Layer 0-3 for different detail levels) inspired our progressive discovery:
```python
# Layer 0: Server names only (~50 tokens)
# Layer 1: Server + categories (~200 tokens)  
# Layer 2: Tool names (~500 tokens)
# Layer 3: Full schemas (on-demand)
```

**4. Code Mode Architecture**

Both systems use the same 2-meta-tool pattern:
- `search` - Discover capabilities (optional for known tools)
- `execute` - Run code with tool access

This reduces 76 tools × ~200 tokens each (~15K tokens) → 2 tools × ~500 tokens each (~1K tokens)

### Performance Comparison

| Implementation | Forgemax (Rust) | MCProxy (Python) |
|----------------|-----------------|------------------|
| **Language** | Rust + deno_core | Python 3.11 + uv |
| **Sandbox** | V8 isolate | uv subprocess |
| **Type Definitions** | TypeScript (.d.ts) | TypeScript-style (generated) |
| **Context Reduction** | 96% (76 tools) | 90% (65 tools) |
| **Discovery Step** | Optional | Optional |
| **Instructions Delivery** | MCP `instructions` field | MCP `instructions` field |

### Implementation Differences

**Forgemax:**
- Compiles TypeScript definitions into binary at build time
- Uses V8 isolate (deno_core) for sandboxing
- AST-based code validation before execution
- Rust-native performance

**MCProxy:**
- Generates TypeScript-style hints dynamically from JSON Schema
- Uses uv subprocess for sandboxed Python execution
- Python-native accessibility
- Hot-reload support for live updates

### What We Learned

The key insight from Forgemax is that **type information should be served upfront**, not discovered on-demand. This transforms the agent workflow from:
1. ❌ Search → Discover → Execute (3 steps)

To:
1. ✅ Execute directly (1 step, type info already known)

This pattern is now part of MCProxy v2.0's core design philosophy.
