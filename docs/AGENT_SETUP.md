# MCProxy Agent Setup

Add this to your `CLAUDE.md` or `AGENTS.md` file:

## Quick Setup Snippet

```markdown
## MCProxy Integration

MCProxy provides MCP tools via the v2 Code Mode API.

**⚠️ CRITICAL: Use only servers from the MCP instructions**

Server names vary by environment. Check the "Available servers and tools" section in the MCP instructions when you connect. Do NOT guess names like `playwright` or `pure_md`.

### Direct Execution (Recommended)

```python
# CORRECT: Use servers from the instructions
result = api.server("wikipedia").search(query="python")
```

### When to Search

Only use `mcproxy_search` if you need to discover tool schemas or explore available tools.

### Hot-Reload (No Restart Needed)

MCProxy supports **hot-reload** for configuration changes:

✅ **Add/remove servers** - Automatically starts/stops server processes  
✅ **Add/remove namespaces** - New namespace endpoints become accessible  
✅ **Add/remove groups** - Group merging updates dynamically  
✅ **Modify server configs** - Servers restart automatically  

Just edit `mcproxy.json` and save. Changes apply within 1 second without restart!

❌ **Requires restart**: Python code changes (as expected for any Python app)
```

## Full Configuration

For complete setup, see:
- MCProxy AGENTS.md: `/path/to/mcproxy/AGENTS.md`
- Quick Start Guide: `/path/to/mcproxy/docs/guides/quick-start-v2.md`
