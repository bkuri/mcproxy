# MCProxy

> A lightweight MCP gateway that aggregates multiple stdio and HTTP MCP servers through namespaced endpoints.

**Status**: v5.0.3 | **Python**: 3.11+ | **Port**: 12010

---

## Features

| Feature | Description |
|---------|-------------|
| **Code Mode API** | Single `mcproxy` meta-tool with execute/search/inspect/help actions |
| **Dual Transport** | Stdio and HTTP MCP servers — connect to pre-existing services or spawn child processes |
| **Namespace Isolation** | Group servers by privilege level with access control and `!` force-include |
| **API Key Auth** | Agent auth with encrypted credential storage and rotation |
| **Blocklist Security** | Server validation with blocked/risky classification |
| **Manifest System** | Capability registry with caching, TypeScript type generation, and event hooks |
| **Sandbox Pool** | Pre-warmed sandbox instances with configurable pool sizing |
| **Session Stash** | Per-session key-value store with TTL for cross-call state |
| **Hot-Reload** | Add/remove servers without dropping connections |
| **Dual Mode** | HTTP/SSE endpoint OR native MCP server over stdio |

---

## Quick Start

```bash
# Setup
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

# Run
python main.py --log --config mcproxy.json
```

### Docker

```bash
docker build -t localhost/mcproxy:latest .
docker run -d -p 12010:12010 \
  -v $(pwd)/config:/app/config:Z \
  localhost/mcproxy:latest
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        MCProxy Gateway                          │
│                                                                 │
│  ┌───────────────┐ ┌───────────────┐ ┌───────────────────────┐ │
│  │  Auth          │ │  Blocklist    │ │  Manifest             │ │
│  │  (API keys +  │ │  (blocked/    │ │  (registry + cache +  │ │
│  │   credentials)│ │   risky)      │ │   TypeScript gen)     │ │
│  └───────┬───────┘ └───────┬───────┘ └───────────┬───────────┘ │
│          └─────────────────┼─────────────────────┘             │
│                            │                                    │
│  ┌─────────────────────────┼────────────────────────────────┐  │
│  │  Sandbox Pool           │    Session Stash               │  │
│  │  (pre-warmed executors  │    (per-session KV + TTL)      │  │
│  │   with code validation) │                                │  │
│  └─────────────────────────┼────────────────────────────────┘  │
│                            │                                    │
│  ┌─────────────────────────┼────────────────────────────────┐  │
│  │                  Server Manager                           │  │
│  │                                                           │  │
│  │  ┌─ Stdio ─────────────┐  ┌─ HTTP ─────────────────────┐ │  │
│  │  │ wikipedia  youtube  │  │ jesse (per-tool timeouts)   │ │  │
│  │  │ perplexity coinstats│  │ any Streamable HTTP server  │ │  │
│  │  │ llms_txt  more...   │  │                             │ │  │
│  │  └────────────────────┘  └─────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Configuration

### Servers

MCProxy supports two server types:

```json
{
  "servers": [
    {
      "name": "wikipedia",
      "command": "/usr/bin/npx",
      "args": ["-y", "wikipedia-mcp"],
      "timeout": 60
    },
    {
      "name": "jesse",
      "type": "http",
      "url": "http://localhost:12011/mcp",
      "timeout": 350,
      "tool_timeout": 600,
      "tool_timeouts": {
        "backtest": 900,
        "optimize": 1200
      }
    }
  ]
}
```

### Namespaces & Groups

```json
{
  "namespaces": {
    "docs": {"servers": ["wikipedia", "llms_txt"], "isolated": false},
    "trading": {"servers": ["jesse"], "isolated": true},
    "home": {"servers": ["home_assistant"], "isolated": false}
  },
  "groups": {
    "research": {"namespaces": ["thinking", "docs", "web", "financial"]},
    "maxitrader": {"namespaces": ["thinking", "financial", "docs", "web", "!trading"]}
  }
}
```

The `!` prefix on a namespace in a group means **force-include** — isolated namespaces are normally excluded from groups unless explicitly prefixed.

### Sandbox

```json
{
  "sandbox": {
    "timeout_secs": 900,
    "pool": {
      "size": 3,
      "max_size": 10,
      "idle_timeout_secs": 300
    }
  }
}
```

---

## Security

Defense-in-depth with blocklist validation and sandbox hardening:

- **Blocklist validation** at startup (blocked/risky/unclassified)
- **Sandbox code validation** — blocked imports (`os`, `subprocess`, `socket`, …), blocked builtins (`eval`, `exec`, `open`, …), blocked dunder attributes
- **JS-style auto-conversion** — agents commonly send `{key: "value"}` instead of `{"key": "value"}`; the sandbox auto-fixes this and other common syntax errors
- **Shell removal** in container (sh/bash/python disabled)
- **Capability dropping** (CapDrop=ALL) and **filesystem isolation** (ProtectHome, ReadOnlyRootfs)

### Blocked Servers

```json
{
  "@executeautomation/tmux-mcp-server": "blocked (arbitrary shell execution)"
}
```

### Risky Servers (require acknowledgment)

```json
{
  "security": {
    "allow_risky_servers": true,
    "risky_server_acknowledgments": {
      "playwright": "Required for browser automation"
    }
  }
}
```

---

## Documentation

| Document | Purpose |
|----------|---------|
| [AGENTS.md](AGENTS.md) | Agent guidelines (quick reference) |
| [docs/EXAMPLES.md](docs/EXAMPLES.md) | Detailed usage examples |
| [docs/HISTORY.md](docs/HISTORY.md) | Archived documentation |
| [ROADMAP.md](ROADMAP.md) | Future plans and milestones |

## Also See

- [CHANGELOG.md](CHANGELOG.md) - Version history

---

## CLI Options

```bash
python main.py [OPTIONS]
  --stdio              Native MCP server over stdio
  --log                Log to stdout (default: syslog)
  --port PORT          Port (default: 12010)
  --config PATH        Config file path
  --no-reload          Disable hot-reload
