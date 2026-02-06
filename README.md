# MCProxy - MCP Gateway Aggregator

A lightweight, configuration-driven MCP (Model Context Protocol) gateway that aggregates multiple stdio MCP servers through a single SSE endpoint.

**Status**: Beta - Internal Use  
**Python Version**: 3.11+  
**Memory**: <512MB  
**Port**: 12010 (default)  
**Security**: Internal network only (no authentication yet)

---

## Features

- ✅ **Hot-Reload**: Edit config without restarting connections
- ✅ **Auto-Restart**: Crashed servers auto-recover (max 3 attempts)
- ✅ **Zero-Config Tool Prefixing**: Automatic namespace resolution
- ✅ **Environment Variable Interpolation**: `${VAR_NAME}` in JSON configs
- ✅ **Low Memory Footprint**: <512MB with 10+ servers
- ✅ **Syslog + Stdout Logging**: Comprehensive observability
- ✅ **Docker/Podman Ready**: Containerized deployment

---

## Quick Start

### Method 1: Native Deployment (Recommended for production)

```bash
# Clone or copy files
cd /srv/containers/mcp-gateway

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create config directory
mkdir -p config

# Copy example config and edit
cp mcp-servers.example.json config/mcp-servers.json
nano config/mcp-servers.json

# Set environment variables
cp .env.example .env
nano .env
# Add your API keys to .env

# Run development server
python main.py --log --port 12010 --config config/mcp-servers.json
```

### Method 2: Podman Compose (Easy deployment)

```bash
# Prepare environment
cp .env.example .env
nano .env
# Add your API keys

# Prepare config
mkdir -p config
cp mcp-servers.example.json config/mcp-servers.json
nano config/mcp-servers.json

# Build and start
podman-compose up -d

# View logs
podman-compose logs -f

# Stop
podman-compose down
```

### Method 3: Quadlet (Systemd-native container)

```bash
# Copy quadlet to system directory
sudo cp mcproxy.container /etc/containers/systemd/mcproxy.container

# Reload systemd
sudo systemctl daemon-reload

# Prepare environment and config (as in Method 1)
# ...

# Start service
sudo systemctl enable mcproxy.service
sudo systemctl start mcproxy.service

# View logs
sudo journalctl -u mcproxy -f
```

---

## Configuration

### mcp-servers.json Format

```json
{
  "servers": [
    {
      "name": "wikipedia",
      "command": "/usr/bin/npx",
      "args": ["-y", "wikipedia-mcp"],
      "env": {
        "PATH": "/usr/bin:/usr/local/bin:/bin"
      },
      "timeout": 60,
      "enabled": true
    }
  ]
}
```

### Environment Variables

Place API keys in `.env` (not committed to git):

```
PERPLEXITY_API_KEY=pplx-xxxxx
PUREMD_API_KEY=pmd-xxxxx
```

Reference in config using `${VAR_NAME}`:

```json
"env": {
  "PERPLEXITY_API_KEY": "${PERPLEXITY_API_KEY}",
  "PERPLEXITY_MODEL": "sonar"
}
```

---

## Command-Line Options

```bash
python main.py [OPTIONS]

Options:
  --log              Log to stdout instead of syslog (useful for debugging)
  --port PORT         Port to listen on (default: 12010)
  --config PATH       Path to mcp-servers.json (default: config/mcp-servers.json)
  --host HOST         Host to bind to (default: 0.0.0.0)
  --no-reload        Disable hot-reload configuration watcher
  --reload-interval SECONDS  Config check interval (default: 1.0)
```

---

## Testing

### Test SSE Endpoint

```bash
curl -N http://localhost:12010/sse
```

### List Tools

```bash
curl -X POST http://localhost:12010/sse \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

### Call Tool

```bash
curl -X POST http://localhost:12010/sse \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc":"2.0",
    "id":1,
    "method":"tools/call",
    "params":{
      "name":"wikipedia__search",
      "arguments":{"query":"Bitcoin"}
    }
  }'
