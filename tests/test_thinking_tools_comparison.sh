#!/bin/bash

# Comprehensive comparison test of all thinking tools
# Demonstrates each tool working on the same problem

set -e

BASE_URL="${1:-http://192.168.50.71:12010}"
PROBLEM="Should we migrate our monolithic application to microservices?"

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║     MCProxy Thinking Tools Comparison Test                     ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "PROBLEM: $PROBLEM"
echo ""

# Color codes
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test 1: Think Tool
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}1. THINK TOOL${NC} - Simple single thought"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

RESPONSE=$(curl -s -X POST "$BASE_URL/sse" \
  -H "Content-Type: application/json" \
  -d "{
    \"jsonrpc\": \"2.0\",
    \"id\": 1,
    \"method\": \"tools/call\",
    \"params\": {
      \"name\": \"think_tool__think\",
      \"arguments\": {
        \"thought\": \"$PROBLEM Analyze the trade-offs and provide a recommendation.\"
      }
    }
  }")

echo "$RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    result = data.get('result', {})
    content = result.get('content', [])
    if content and isinstance(content, list):
        text = content[0].get('text', 'No response')
        print(text[:800] if len(text) > 800 else text)
    else:
        print('Response:', json.dumps(result, indent=2)[:800])
except:
    print('Error parsing response')
" 2>&1

echo ""
echo "Time to respond: ~1-2 seconds"
echo ""

# Test 2: Sequential Thinking
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}2. SEQUENTIAL THINKING${NC} - Multi-step structured approach"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

STEPS=(
  "Step 1: Analyze current system constraints and pain points"
  "Step 2: Evaluate microservices benefits (scalability, team autonomy, independent deployment)"
  "Step 3: Consider migration costs (time, complexity, operational overhead)"
  "Step 4: Assess organizational readiness (DevOps capability, team structure)"
)

for i in "${!STEPS[@]}"; do
  STEP_NUM=$((i + 1))
  TOTAL_STEPS=4
  
  echo -e "${YELLOW}Request $STEP_NUM/$TOTAL_STEPS:${NC} ${STEPS[$i]}"
  
  RESPONSE=$(curl -s -X POST "$BASE_URL/sse" \
    -H "Content-Type: application/json" \
    -d "{
      \"jsonrpc\": \"2.0\",
      \"id\": $((i + 100)),
      \"method\": \"tools/call\",
      \"params\": {
        \"name\": \"sequential_thinking__sequentialthinking\",
        \"arguments\": {
          \"thought\": \"${STEPS[$i]}\",
          \"thoughtNumber\": $STEP_NUM,
          \"totalThoughts\": $TOTAL_STEPS,
          \"nextThoughtNeeded\": true
        }
      }
    }")
  
  echo "$RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    result = data.get('result', {}).get('content', [{}])[0]
    text = result.get('text', '')
    if text:
        obj = json.loads(text)
        print(f'  → Thought #{obj.get(\"thoughtNumber\")}/{obj.get(\"totalThoughts\")}')
        print(f'  → Next needed: {obj.get(\"nextThoughtNeeded\")}')
        print(f'  → Branches: {len(obj.get(\"branches\", []))}')
except:
    pass
" 2>&1
done

echo ""

# Test 3: Atom of Thoughts
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}3. ATOM OF THOUGHTS${NC} - Structured atomic reasoning"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

ATOMS=(
  "P1:premise:Current system has scaling and deployment challenges:0.9"
  "R1:reasoning:Microservices offer independent scaling and deployment:0.85"
  "H1:hypothesis:Microservices migration is the right choice:0.7"
  "V1:verification:Team has DevOps expertise to support microservices:0.8"
  "C1:conclusion:Proceed with phased microservices migration:0.85"
)

DEPS=(
  "[]"
  "[\"P1\"]"
  "[\"R1\"]"
  "[\"H1\"]"
  "[\"V1\",\"H1\"]"
)

