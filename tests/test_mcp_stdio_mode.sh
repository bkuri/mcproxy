#!/bin/bash
# Test MCProxy as native MCP server over stdio
#
# This script tests MCProxy running in --stdio mode, which makes it a native MCP
# server that can be used directly with MCP clients.
#
# Usage: bash tests/test_mcp_stdio_mode.sh
#
# Tests:
# 1. Initialize MCP protocol
# 2. List all aggregated tools
# 3. Call various tools (fear_greed, think_tool, sequential_thinking, etc.)

set -e

echo "============================================================"
echo "MCProxy Native MCP Server Test (--stdio mode)"
echo "============================================================"
echo ""

# Create a temporary Python script to test MCProxy
TEST_SCRIPT=$(mktemp)
cat > "$TEST_SCRIPT" << 'PYTEST'
#!/usr/bin/env python3
import json
import subprocess
import sys
import time

def send_request(proc, request):
    """Send MCP request and get response."""
    proc.stdin.write(json.dumps(request) + "\n")
    proc.stdin.flush()
    time.sleep(0.5)
    
    try:
        response = proc.stdout.readline()
        if response:
            return json.loads(response)
    except json.JSONDecodeError:
        pass
    return None

def main():
    print("Starting MCProxy in stdio mode...", file=sys.stderr)
    
    proc = subprocess.Popen(
        ["python", "./main.py", "--stdio", "--config", "mcp-servers.json"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
        cwd="/home/bk/source/mcproxy"
    )
    
    # Wait for servers to start
    time.sleep(12)
    
    tests_passed = 0
    tests_failed = 0
    
    try:
        # Test 1: Initialize
        print("\n[TEST 1] Initialize MCP server", file=sys.stderr)
        init_req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"}
            }
        }
        resp = send_request(proc, init_req)
        
        if resp and resp.get('id') == 1 and 'result' in resp:
            print("✓ PASS: Initialize successful", file=sys.stderr)
            tests_passed += 1
        else:
            print("✗ FAIL: Initialize failed", file=sys.stderr)
            tests_failed += 1
        
        # Send initialized notification
        init_notif = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {}
        }
        proc.stdin.write(json.dumps(init_notif) + "\n")
        proc.stdin.flush()
        time.sleep(0.5)
        
        # Test 2: List tools
        print("\n[TEST 2] List available tools", file=sys.stderr)
        list_req = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }
        resp = send_request(proc, list_req)
        
        if resp and 'result' in resp:
            tools = resp.get('result', {}).get('tools', [])
            if tools:
                print(f"✓ PASS: Found {len(tools)} tool(s)", file=sys.stderr)
                print(f"        Available tools: {[t['name'] for t in tools]}", file=sys.stderr)
                tests_passed += 1
            else:
                print("✗ FAIL: No tools found", file=sys.stderr)
                tests_failed += 1
        else:
            print("✗ FAIL: Could not list tools", file=sys.stderr)
            tests_failed += 1
        
        # Test 3: Call fear_greed_index tool
        print("\n[TEST 3] Call fear_greed_index__get_fear_greed_index", file=sys.stderr)
        call_req = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "call_tool",
                "arguments": {
                    "name": "fear_greed_index__get_fear_greed_index",
                    "arguments": {}
                }
            }
        }
        resp = send_request(proc, call_req)
        time.sleep(1)  # Extra wait for tool execution
        if not resp:
            resp = send_request(proc, call_req)
        
        if resp and 'result' in resp:
            content = resp.get('result', {}).get('content', [])
            if content and not resp.get('result', {}).get('isError'):
                print("✓ PASS: Tool call successful", file=sys.stderr)
                tests_passed += 1
            else:
                print("✗ FAIL: Tool returned error", file=sys.stderr)
                tests_failed += 1
        else:
            print("✗ FAIL: No response from tool", file=sys.stderr)
            tests_failed += 1
        
        # Test 4: Call think_tool
        print("\n[TEST 4] Call think_tool__think", file=sys.stderr)
        call_req = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "call_tool",
                "arguments": {
                    "name": "think_tool__think",
                    "arguments": {"thought": "What is 2+2?"}
                }
            }
        }
        resp = send_request(proc, call_req)
        time.sleep(2)  # Extra wait for tool execution
        if not resp:
            resp = send_request(proc, call_req)
        
        if resp and 'result' in resp:
            content = resp.get('result', {}).get('content', [])
            if content and not resp.get('result', {}).get('isError'):
                print("✓ PASS: Tool call successful", file=sys.stderr)
                tests_passed += 1
            else:
                print("✗ FAIL: Tool returned error", file=sys.stderr)
                tests_failed += 1
        else:
            print("✗ FAIL: No response from tool", file=sys.stderr)
            tests_failed += 1
        
        # Test 5: Call sequential_thinking
        print("\n[TEST 5] Call sequential_thinking__sequentialthinking", file=sys.stderr)
        call_req = {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "call_tool",
                "arguments": {
                    "name": "sequential_thinking__sequentialthinking",
                    "arguments": {
                        "thought": "What is 2+2?",
                        "thoughtNumber": 1,
                        "totalThoughts": 2,
                        "nextThoughtNeeded": True
                    }
                }
            }
        }
        resp = send_request(proc, call_req)
        time.sleep(2)
        if not resp:
            resp = send_request(proc, call_req)
        
        if resp and 'result' in resp:
            content = resp.get('result', {}).get('content', [])
            if content and not resp.get('result', {}).get('isError'):
                print("✓ PASS: Tool call successful", file=sys.stderr)
                tests_passed += 1
            else:
                print("✗ FAIL: Tool returned error", file=sys.stderr)
                tests_failed += 1
        else:
            print("✗ FAIL: No response from tool", file=sys.stderr)
            tests_failed += 1
        
        # Summary
        print("\n" + "="*60, file=sys.stderr)
        print(f"Test Results: {tests_passed} passed, {tests_failed} failed", file=sys.stderr)
        print("="*60, file=sys.stderr)
        
        if tests_failed == 0:
            print("\n✓ All tests passed! MCProxy is working as an MCP server.", file=sys.stderr)
            sys.exit(0)
        else:
            print(f"\n✗ {tests_failed} test(s) failed.", file=sys.stderr)
            sys.exit(1)
        
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

if __name__ == "__main__":
    main()
PYTEST

# Run the test
python3 "$TEST_SCRIPT"
RESULT=$?

# Cleanup
rm -f "$TEST_SCRIPT"

exit $RESULT
