# MCProxy Decision & Plan Summary

## The Choice: Custom Python Gateway

After comprehensive research and analysis, **custom Python MCP gateway (MCProxy)** is the best solution for your specific needs.

---

## Why Custom Python Wins

### vs Obot
- ✅ Perfect fit vs 80% fit (overkill)
- ✅ 500 LoC vs 100,000+ LoC monolith
- ✅ Hot-reload native from day 1
- ✅ Set-and-forget vs feature-rich UI
- ✅ You own every line vs community-maintained black box

### vs Node.js
- ✅ Mature MCP ecosystem (Python SDK is official)
- ✅ Battle-tested patterns (Magg, mcp-gateway exist)
- ✅ Better subprocess management
- ✅ No established Node.js aggregators
- ✅ Learning from proven projects

### vs FastMCP
- ✅ FastMCP is excellent for BUILDING servers, not aggregating
- ✅ Adds abstraction that complicates config-driven aggregation
- ✅ Our use case (pure passthrough) is simpler than what FastMCP targets

---

## Your Requirements Met

| Requirement | Solution |
|-------------|----------|
| **Set and forget** | Hot-reload in 1-2s, minimal ops |
| **Hot-reload mcp-servers.json** | File watcher built in |
| **10+ servers** | Tested pattern, linear scaling |
| **Syslog logging** | Default + --log for stdout |
| **No auth needed** | Omitted entirely |
| **Stable** | No Better Auth bugs, proven patterns |

---

## Architecture Decisions

### Why FastAPI?
- Lightweight (vs Flask for this simple use case)
- Native async/await support
- Minimal boilerplate
- SSE streaming built-in

### Why Python asyncio?
- Perfect for I/O-bound work (stdio servers)
- Better subprocess handling than Node.js
- Simpler long-running processes
- Proven in production (Magg uses it)

### Why SSE over WebSocket?
- Simpler to implement
- Works with all MCP clients
- Lower overhead than WebSocket
- Standard for MCP protocol

### Hot-Reload Strategy
When config changes:
1. File watcher detects change
2. Parse and validate new config
3. Stop removed servers gracefully
4. Start new servers
5. Update tool metadata
6. **Client connections stay alive** (zero-downtime)

---

## Implementation Phases

### Phase 1: MVP (3-4 hours) ← START HERE
Build core functionality:
- HTTP SSE server
- Stdio server spawning
- Tool aggregation
- Config loading
- Basic error handling

Deliverable: Working gateway for 3-5 servers

### Phase 2: Polish (2-3 hours)
Production-ready:
- Hot-reload watcher
- Comprehensive logging
- Graceful transitions
- Process recovery
- Container setup

Deliverable: Production-ready for 10+ servers

### Phase 3: Deploy (1-2 hours)
Go live:
- Quadlet file
- Full config
- Testing
- MetaMCP migration
- Documentation

Deliverable: Live on server2, MetaMCP replaced

---

## Current State Analysis

### Confirmed Information
- **Running**: Playwright MCP server (docker container)
- **Failed**: MetaMCP (OOM/exit code 137)
- **Quadlet**: `/etc/containers/systemd/mcp-metamcp.container` exists
- **Config**: Missing from `/srv/containers/metamcp/` (lost?)
- **Servers**: Playwright at minimum, 5-8+ expected from MetaMCP

### Action Items Before Implementation
1. Extract MetaMCP quadlet config details
2. Identify all 10+ stdio server commands
3. List all required environment variables
4. Create initial mcp-servers.json template

---

## Success Criteria

When MCProxy is complete, you'll have:

✅ **Replaced MetaMCP** with cleaner, simpler solution
✅ **10+ MCP servers aggregated** into single endpoint
✅ **Hot-reload working** without restart
✅ **Zero authentication** (internal use)
✅ **Syslog logging** for ops integration
✅ **<100MB memory footprint** (vs MetaMCP OOM)
✅ **Set-and-forget deployment** (no manual intervention)
✅ **Code you understand** (500 lines, well-documented)

---

## Timeline

