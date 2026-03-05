# Empty Search Optimization

## Problem

With 1000+ servers, `mcproxy_search()` listing all tools wastes tokens:
- Depth 2 with empty query = all servers + all tools listed
- Example: 8 servers × 130 tools = ~15KB JSON response

## Solution

**Adaptive depth based on query:**
- Empty query → `max_depth=1` (concise)
- With query → `max_depth=2` (detailed)

## Implementation

### 1. Add tool counts at depth=1

```python
# manifest/query.py
if max_depth >= 1:
    server_entry["categories"] = categories
    server_entry["matched_categories"] = matched_categories
    
    # Always include tool count at depth >= 1
    tools = self._registry.get_tools(server_name, namespace)
    server_entry["tools"] = len(tools)
```

### 2. Adaptive default depth

```python
# server/handlers.py
query = params.get("query", "")

# Default to depth=1 for empty queries (concise), depth=2 for specific queries
default_depth = 1 if not query else 2
max_depth = params.get("max_depth", default_depth)
```

## Results

### Empty Search (Before)
```json
{
  "max_depth": 2,
  "results": [
    {
      "server": "home_assistant",
      "tools": 81,
      "matched_tools": [
        {"name": "ha_read_file", "match_score": 1.0},
        {"name": "ha_write_file", "match_score": 1.0},
        // ... 81 tools listed ...
      ]
    }
  ]
}
```
**Size**: ~15KB for 8 servers

### Empty Search (After)
```json
{
  "max_depth": 1,
  "results": [
    {
      "server": "home_assistant",
      "tools": 81,
      "categories": [],
      "matched_categories": []
    }
  ]
}
```
**Size**: ~500 bytes for 8 servers (30× smaller)

### With Query (Unchanged)
```json
{
  "query": "home automation",
  "max_depth": 2,
  "results": [
    {
      "server": "home_assistant",
      "tools": 81,
      "matched_tools": [
        {"name": "ha_read_file", "match_score": 1.0}
        // ... only matching tools ...
      ]
    }
  ]
}
```
**Size**: Varies by matches

## Usage

```python
# List all servers (concise)
mcproxy_search()
# Returns: server names + tool counts

# Search for specific tools (detailed)
mcproxy_search(query='home automation files')
# Returns: server names + tool counts + matched tools
```

## Token Savings

| Scenario | Before | After | Savings |
|----------|--------|-------|---------|
| 8 servers, empty query | ~15KB | ~500B | 30× |
| 100 servers, empty query | ~200KB | ~6KB | 33× |
| 1000 servers, empty query | ~2MB | ~60KB | 33× |
| Specific query | Varies | Varies | Same |

## Instructions Updated

```
Discovery:
  mcproxy_search()                        # List servers + tool counts (concise)
  mcproxy_search(query='what you need')   # Search for specific tools
```

## Deployment

✅ **Merged to main** (commit 0b4a2ee)  
✅ **Deployed to server2**  
✅ **Verified**: Empty search uses max_depth=1

## Benefits

1. **Scalability**: Works with 1000+ servers without token explosion
2. **Ergonomics**: Default behavior is concise (what you want most of the time)
3. **Flexibility**: Explicit `max_depth=2` still available if needed
4. **Backward compatible**: Existing code with explicit depth works unchanged

## Example Output

```
> mcproxy_search()

max_depth: 1
servers: 14

Results:
- fear_greed_index: 1 tool
- coinstats: 3 tools  
- home_assistant: 81 tools
- playwright: 33 tools
- perplexity_sonar: 1 tool
- pure_md: 2 tools
- sequential_thinking: 1 tool
- think_tool: 1 tool
- wikipedia: 2 tools
- youtube: 1 tool
- llms_txt: 2 tools
- jesse_baremetal: 10 tools
- trading: 2 tools
- asset_price: 2 tools

Total: 142 tools across 14 servers
```

**Token cost**: ~300 tokens (vs ~4500 before)
