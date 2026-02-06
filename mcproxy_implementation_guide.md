# MCProxy - Implementation Guide

## Pre-Implementation Checklist

Before starting Phase 1, gather current MCP server information:

### 1. Extract MetaMCP Configuration
```bash
ssh server2-auto "sudo cat /etc/containers/systemd/mcp-metamcp.container"
```

Look for:
- Volume mounts (server definitions)
- Environment variables (API keys)
- Image used (may contain config)

### 2. Check for Local MCP Servers
```bash
# Check if Jesse or other services have MCP capabilities
ssh server2-auto "find /srv/containers -name '*mcp*' -o -name '*server*' 2>/dev/null"
```

### 3. Identify Stdio Server Commands
Create a list like:
```
1. Playwright: npx @modelcontextprotocol/server-playwright
2. Claude: python -m mcp.servers.claude
3. Perplexity: node /path/to/perplexity-server.js
... (10+ servers)
```

---

## Phase 1: MVP Implementation (3-4 hours)

### Step 1: Project Setup

```bash
# Create project directory
mkdir -p /srv/containers/mcp-gateway
cd /srv/containers/mcp-gateway

# Create Python venv
python3.11 -m venv venv
source venv/bin/activate

# Create requirements.txt
cat > requirements.txt << 'REQS'
fastapi==0.104.0
uvicorn==0.24.0
python-json-logger==2.0.7
watchfiles==0.21.0
REQS

pip install -r requirements.txt
```

### Step 2: Basic HTTP Server (server.py)

Create `server.py` with:
- FastAPI app initialization
- SSE endpoint `/sse`
- Basic MCP protocol handling
- Error handling for missing server manager

Key functions:
- `async def sse_endpoint()`: Main SSE connection handler
- `async def initialize()`: MCP protocol init
- `async def list_tools()`: Return aggregated tool list
- `async def call_tool()`: Route request to appropriate server

### Step 3: Server Manager (server_manager.py)

Create `server_manager.py` with:
- ServerManager class to spawn/manage processes
- Config-driven server creation
- Tool aggregation from each server
- Error recovery (restart failed servers)

Key methods:
- `__init__(config)`: Initialize with config
- `spawn_servers()`: Start all enabled servers
- `get_aggregated_tools()`: Collect tools from all servers
- `route_tool_call(server_name, tool_name, args)`: Execute tool
- `stop_servers()`: Graceful shutdown

### Step 4: Config Loading (config_watcher.py)

Create `config_watcher.py` with:
- Load mcp-servers.json
- JSON Schema validation
- Environment variable interpolation
- Return validated config dict

Key functions:
- `load_config(path)`: Parse and validate JSON
- `validate_schema(config)`: Check required fields
- `interpolate_env_vars(config)`: Replace ${VAR_NAME}

### Step 5: Tool Aggregation (tool_aggregator.py)

Create `tool_aggregator.py` with:
- Collect tools from stdio servers
- Add server prefix: `{server}__{tool}`
- Handle duplicates/conflicts
- Caching with TTL

Key functions:
- `get_tools_from_server(server)`: Query server for tools
- `aggregate_tools(servers)`: Merge all tools with prefixes
- `resolve_conflicts(tools)`: Handle duplicates

### Step 6: Logging Setup (logging_config.py)

Create `logging_config.py` with:
- Syslog configuration (default)
- Stdout configuration (--log flag)
- Structured logging format

Key functions:
- `setup_syslog()`: Configure syslog handler
- `setup_stdout()`: Configure console handler
- `get_logger(name)`: Return configured logger

### Step 7: Main Entry Point (main.py)

Create `main.py` with:
- Argument parsing (--log, --port, --config)
- Config loading
- Server manager initialization
- Uvicorn server startup

```python
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", action="store_true", help="Log to stdout")
    parser.add_argument("--port", type=int, default=12009)
    parser.add_argument("--config", default="mcp-servers.json")
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(use_stdout=args.log)
    
    # Load config
    config = load_config(args.config)
    
    # Start server manager
    manager = ServerManager(config)
    manager.spawn_servers()
    
    # Run uvicorn
    uvicorn.run(app, host="0.0.0.0", port=args.port)
```

### Step 8: Initial mcp-servers.json

Create minimal config:
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

### Testing Phase 1

```bash
# Start service
python main.py --log

# In another terminal, test SSE endpoint
curl -N http://localhost:12009/sse

# Test with Claude Desktop (point to http://localhost:12009/sse)
```