| Phase | Duration | Cumulative |
|-------|----------|-----------|
| Phase 1 MVP | 3-4 hours | 3-4h |
| Phase 2 Polish | 2-3 hours | 5-7h |
| Phase 3 Deploy | 1-2 hours | 6-9h |

**Total**: 6-9 hours of development + 1-2 hours of gathering server info

---

## Deployment Details

### Where It Runs
- **Server**: server2 (where MetaMCP was)
- **Container**: Podman system-level
- **Quadlet**: `/etc/containers/systemd/mcp-gateway.container`
- **Config**: `/srv/containers/mcp-gateway/mcp-servers.json` (hot-reloaded)
- **Port**: 12009 (local network access)

### How Clients Connect
```
Claude Desktop → http://localhost:12009/sse
Cursor         → http://localhost:12009/sse
VS Code        → http://localhost:12009/sse
```

### Operations
```bash
# Start
sudo systemctl start mcp-gateway.service

# View logs
sudo journalctl -u mcp-gateway.service -f

# Edit config (auto-reloads)
vim /srv/containers/mcp-gateway/mcp-servers.json

# Add/remove/enable/disable servers just by editing JSON
```

---

## Key Files to Create

```
/srv/containers/mcp-gateway/
├── main.py                    (50 lines)
├── server.py                  (100 lines)
├── server_manager.py          (150 lines)
├── config_watcher.py          (80 lines)
├── tool_aggregator.py         (100 lines)
├── logging_config.py          (60 lines)
├── mcp-servers.json           (config)
├── requirements.txt           (4 deps)
├── Dockerfile                 (10 lines)
└── README.md                  (docs)

/etc/containers/systemd/
└── mcp-gateway.container      (systemd quadlet)
```

Total: ~540 lines of Python code

---

## Risks & Mitigations

| Risk | Probability | Mitigation |
|------|-------------|-----------|
| Subprocess management tricky | Low | Use proven patterns from Magg |
| Config hot-reload complexity | Low | Comprehensive validation + testing |
| Memory leaks in long-running | Low | Process monitoring + periodic health checks |
| Network/SSE issues | Low | Use battle-tested MCP SDK |
| Deployment hiccups | Low | Careful quadlet setup + testing |

All risks are Low due to using proven patterns, not inventing new ones.

---

## Why This Is The Right Call

1. **Exact Match**: Requirements → Design → Implementation (no waste)
2. **Ownership**: You understand every line (vs black box Obot)
3. **Simplicity**: 500 LoC vs 100K LoC (vs Obot)
4. **Hot-Reload**: Built-in from day 1 (vs second-thought feature)
5. **Proven**: Patterns borrowed from Magg (production-ready)
6. **Reliable**: No Better Auth bugs, no OOM crashes
7. **Maintainable**: Future changes trivial (not trapped in monolith)

---

## Next Steps

**BEFORE IMPLEMENTATION**:
1. Review this decision summary (5 min)
2. Review specification document (20 min)
3. Review implementation guide (15 min)
4. Ask clarifying questions if any (respond to this doc)

**READY TO IMPLEMENT?**:
1. Confirm you want to proceed with custom Python route
2. Confirm ports (12009) and paths (/srv/containers/mcp-gateway/)
3. Confirm you have access to extract MetaMCP servers
4. Then: Begin Phase 1 MVP

---

## Documents Created

For your reference:

1. **mcproxy_spec.md** - Complete specification
   - Requirements, architecture, configuration, deployment
   - 200+ lines of detailed reference

2. **mcproxy_implementation_guide.md** - Step-by-step coding guide
   - Phase 1, 2, 3 with code examples
   - Testing strategy, pitfalls to avoid
   - Estimated 300+ lines

3. **mcproxy_decision_summary.md** (this file)
   - Why this decision, timeline, next steps

All documents in: `/home/bk/.opencode/plan/`

---

**Decision**: ✅ Custom Python MCProxy
**Status**: Ready for Implementation
**Target Start**: Immediately after your confirmation
**Estimated Delivery**: 6-9 hours
**Expected Go-Live**: This week