```

---

## Deployment

```bash
# Quadlet (Systemd)
sudo cp mcproxy.container /etc/containers/systemd/
sudo systemctl enable --now mcproxy.service

# Auto-deploy (after initial setup)
git push  # Hook handles rest
```

---

## Configuration

### Timeouts

Each server has a configurable `timeout` (in seconds) that controls how long mcproxy waits for a response from the MCP subprocess. The default is **120 seconds**.

```json
{
  "name": "my_server",
  "command": "/usr/bin/npx",
  "args": ["-y", "some-mcp-server"],
  "timeout": 120
}
```

For long-running operations (e.g., backtesting), you can set higher timeouts or use `tool_timeouts` for per-tool overrides:

```json
{
  "name": "jesse",
  "timeout": 350,
  "tool_timeout": 600,
  "tool_timeouts": {
    "backtest": 900,
    "optimize": 1200
  }
}
```

> **Note:** If you're calling mcproxy through an MCP client (e.g., opencode, Claude Desktop), ensure the client's own timeout is set higher than mcproxy's server timeout, or the client may terminate the connection before mcproxy responds. For example, in opencode's `opencode.json`, set `"timeout": 120000` (120s in milliseconds).

---

## Troubleshooting

```bash
# Health check
curl http://localhost:12010/health

# Validate config
python -m json.tool mcproxy.json

# Check logs
journalctl -u mcproxy.service -f
```

---

## Dependencies

```
fastapi>=0.104.0
uvicorn>=0.24.0
python-json-logger>=2.0.7
fastmcp>=0.1.0
orjson>=3.9.0
cryptography>=42.0.0
python-jose[cryptography]>=3.3.0
bcrypt>=4.0.0
aiohttp>=3.9.0
```

---

## Acknowledgments

MCProxy v2.0's Code Mode architecture was inspired by **[Forgemax](https://github.com/postrv/forgemax)** — a Rust-based MCP gateway that introduced the concept of collapsing N servers × M tools into just 2 meta-tools (`search` + `execute`) for massive context reduction.

---

**GitHub**: https://github.com/bkuri/mcproxy
**Issues**: https://github.com/bkuri/mcproxy/issues
