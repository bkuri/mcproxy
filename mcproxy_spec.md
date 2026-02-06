# MCProxy - Custom MCP Gateway Specification

## Overview

MCProxy is a lightweight, configuration-driven MCP (Model Context Protocol) aggregator that exposes multiple external stdio MCP servers through a single SSE (Server-Sent Events) endpoint. It prioritizes simplicity, reliability, and operational ease-of-use through hot-reloadable configuration.

**Target**: Production-ready set-and-forget service for hobby/internal use.

---

## Requirements & Constraints

### Functional Requirements
- ✅ Aggregate 10+ external stdio MCP servers into single gateway
- ✅ Expose via MCP SSE transport (compatible with Claude Desktop, Cursor, VS Code)
- ✅ Hot-reload configuration from `mcp-servers.json` without service restart
- ✅ Tool name aggregation with server prefix (e.g., `claude_tools__some_tool`)
- ✅ Graceful error handling (one bad server doesn't break entire gateway)
- ✅ Syslog logging with optional `--log` flag for stdout

### Non-Functional Requirements
- Config reload latency: 1-2 seconds acceptable
- Memory footprint: <100MB total
- Startup time: <5 seconds
- Availability: Set-and-forget (minimal maintenance)
- Python 3.11+ required

---

## Architecture

### Components
1. **HTTP SSE Server** - Listens on 0.0.0.0:12009
2. **Server Manager** - Spawns & manages stdio processes
3. **Config Watcher** - Hot-reload mcp-servers.json
4. **Tool Aggregator** - Prefixes & aggregates tools
5. **Logging** - Syslog + optional stdout

### Directory Structure
```
/srv/containers/mcp-gateway/
├── mcp-servers.json
├── main.py
├── server.py
├── server_manager.py
├── config_watcher.py
├── tool_aggregator.py
├── logging_config.py
├── requirements.txt
└── Dockerfile
```

---

## Configuration

### mcp-servers.json Format
```json
{
  "servers": [
    {
      "name": "playwright",
      "command": "npx",
      "args": ["@modelcontextprotocol/server-playwright"],
      "env": {},
      "timeout": 30,
      "enabled": true
    }
  ]
}
```

### Fields
- `name`: Server ID (alphanumeric + underscore)
- `command`: Executable
- `args`: Command arguments array
- `env`: Environment variables (supports ${VAR_NAME})
- `timeout`: Init timeout in seconds
- `enabled`: Start this server? (default: true)

---

## Deployment

### Quadlet File
**Location**: `/etc/containers/systemd/mcp-gateway.container`

```ini
[Unit]
Description=MCProxy - MCP Gateway
After=network-online.target
Wants=network-online.target

[Container]
Image=localhost/mcproxy:latest
ContainerName=mcp-gateway
Network=host
WorkingDirectory=/app
Volume=/srv/containers/mcp-gateway:/app:Z
Exec=python main.py --log

[Install]
WantedBy=multi-user.target
```

### Commands
```bash
sudo systemctl start mcp-gateway.service
sudo journalctl -u mcp-gateway.service -f
sudo systemctl restart mcp-gateway.service
```

---

## API

### SSE Endpoint
- **URL**: http://localhost:12009/sse
- **Protocol**: MCP SSE
- **Heartbeat**: 30 seconds

### Tool Naming
Format: `{server_name}__{tool_name}`

Example: `playwright__navigate_page`

---

## Logging

### Syslog (default)
```
Feb 05 10:30:45 server2 mcp-gateway[12345]: [INFO] Server 'playwright' started
```

### Stdout (--log flag)
```
2025-02-05 10:30:45,123 [INFO] Server 'playwright' started
```

---

## Operations

### Add Server
1. Edit `/srv/containers/mcp-gateway/mcp-servers.json`
2. Add entry to `servers` array
3. Save (auto-reloads in 1-2 seconds)

### Disable Server
Set `"enabled": false` in config

### Troubleshooting
```bash
# Check config
python -m json.tool /srv/containers/mcp-gateway/mcp-servers.json

# View logs
sudo journalctl -u mcp-gateway.service -n 50

# Restart
sudo systemctl restart mcp-gateway.service
```

---

## Dependencies

**Python** (4 packages):
- fastapi==0.104.0
- uvicorn==0.24.0
- python-json-logger==2.0.7
- watchfiles==0.21.0

**System**:
- Python 3.11+
- Podman/Docker
- syslog daemon

---

## Implementation Plan

### Phase 1: MVP (3-4 hours)
- Basic HTTP SSE server
- Stdio server spawning
- Tool aggregation
- Config loading & validation
- Basic error handling

### Phase 2: Polish (2-3 hours)
- Hot-reload config watcher
- Comprehensive logging
- Graceful transitions
- Process recovery
- Container setup

### Phase 3: Deploy (1-2 hours)
- Quadlet file
- Documentation
- Initial deployment
- MetaMCP migration

---

## Success Criteria
✅ Replaces MetaMCP
✅ 10+ servers aggregated
✅ Hot-reload works
✅ No auth needed
✅ Syslog logging
✅ <100MB memory
✅ Set-and-forget operation
✅ Clean, documented code

---

**Status**: Ready for Implementation
**Next**: Extract MetaMCP servers → Begin Phase 1
