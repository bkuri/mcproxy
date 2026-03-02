# MCProxy Quick Reference for Chat Integration

## Overview

MCProxy is now available as a native MCP server that exposes 52+ tools from multiple MCP servers. Once configured in this chat interface, you can call any of these tools directly.

## 🛠️ Available Tools

### Thinking & Reasoning Tools
- **think_tool__think**: Simple single-thought reasoning
  - Parameters: `thought` (string)
  
- **sequential_thinking__sequentialthinking**: Multi-step structured reasoning
  - Parameters: `thought`, `thoughtNumber`, `totalThoughts`, `nextThoughtNeeded`
  
- **atom_of_thoughts__AoT**: Atomic reasoning with dependencies
  - Parameters: `atomId`, `content`, `atomType`, `dependencies`, `confidence`

### Market & Finance Tools
- **fear_greed_index__get_fear_greed_index**: US stock market sentiment
  - No parameters
  
- **coincap__get_assets**: Cryptocurrency data
  - Parameters: `limit` (optional)
  
- **asset_price__get_price**: Asset pricing information
  - Parameters: `symbol` (required)

### Information & Search Tools
- **wikipedia__search_wikipedia**: Wikipedia search
  - Parameters: `query` (required)
  
- **youtube__search_videos**: YouTube video search
  - Parameters: `query` (required)
  
- **perplexity_sonar__perplexity_search**: Web search via Perplexity
  - Parameters: `query` (required)

### Browser Automation Tools
- **playwright__navigate_page**: Navigate to URL
- **playwright__get_page_content**: Get page content
- **playwright__click_element**: Click on page elements
- And 30+ more playwright tools for web automation

### Documentation Tools
- **llms_txt__get_langraph_docs**: LangGraph documentation
- **pure_md__get_markdown_links**: Markdown file operations

## 🔄 How to Use in This Chat

### Format

When calling tools through MCProxy, use the format:

```
Tool: call_tool
Arguments: {
  "name": "server__tool_name",
  "arguments": {
    "param1": "value1",
    "param2": "value2"
  }
}
```

### Examples

**Example 1: Get market fear/greed index**
```
Tool: call_tool
Arguments: {
  "name": "fear_greed_index__get_fear_greed_index",
  "arguments": {}
}
```

**Example 2: Search Wikipedia**
```
Tool: call_tool
Arguments: {
  "name": "wikipedia__search_wikipedia",
  "arguments": {
    "query": "Bitcoin"
  }
}
```

**Example 3: Use thinking tool**
```
Tool: call_tool
Arguments: {
  "name": "think_tool__think",
  "arguments": {
    "thought": "What are the implications of quantum computing for cryptography?"
  }
}
```

**Example 4: Multi-step reasoning**
```
Tool: call_tool
Arguments: {
  "name": "sequential_thinking__sequentialthinking",
  "arguments": {
    "thought": "First, let me think about the problem statement",
    "thoughtNumber": 1,
    "totalThoughts": 3,
    "nextThoughtNeeded": true
  }
}
```

## 📋 Complete Tool List

MCProxy exposes these servers and their tools:

### 1. **fear_greed_index** (1 tool)
   - get_fear_greed_index

### 2. **sequential_thinking** (1 tool)
   - sequentialthinking

### 3. **atom_of_thoughts** (3 tools)
   - AoT
   - AoT_light
   - atomcommands

### 4. **think_tool** (1 tool)
   - think

### 5. **coincap** (3 tools)
   - get_assets
   - get_exchange_rates
   - get_historical_data

### 6. **llms_txt** (2 tools)
   - get_langraph_docs
   - get_docs

### 7. **youtube** (1 tool)
   - search_videos

### 8. **wikipedia** (2 tools)
   - search_wikipedia
   - get_page_content

### 9. **asset_price** (2 tools)
   - get_price
   - get_historical_prices

### 10. **pure_md** (2 tools)
   - get_markdown_links
   - get_file_content

### 11. **playwright** (33 tools)
   - navigate_page
   - get_page_content
   - click_element
   - type_text
   - take_screenshot
   - And 28 more...

### 12. **perplexity_sonar** (1 tool)
   - perplexity_search

## ⚙️ Configuration Status

MCProxy is configured with:
- **13 MCP servers** (one disabled: ollama)
- **52 total tools** available
- **Startup time**: ~10-12 seconds
- **Memory usage**: <1GB

## 🚨 Tips & Troubleshooting

### Tool Names
- Always use format: `server__tool_name` (double underscore)
- Examples: `wikipedia__search_wikipedia`, `fear_greed_index__get_fear_greed_index`

### Arguments
- Check the tool description for required vs optional parameters
- Some tools take no arguments (use empty `{}`)
- Always pass arguments as proper JSON

### Errors
- If tool not found, check spelling and double underscores
- If server not responding, it might still be starting up
- Some tools (thinking tools) take longer (200-500ms)

### Rate Limits
- No rate limiting currently enforced
- Be mindful of API limits for Perplexity and asset price APIs
- Check your .env file for API keys configuration

## 📚 Documentation

For more details:
- **README.md**: Full MCProxy documentation
- **SESSION_SUMMARY.md**: Technical implementation details
- **THINKING_TOOLS_QUICK_REFERENCE.md**: Detailed thinking tool reference
- **TESTING_THINKING_TOOLS.md**: Comprehensive testing guide

## 🔗 Repository

- **GitHub**: https://github.com/bkuri/mcproxy
- **Latest docs**: Check the repo for updates

---

**Last Updated**: 2026-02-06  
**Status**: Ready for Use