Expected: Playwright tools accessible via SSE

---

## Phase 2: Hot-Reload & Polish (2-3 hours)

### Step 1: Add Hot-Reload

Enhance `config_watcher.py`:
- Watch file changes with watchfiles
- On change: validate, load, update ServerManager
- Keep existing connections alive
- Log changes

```python
async def watch_config(path, manager, interval=1):
    async for changes in awatch(path):
        try:
            new_config = load_config(path)
            manager.update_config(new_config)
            logger.info(f"Config reloaded: {len(changes)} changes")
        except Exception as e:
            logger.error(f"Config reload failed: {e}")
```

### Step 2: Improve Server Manager

Add to `server_manager.py`:
- Process monitoring (detect crashes)
- Exponential backoff restart
- Graceful shutdown handling
- Health checks

### Step 3: Enhanced Logging

Improve `logging_config.py`:
- Add request/response logging
- Log config changes
- Log server lifecycle events
- Structured JSON logging option

### Step 4: Error Handling

Add throughout:
- Try/catch for server spawning
- Timeout handling
- Graceful degradation
- Clear error messages

### Step 5: Docker Container

Create `Dockerfile`:
```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["python", "main.py", "--log"]
```

Build:
```bash
docker build -t localhost/mcproxy:latest .
```

### Testing Phase 2

```bash
# Test config hot-reload
echo '{"servers": [...]}' > mcp-servers.json
# Watch logs for reload message

# Test server crash recovery
kill <server_pid>
# Should auto-restart

# Test with multiple servers
# Add more servers to config
```

Expected: Hot-reload, crash recovery, comprehensive logging

---

## Phase 3: Deployment (1-2 hours)

### Step 1: Quadlet File

Create `/etc/containers/systemd/mcp-gateway.container`:
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

Deploy:
```bash
sudo cp mcp-gateway.container /etc/containers/systemd/
sudo systemctl daemon-reload
sudo systemctl start mcp-gateway.service
```

### Step 2: Populate Full Config

Extract from MetaMCP and add all 10+ servers to `mcp-servers.json`:
```json
{
  "servers": [
    {"name": "playwright", ...},
    {"name": "claude", ...},
    ... (10+ total)
  ]
}
```

### Step 3: Testing & Validation

```bash
# Check service status
sudo systemctl status mcp-gateway.service

# View logs
sudo journalctl -u mcp-gateway.service -f

# Test with Claude Desktop
# Connect to http://192.168.50.70:12009/sse

# Verify all tools appear
# Test tool execution from each server
```

### Step 4: Documentation

Create `README.md`:
- How to add/remove servers
- How to view logs
- Troubleshooting steps
- Port/config details

### Step 5: Optional - Cleanup

```bash
# Stop MetaMCP
sudo systemctl stop mcp-metamcp.service
sudo systemctl disable mcp-metamcp.service

# Remove old config
rm -rf /srv/containers/metamcp/
```

---

## Code Quality Checklist

- [ ] Type hints on all functions
- [ ] Docstrings for classes/modules
- [ ] Error messages are helpful
- [ ] Logging at appropriate levels
- [ ] Config validation comprehensive
- [ ] Tests pass (unit + integration)
- [ ] No hardcoded values (all from config)
- [ ] Graceful shutdown (signal handlers)
- [ ] Memory leaks checked (process monitoring)

---

## Common Pitfalls to Avoid

1. **Blocking calls** → Use async/await throughout
2. **Zombie processes** → Proper signal handling + cleanup
3. **Config validation** → Check ALL required fields
4. **Logging verbosity** → Balance detail vs noise
5. **Memory leaks** → Monitor subprocess output
6. **Tool prefixes** → Ensure consistent naming
7. **Environment vars** → Validate exists before use
8. **SSE connection** → Keep alive during reloads

---

## Estimated Timeline

| Phase | Duration | Effort |
|-------|----------|--------|
| Phase 1 MVP | 3-4 hours | Straightforward |
| Phase 2 Polish | 2-3 hours | Moderate |
| Phase 3 Deploy | 1-2 hours | Light |
| **Total** | **6-9 hours** | **Moderate** |

---

## Next Steps

1. ✅ Review spec document
2. ⏳ Extract MetaMCP server list
3. ⏳ Begin Phase 1 implementation
4. ⏳ Test with Playwright server
5. ⏳ Add remaining servers
6. ⏳ Deploy to server2
7. ⏳ Retire MetaMCP

