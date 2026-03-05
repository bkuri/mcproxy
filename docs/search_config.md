# Search Configuration

## Config File

Add to `mcproxy.json`:

```json
{
  "search": {
    "min_words": 2,
    "max_tools": 5
  }
}
```

## Parameters

### `min_words` (default: 2)

Minimum words to trigger depth=2 (schemas).

| Value | Behavior |
|-------|----------|
| `0` or negative | Always depth=2 (schemas for all queries) |
| `1` | Single word triggers depth=2 |
| `2` (default) | Two+ words trigger depth=2 |
| `3+` | Only longer queries get schemas |

**Example:**
```json
{"min_words": 3}  // "ha_read_file" → depth=1, "read ha config file" → depth=2
```

### `max_tools` (default: 5)

Maximum tools to return at depth=2 per server.

| Value | Behavior |
|-------|----------|
| `0` or negative | Unlimited (show all matching tools) |
| `5` (default) | Top 5 tools per server |
| `10` | Top 10 tools per server |
| `100+` | Show many tools (use carefully) |

**Example:**
```json
{"max_tools": 10}  // Show top 10 tools with schemas
{"max_tools": 0}   // Show ALL tools with schemas (no limit)
```

## Use Cases

### Conservative (Default)
```json
{"min_words": 2, "max_tools": 5}
```
- 2+ words → depth=2 with top 5 tools
- Balances token usage with usefulness

### Unlimited Tools
```json
{"min_words": 2, "max_tools": 0}
```
- 2+ words → depth=2 with ALL matching tools
- Good when you have few tools or need comprehensive results

### Always Schemas
```json
{"min_words": 0, "max_tools": 5}
```
- ANY query → depth=2 (even single words)
- Good when you always want to see tool schemas

### Unlimited Everything
```json
{"min_words": 0, "max_tools": 0}
```
- Always depth=2, show ALL tools
- Maximum information, maximum tokens
- Use only when you have few tools or need everything

## Token Impact

With 100 tools across 10 servers:

| Config | Tokens (depth=2) |
|--------|------------------|
| `max_tools: 5` | ~2,000 |
| `max_tools: 10` | ~4,000 |
| `max_tools: 0` | ~20,000 |

**Recommendation**: Start with defaults (2, 5). Increase only if needed.

## Instructions

The startup instructions are **dynamic** - they show your actual config:

```
Search behavior:
  - 2+ words → depth=2 (top 5 matching tools with schemas + warning)
```

With `{"max_tools": 0}`:
```
Search behavior:
  - 2+ words → depth=2 (all matching tools with schemas + warning)
```
