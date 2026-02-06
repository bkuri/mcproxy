# MCProxy Thinking Tools - Quick Reference

## When to Use Each Tool

### 🧠 Think Tool (`think_tool__think`)
**Best for:** Quick brainstorming, simple analysis  
**Complexity:** ⭐ Simple  
**API:** 1 required parameter  
**Response time:** ~1 second  
**Max use:** One-off thoughts

```bash
curl -X POST http://192.168.50.71:12010/sse \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "think_tool__think",
      "arguments": {
        "thought": "Your question or problem here"
      }
    }
  }'
```

**Use case example:**
- "What are the pros and cons of REST vs GraphQL?"
- "How should I approach this coding problem?"
- "What factors make a good API design?"

---

### 📋 Sequential Thinking (`sequential_thinking__sequentialthinking`)
**Best for:** Step-by-step problem solving, decision trees  
**Complexity:** ⭐⭐⭐ Complex  
**API:** 9 parameters (thought, thoughtNumber, totalThoughts, etc.)  
**Response time:** ~2 seconds per step  
**Max use:** Multi-step reasoning chains  

**Key parameters:**
- `thought`: Current step content
- `thoughtNumber`: Which step (1, 2, 3...)
- `totalThoughts`: Estimated total steps
- `nextThoughtNeeded`: Boolean for continuation
- `isRevision`: True if reconsidering previous thought
- `branchFromThought`: For alternative paths

**Use case example:**
```
Step 1: Define the problem
Step 2: List constraints
Step 3: Brainstorm solutions
Step 4: Evaluate trade-offs
Step 5: Recommend action
```

---

### ⚛️ Atom of Thoughts (AoT) (`atom_of_thoughts__AoT`)
**Best for:** Complex reasoning, verification, decomposition  
**Complexity:** ⭐⭐⭐ Complex  
**API:** 7 parameters (atomId, content, atomType, dependencies, confidence, etc.)  
**Response time:** ~3 seconds  
**Max use:** Deep analysis with verification  

**Atom types:**
- `premise`: Base facts/assumptions
- `reasoning`: Logical deduction
- `hypothesis`: Proposed solutions
- `verification`: Evaluation of hypotheses
- `conclusion`: Final answer

**Best for decomposing problems into:**
- Base facts → Reasoning → Hypotheses → Verification → Conclusion
- Handles dependencies between atoms
- Tracks confidence (0-1) for each atom
- Supports depth tracking

**Use case example:**
- Technical architecture decisions
- Complex business strategies
- Research problems with multiple verification steps
- Scientific hypotheses

---

### ⚡ AoT-Light (`atom_of_thoughts__AoT-light`)
**Best for:** Time-sensitive atomic reasoning  
**Complexity:** ⭐⭐ Moderate  
**API:** 6 parameters (simpler than AoT)  
**Response time:** ~1.5 seconds  
**Max use:** Quick analysis with structure  

**Differences from full AoT:**
- Max depth: 3 (vs 5 in full AoT)
- Simplified verification
- Faster processing
- Reduced computational overhead

**Use case example:**
- Rapid competitive analysis
- Quick risk assessments
- Time-constrained decisions
- Initial exploration before full AoT

---

## Quick Decision Tree

```
Is your problem time-sensitive?
├─ YES, just one thought → Use Think Tool
├─ YES, needs verification → Use AoT-Light
└─ NO
   └─ Does it need step-by-step approach?
      ├─ YES, with alternatives → Use Sequential Thinking
      └─ YES, with verification → Use AoT
```

---

## Running All Tests

```bash
# Quick test all 4 tools
cd /home/bk/source/mcproxy
bash tests/test_thinking_tools_comparison.sh

# Or run against different server
bash tests/test_thinking_tools_comparison.sh http://your-server:12010
```

---

## API Reference

### Think Tool
```json
{
  "name": "think_tool__think",
  "arguments": {
    "thought": "string (required)"
  }
}
```

### Sequential Thinking
```json
{
  "name": "sequential_thinking__sequentialthinking",
  "arguments": {
    "thought": "string (required)",
    "thoughtNumber": "integer (required)",
    "totalThoughts": "integer (required)",
    "nextThoughtNeeded": "boolean (required)",
    "isRevision": "boolean (optional)",
    "revisesThought": "integer (optional)",
    "branchFromThought": "integer (optional)",
    "branchId": "string (optional)",
    "needsMoreThoughts": "boolean (optional)"
  }
}
```

### Atom of Thoughts
```json
{
  "name": "atom_of_thoughts__AoT",
  "arguments": {
    "atomId": "string (required)",
    "content": "string (required)",
    "atomType": "enum (required): premise|reasoning|hypothesis|verification|conclusion",
    "dependencies": "array[string] (required)",
    "confidence": "number 0-1 (required)",
    "isVerified": "boolean (optional)",
    "depth": "number (optional)"
  }
}
```

### AoT-Light
```json
{
  "name": "atom_of_thoughts__AoT-light",
  "arguments": {
    "atomId": "string (required)",
    "content": "string (required)",
    "atomType": "enum (required): premise|reasoning|hypothesis|verification|conclusion",
    "dependencies": "array[string] (required)",
    "confidence": "number 0-1 (required)",
    "depth": "number (optional)"
  }
}
```

---

## Performance Benchmarks

| Tool | Response Time | Complexity | Best For |
|------|---|---|---|
| Think | ~1s | Simple | Single thoughts |
| Sequential | ~2s/step | Complex | Multi-step reasoning |
| AoT | ~3s | Complex | Deep analysis |
| AoT-Light | ~1.5s | Moderate | Quick analysis |

---

## Example Problems & Best Tool

| Problem | Best Tool | Why |
|---------|-----------|-----|
| "Summarize this article" | Think Tool | Single thought needed |
| "Design API architecture" | AoT | Complex with verification |
| "Decision tree analysis" | Sequential | Step-by-step branching |
| "Quick code review" | AoT-Light | Atomic feedback, time-constrained |
| "What is X?" | Think Tool | Quick answer |
| "What is X and why?" | AoT-Light | Reasoning with structure |
| "Build complete strategy" | AoT | Full analysis needed |

