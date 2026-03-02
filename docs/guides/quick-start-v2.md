# MCProxy v2 Quick Start Guide

## Overview

MCProxy v2 uses a **Code Mode API** that exposes just 2 meta-tools instead of exposing all individual tools directly:

- **`search`** - Discover available tools
- **`execute`** - Run Python code that calls tools via the `api` object

This approach reduces context from ~15,000 tokens (76 tools) to ~1,000 tokens (2 tools).

## Available Tools

### Search Tool

```python
# Discover tools
mcproxy_search(query="perplexity search")
mcproxy_search(query="wikipedia")
```

### Execute Tool

The execute tool runs Python code in a sandbox with access to the `api` object:

```python
# Call tools via fluent API
result = api.server("perplexity_sonar").perplexity_search_web(
    query="latest news",
    search_recency_filter="day"
)

# Get available tools
manifest = api.manifest()

# Use session stash for caching
stash.put("key", data, ttl=3600)
cached = stash.get("key")
```

## Examples

### Example 1: Search Wikipedia

```python
result = api.server("wikipedia").search(query="Python programming language")
```

### Example 2: Get Market Data

```python
result = api.server("fear_greed_index").get_fear_greed_index()
```

### Example 3: Use Thinking Tools

```python
result = api.server("sequential_thinking").sequentialthinking(
    thought="First, let me analyze the problem",
    thoughtNumber=1,
    totalThoughts=3,
    nextThoughtNeeded=True
)
```

### Example 4: Browse the Web

```python
result = api.server("playwright").playwright_navigate(url="https://example.com")
```

## Common Mistakes to Avoid

❌ **Wrong**: Calling tools directly
```python
result = wikipedia__search(query="test")  # This won't work!
```

✅ **Right**: Use the `api` object
```python
result = api.server("wikipedia").search(query="test")
```

❌ **Wrong**: Using old `call_tool` function
```python
result = call_tool("server", "tool", {})  # Not defined!
```

✅ **Right**: Use `api.call_tool` method
```python
result = api.call_tool("server", "tool", {"arg": "value"})
```

## Available Servers

- **perplexity_sonar** - Web search with recency filtering
- **wikipedia** - Wikipedia search and articles
- **playwright** - Browser automation (33 tools)
- **sequential_thinking** - Multi-step reasoning
- **think_tool** - Simple thought processing
- **fear_greed_index** - Market sentiment
- **coincap** - Cryptocurrency data
- **asset_price** - Asset pricing
- **youtube** - YouTube video search
- **llms_txt** - Documentation access
- **pure_md** - Markdown operations

## Tips

1. **Always use `api.server("name").tool()`** - This is the v2 pattern
2. **Check available tools** with `api.manifest()`
3. **Use stash for caching** across multiple calls
4. **Namespace matters** - Some servers may not be in all namespaces

## Namespace Support

Use the `X-Namespace` header or `/sse/{namespace}` endpoint to control which servers are accessible:

- Default namespace: All non-isolated servers
- Custom namespaces: Only servers in that namespace
- Groups: Merge multiple namespaces

### Hot-Reload Namespaces

Namespaces and servers can be added/removed **without restarting** MCProxy:

```bash
# Edit config
vim mcproxy.json

# Changes apply within 1 second automatically
# New namespaces immediately accessible at /sse/{new_namespace}
# Removed servers stop automatically
```

This enables zero-downtime configuration updates in production.

## Getting Help

If you see errors like:
- `NameError: 'tool__name' is not a function` → Use `api.server()`
- `Access denied to 'server'` → Check namespace permissions
- `Tool not found` → Run `api.manifest()` to see available tools

## Further Reading

- **AGENTS.md** - Full API reference
- **README.md** - Architecture details
- **mcproxy_spec.md** - Technical specification
