# Testing MCProxy Thinking Tools

MCProxy includes 4 thinking/reasoning tools for complex problem-solving:

## Tool Overview

### 1. Think Tool (`think_tool__think`)
- **Purpose**: Simple reasoning space for thinking about problems
- **Best for**: Quick single-thought analysis, brainstorming
- **Complexity**: ⭐ Simple (1 parameter)
- **Parameters**: `thought` (string)
- **Output**: Structured thinking response

### 2. Sequential Thinking (`sequential_thinking__sequentialthinking`)
- **Purpose**: Multi-step structured reasoning with branching support
- **Best for**: Step-by-step problem solving, decision trees
- **Complexity**: ⭐⭐⭐ Complex (9 parameters)
- **Key Parameters**:
  - `thought`: Current step
  - `thoughtNumber`: Step number (1-indexed)
  - `totalThoughts`: Estimated total steps needed
  - `nextThoughtNeeded`: Boolean flag for continuation
  - `isRevision`: Revise previous thinking
  - `branchFromThought`: For branching logic
  - `branchId`: Identifies branch

### 3. Atom of Thoughts (AoT) (`atom_of_thoughts__AoT`)
- **Purpose**: Decompose problems into independent atomic units
- **Best for**: Complex reasoning with verification, hypothesis testing
- **Complexity**: ⭐⭐⭐ Complex (7 parameters)
- **Atom Types**: premise, reasoning, hypothesis, verification, conclusion
- **Key Features**:
  - Atomic decomposition
  - Dependency tracking
  - Confidence scoring (0-1)
  - Verification mechanism
  - Depth tracking

### 4. AoT-Light (`atom_of_thoughts__AoT-light`)
- **Purpose**: Lightweight version of AoT for faster responses
- **Best for**: Time-sensitive reasoning, quick analysis
- **Complexity**: ⭐⭐ Moderate (6 parameters)
- **Key Differences from AoT**:
  - Lower maximum depth (3 vs 5)
  - Simplified verification
  - Faster processing
  - Reduced overhead

---

## Testing Strategies

### Strategy 1: Single-Tool Direct Test
Test each tool individually with a simple problem.

```bash
# Think Tool
curl -X POST http://192.168.50.71:12010/sse \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "think_tool__think",
      "arguments": {
        "thought": "What is the best approach to scaling a distributed system?"
      }
    }
  }'
```

### Strategy 2: Multi-Step Sequential Test
Chain multiple sequential thinking steps together.

```bash
# Step 1: Initial analysis
curl -X POST http://192.168.50.71:12010/sse \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "sequential_thinking__sequentialthinking",
      "arguments": {
        "thought": "First, consider the problem statement and constraints",
        "thoughtNumber": 1,
        "totalThoughts": 5,
        "nextThoughtNeeded": true
      }
    }
  }'

# Step 2: Build on previous
curl -X POST http://192.168.50.71:12010/sse \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "sequential_thinking__sequentialthinking",
      "arguments": {
        "thought": "Next, identify potential solution approaches",
        "thoughtNumber": 2,
        "totalThoughts": 5,
        "nextThoughtNeeded": true
      }
    }
  }'
```

### Strategy 3: Atomic Reasoning Test
Build a hypothesis with supporting atoms and verification.

```bash
# Premise: Establish base facts
curl -X POST http://192.168.50.71:12010/sse \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "atom_of_thoughts__AoT",
      "arguments": {
        "atomId": "P1",
        "content": "The problem involves scaling a system with 10M+ users",
        "atomType": "premise",
        "dependencies": [],
        "confidence": 0.95
      }
    }
  }'

# Hypothesis: Propose solution
curl -X POST http://192.168.50.71:12010/sse \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {
      "name": "atom_of_thoughts__AoT",
      "arguments": {
        "atomId": "H1",
        "content": "Database sharding with consistent hashing is the optimal solution",
        "atomType": "hypothesis",
        "dependencies": ["P1"],
        "confidence": 0.75
      }
    }
  }'

# Verification: Evaluate hypothesis
curl -X POST http://192.168.50.71:12010/sse \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
      "name": "atom_of_thoughts__AoT",
      "arguments": {
        "atomId": "V1",
        "content": "Database sharding handles horizontal scaling and improves query performance",
        "atomType": "verification",
        "dependencies": ["H1"],
        "confidence": 0.9
      }
    }
  }'

# Conclusion: Draw conclusion
curl -X POST http://192.168.50.71:12010/sse \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 4,
    "method": "tools/call",
    "params": {
      "name": "atom_of_thoughts__AoT",
      "arguments": {
        "atomId": "C1",
        "content": "Database sharding is the recommended approach for scaling to 10M+ users",
        "atomType": "conclusion",
        "dependencies": ["H1", "V1"],
        "confidence": 0.95
      }
    }
  }'
```

### Strategy 4: Comparison Test
Run same problem through all thinking tools and compare approaches.

**Problem**: "How should we design a cache for high-traffic API?"

1. **Think Tool**: Single comprehensive thought
2. **Sequential Thinking**: Break into 4-5 steps
3. **AoT**: Build atomic premises, hypotheses, verifications
4. **AoT-Light**: Quick atomic analysis

### Strategy 5: Edge Case Testing
- Empty thoughts
- Very long thoughts
- Circular dependencies (AoT)
- High confidence vs low confidence
- Multiple revisions (Sequential)

---

## Test Execution

Run comprehensive test suite:

```bash
# Quick test all 4 tools
./tests/test_thinking_tools_quick.sh

# Comprehensive multi-step test
./tests/test_thinking_tools_comprehensive.sh

# Stress test with 50 concurrent requests
./tests/test_thinking_tools_stress.sh

# Compare outputs
./tests/test_thinking_tools_compare.sh
```

---

## Expected Behaviors

### Think Tool
- Returns formatted thinking response
- Instant response
- No state maintained between calls

### Sequential Thinking
- Returns thought tracking data
- Supports continuous thinking
- Can revise previous thoughts
- Can branch into alternatives
- Maintains internal state

### Atom of Thoughts
- Builds dependency graph
- Tracks verification status
- Returns comprehensive reasoning structure
- Supports decomposition/contraction
- Slower but more thorough

### AoT-Light
- Similar to AoT but constrained
- Faster processing
- Max depth of 3
- Good for time-sensitive decisions

---

## Success Criteria

✅ All tools return without errors  
✅ Responses contain expected structure  
✅ Tools work together in sequence  
✅ Complex problems get detailed responses  
✅ Performance is acceptable (<5s per call)  

---

## Known Limitations

1. **Sequential Thinking**: Maintains local state per call (no cross-call memory)
2. **AoT**: Can become complex with many atoms
3. **Think Tool**: Best for simple thoughts (doesn't branch)
4. **All tools**: Require explicit structuring by caller

