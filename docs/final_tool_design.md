# MCProxy Final Tool Design

## Evolution

1. **Started with**: 3 tools (search, execute, sequence) - agents didn't know when to use them
2. **Added**: `mcproxy_list` - but redundant with search
3. **Final**: 3 tools (search, execute, sequence) - but better organized

## Final Tool Set

### 1. mcproxy_sequence (RECOMMENDED)
**Default tool for all operations**

```python
# Simple read
mcproxy_sequence(read={
    'server': 'home_assistant', 
    'tool': 'ha_read_file', 
    'args': {'path': 'config.yaml'}
})

# Read-modify-write
mcproxy_sequence(
    read={...},
    transform='config = json.loads(read_result); config["new"] = "value"; result = {...}',
    write={'server': 'home_assistant', 'tool': 'ha_write_file'}
)
```

**Why default?**
- Works for reads (omit write)
- Works for read-modify-write (include transform + write)
- Self-documenting parameter names
- Single tool to learn

### 2. mcproxy_search
**Discover servers and tools**

```python
# List all servers
mcproxy_search()

# Search for specific tools
mcproxy_search(query='home automation files')
```

**Behavior:**
- Empty query → lists ALL servers (efficient token usage when needed)
- With query → filtered results (saves tokens)

**When to use:**
- Don't know server names
- Don't know tool names
- Exploring what's available

### 3. mcproxy_execute
**Complex Python logic**

```python
mcproxy_execute(code="""
result = api.server('home_assistant').ha_read_file(path='config.yaml')
content = result['content'][0]['text']
lines = content.split('\\n')[:10]
""")
```

**When to use:**
- Complex Python logic needed
- Multiple operations in one call
- Advanced use cases

## Instructions

```
MCProxy v2 Code Mode API

Default: Use mcproxy_sequence for all operations (reads, read-modify-write)

When unsure about server/tool names:
  mcproxy_search()                        # List all servers
  mcproxy_search(query='what you need')   # Search for specific tools

MCP Tools:
  mcproxy_sequence  - Single reads OR read-modify-write (RECOMMENDED)
  mcproxy_search    - Discover servers/tools (empty query = list all)
  mcproxy_execute   - Complex Python logic with tool access
```

## Design Principles

### 1. One Tool to Rule Them All
- **Before**: Agents had to choose between execute/sequence
- **After**: `sequence` is the default, covers 90% of cases

### 2. Discoverable Discovery
- **Before**: `api.manifest()` buried in execute code
- **After**: `mcproxy_search()` - standalone, intuitive

### 3. Efficient Token Usage
- **Before**: `mcproxy_list` always returns everything
- **After**: `mcproxy_search(query='...')` returns only matches

### 4. Progressive Disclosure
- **Level 1**: Use `sequence` for simple operations
- **Level 2**: Use `search` when uncertain
- **Level 3**: Use `execute` for complex logic

## Comparison

| Aspect | Before | After |
|--------|--------|-------|
| Number of tools | 3 | 3 (but better organized) |
| Default tool | None (choose execute/sequence) | sequence (covers most cases) |
| Discovery | `api.manifest()` in execute | `mcproxy_search()` standalone |
| Token efficiency | List always returns all | Search can filter |
| Learning curve | Steep (3 equal tools) | Gradual (default → discovery → advanced) |

## Test Results

- ✅ `mcproxy_search()` with no args lists all 8 servers
- ✅ `mcproxy_search(query='...')` filters results
- ✅ Instructions promote sequence as default
- ✅ Agents use tools when explicitly mentioned

## Future Improvements

1. Make agents more likely to use `mcproxy_search()` for vague prompts
2. Add usage examples in instructions
3. Consider auto-discovery on first call (but adds overhead)

## Deployment

✅ **Merged to main** (commit ca48b10)  
✅ **Deployed to server2**  
✅ **Active and running**

---

**Key Insight**: Simpler is better. Merge `list` into `search`, make `sequence` the default, keep `execute` for advanced cases.
