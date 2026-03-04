# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Breaking Changes

#### `mcproxy_sequence` transform variable renamed: `data` → `read_result`

**What changed:**
- In `mcproxy_sequence` transform code, the variable containing the extracted read result has been renamed from `data` to `read_result`

**Why:**
- `read_result` is self-documenting - agents immediately understand it's the result from the read step
- `data` was ambiguous - agents tried to access it like `data['content'][0]['text']` when it was already extracted
- Future-proof - works regardless of extraction format (text, json, binary, etc.)

**Migration:**
```python
# Before
mcproxy_sequence(
    read={...},
    transform='''
    config = json.loads(data)
    result = {"content": json.dumps(config)}
    ''',
    write={...}
)

# After
mcproxy_sequence(
    read={...},
    transform='''
    config = json.loads(read_result)
    result = {"content": json.dumps(config)}
    ''',
    write={...}
)
```

**Impact:**
- Any existing `mcproxy_sequence` transforms using `data` will break
- Simple find/replace: `data` → `read_result` in transform code
- Deployed 2026-03-03, minimal existing usage expected

---

## [1.0.0] - 2026-03-03

### Added
- Initial release of MCProxy v2 Code Mode API
- `mcproxy_search` - Discover tools by query
- `mcproxy_execute` - Run Python code with tool access
- `mcproxy_sequence` - Read-modify-write in single call
- Namespace-aware routing
- Hot-reload configuration
- Session stash for stateful operations
