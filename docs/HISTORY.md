# MCProxy History

Archived documentation from earlier versions. For current documentation, see [AGENTS.md](../AGENTS.md) and [ROADMAP.md](../ROADMAP.md).

## Phase 2 Features (v3.2 - v3.x)

These features were implemented and are now part of the core system.

### Hot-Reload Configuration

MCProxy watches the config file and reloads automatically:

- **Automatic detection** of mcproxy.json changes
- **Zero-downtime reload** - SSE connections stay alive
- **Smart diffing** - Only changed servers are restarted
- **Validation** - Invalid configs are rejected with error logging

### Auto-Restart Failed Servers

Servers that crash are automatically restarted:

- **Max 3 restart attempts** to prevent restart loops
- **2-second delay** between restart attempts
- **Health monitoring** before each tool call

### Robust Error Handling

The system handles edge cases gracefully:

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

## Phase 3 Features (v3.3 - v3.x)

### Namespace-Aware Routing

Namespaces provide server isolation:

```json
{
  "servers": [...],
  "namespaces": {
    "dev": {
      "servers": ["wikipedia", "llms_txt"],
      "isolated": false
    },
    "home": {
      "servers": ["home_assistant"],
      "isolated": true
    }
  }
}
```

### Groups

Groups merge multiple namespaces:

```json
{
  "groups": {
    "dev_full": {
      "namespaces": ["dev", "docs"]
    }
  }
}
```

## Dependencies (Historical)

Earlier versions had these dependencies. Current versions use [pyproject.toml](../pyproject.toml).

```
fastapi==0.104.0
uvicorn==0.24.0
python-json-logger==2.0.7
```

## Internal Tool Naming (v1)

In v1, tools were prefixed with server name:

```python
# v1 format (deprecated)
tool_name = f"{server_name}__{original_tool_name}"

# v2+ format (current)
api.server('server').tool(args)
```

## See Also

- [ROADMAP.md](../ROADMAP.md) - Future plans and milestones
- [AGENTS.md](../AGENTS.md) - Agent guidelines (current)
- [docs/EXAMPLES.md](EXAMPLES.md) - Usage examples
