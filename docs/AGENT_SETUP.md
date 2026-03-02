# MCProxy Agent Setup

Add this to your `CLAUDE.md` or `AGENTS.md` file:

## Quick Setup Snippet

```markdown
## MCProxy Integration

MCProxy provides MCP tools via the v2 Code Mode API.

**IMPORTANT: Skip search for known tools!**

Most of the time you can call `mcproxy_execute` directly. The available servers are listed in the MCP instructions.

### Direct Execution (Recommended)

```python
# Call execute directly - no search needed!
mcproxy_execute(code='''
result = api.server("perplexity_sonar").perplexity_search_web(
    query="latest news",
    search_recency_filter="day"
)
''')
```

### Common Servers

- `perplexity_sonar` - Web search
- `wikipedia` - Wikipedia articles
- `playwright` - Browser automation
- `think_tool` - Simple reasoning
- `sequential_thinking` - Multi-step reasoning
- `fear_greed_index` - Market sentiment
- `coincap` - Crypto prices
- `asset_price` - Stock prices
- `youtube` - Video subtitles
- `llms_txt` - Documentation
- `pure_md` - Web scraping
- `tmux` - Terminal sessions

### When to Search

Only use `mcproxy_search` if you truly don't know which server/tool to use.

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