```

---

## MCP Server Configuration

### Adding New MCP Servers

Edit `mcp-servers.json`:

```json
{
  "name": "my_new_server",
  "command": "/usr/bin/npx",
  "args": ["-y", "my-mcp-server"],
  "env": {
    "PATH": "/usr/bin:/usr/local/bin:/bin",
    "API_KEY": "${MY_API_KEY}"
  },
  "timeout": 60,
  "enabled": true
}
```

**Hot-reload** will automatically detect changes and restart affected servers within 1 second.

### Popular MCP Servers

| Server | Command | Package |
|--------|----------|----------|
| Wikipedia | `npx -y wikipedia-mcp` | npm |
| YouTube | `npx -y @anaisbetts/mcp-youtube` | npm |
| Tmux | `npx -y @executeautomation/tmux-mcp-server` | npm |
| Perplexity | `uvx perplexity-mcp` | Python/uv |
| Playwright | `uvx @executeautomation/playwright-mcp-server` | Python/uv |

---

## Deployment

### Production Checklist

- [ ] Configure `mcp-servers.json` with all required MCP servers
- [ ] Set API keys in `.env` file
- [ ] Adjust port if needed (default: 12010)
- [ ] Enable syslog logging (remove `--log` flag for production)
- [ ] Set resource limits (512M memory recommended)
- [ ] Configure hot-reload (default: enabled)
- [ ] Test all tools before going live
- [ ] Set up monitoring (journalctl -u mcproxy -f)

### Systemd Service (Native)

Create `/etc/systemd/system/mcproxy.service`:

```ini
[Unit]
Description=MCProxy - MCP Gateway Aggregator
Documentation=https://github.com/mcproxy/mcproxy
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=server
WorkingDirectory=/srv/containers/mcp-gateway
Environment="PATH=/srv/containers/mcproxy/gateway/venv/bin:/usr/local/bin:/usr/bin"
EnvironmentFile=/srv/containers/mcproxy/gateway/.env
ExecStart=/srv/containers/mcproxy/gateway/venv/bin/python main.py --config /srv/containers/mcproxy/gateway/config/mcp-servers.json

# Resource limits
MemoryMax=512M
CPUQuota=50%

# Restart policy
Restart=always
RestartSec=10

# Logging
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=mcproxy

[Install]
WantedBy=multi-user.target
```

---

## Troubleshooting

### Server Won't Start

```bash
# Check logs
tail -f /tmp/mcproxy.log

# Check config syntax
python -m json.tool config/mcp-servers.json

# Check port availability
sudo ss -tlnp | grep :12010
```

### MCP Server Fails to Initialize

```bash
# Check MCProxy logs
sudo journalctl -u mcproxy -f

# Test MCP server command manually
/usr/bin/npx -y wikipedia-mcp

# Check API keys
env | grep API_KEY
```

### Memory Issues

```bash
# Check memory usage
sudo systemctl status mcproxy
# Look for: "Mem peak:" value

# Increase limit in systemd or quadlet
MemoryMax=1024M
```

### Hot-Reload Not Working

```bash
# Check config file permissions (must be readable)
ls -la config/mcp-servers.json

# Verify reload interval
# Default is 1.0 seconds, increase if needed:
python main.py --reload-interval 5.0
```

---

## Architecture

```
mcp-servers.json (config)
        ↓
    [Config Watcher] ← Polls every 1s
        ↓
    [HTTP SSE Server]
    (FastAPI on 12010)
        ↓
    [Server Manager]
    (spawns stdio processes)
        ↓
    [Tool Aggregator]
    (prefixes: server__tool)
        ↓
    [Logging System]
    (syslog + stdout)
```

---

## Dependencies

```txt
fastapi==0.104.0
uvicorn==0.24.0
python-json-logger==2.0.7
```

---

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

---

## License

MIT License

---

## Roadmap

Future enhancements (not yet implemented):
- [ ] Authentication & authorization
- [ ] TLS/SSL support
- [ ] Metrics & monitoring dashboard
- [ ] Request rate limiting
- [ ] Load balancing for multiple gateways
- [ ] Tool-level access control

## Support

For issues, questions, or contributions:
- **GitHub**: https://github.com/bkuri/mcproxy
- **Issues & Bugs**: https://github.com/bkuri/mcproxy/issues
- **Discussions**: https://github.com/bkuri/mcproxy/discussions