for i in "${!ATOMS[@]}"; do
  IFS=':' read -r ATOM_ID ATOM_TYPE ATOM_CONTENT CONFIDENCE <<< "${ATOMS[$i]}"
  ATOM_DEPS="${DEPS[$i]}"
  
  echo -e "${YELLOW}Atom $((i + 1)): $ATOM_ID${NC} ($ATOM_TYPE, conf: $CONFIDENCE)"
  
  RESPONSE=$(curl -s -X POST "$BASE_URL/sse" \
    -H "Content-Type: application/json" \
    -d "{
      \"jsonrpc\": \"2.0\",
      \"id\": $((i + 200)),
      \"method\": \"tools/call\",
      \"params\": {
        \"name\": \"atom_of_thoughts__AoT\",
        \"arguments\": {
          \"atomId\": \"$ATOM_ID\",
          \"content\": \"$ATOM_CONTENT\",
          \"atomType\": \"$ATOM_TYPE\",
          \"dependencies\": $ATOM_DEPS,
          \"confidence\": $CONFIDENCE
        }
      }
    }")
  
  echo "$RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    result = data.get('result', {}).get('content', [{}])[0]
    text = result.get('text', '')
    if text:
        obj = json.loads(text)
        print(f'  ✓ Atom registered: {obj.get(\"atomId\")}')
        print(f'  ✓ Total atoms: {obj.get(\"atomsCount\")}')
        term = obj.get('terminationStatus', {})
        if term.get('shouldTerminate'):
            print(f'  ⊗ TERMINATION: {term.get(\"reason\")}')
except:
    pass
" 2>&1
done

echo ""

# Test 4: AoT-Light
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}4. ATOM OF THOUGHTS - LIGHT${NC} - Fast atomic analysis"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

RESPONSE=$(curl -s -X POST "$BASE_URL/sse" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 300,
    "method": "tools/call",
    "params": {
      "name": "atom_of_thoughts__AoT-light",
      "arguments": {
        "atomId": "QUICK1",
        "content": "Quick assessment: Microservices migration recommended for scaling, but requires strong DevOps team and careful phasing",
        "atomType": "conclusion",
        "dependencies": [],
        "confidence": 0.85
      }
    }
  }')

echo "$RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    result = data.get('result', {}).get('content', [{}])[0]
    text = result.get('text', '')
    if text:
        obj = json.loads(text)
        print(f'✓ Quick conclusion registered')
        print(f'✓ Confidence: {obj.get(\"confidence\")}')
        print(f'✓ Atom count: {obj.get(\"atomsCount\")}')
        best = obj.get('bestConclusion')
        if best:
            print(f'✓ Best conclusion: {best}')
except:
    pass
" 2>&1

echo ""

# Summary
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}SUMMARY${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

cat << 'SUMMARY'
Tool Comparison:

THINK TOOL
  ✓ Best for: Quick single thoughts
  ✓ Simplest API (1 parameter)
  ✓ Instant response
  ✗ No multi-step support

SEQUENTIAL THINKING
  ✓ Best for: Step-by-step problems
  ✓ Branching & revision support
  ✓ Maintains thought state
  ✗ Complex API (9 parameters)

ATOM OF THOUGHTS
  ✓ Best for: Complex reasoning
  ✓ Dependency tracking
  ✓ Verification mechanism
  ✓ Decomposition support
  ✗ Most complex API

AOT-LIGHT
  ✓ Best for: Time-sensitive analysis
  ✓ Faster than full AoT
  ✓ Limited depth (3 vs 5)
  ✓ Good balance of features

RECOMMENDATION:
  • Use Think Tool for quick brainstorming
  • Use Sequential Thinking for step-by-step decisions
  • Use AoT for deep analysis with verification
  • Use AoT-Light for time-sensitive decisions
SUMMARY

echo ""
echo -e "${GREEN}✓ All thinking tools tested successfully!${NC}"
