"""Shared pytest fixtures for MCProxy v2.0 tests."""

import pytest
from typing import Any, Dict, List

from api_manifest import CapabilityRegistry
from api_sandbox import SandboxManifest, NamespaceAccessControl


@pytest.fixture
def sample_servers_tools() -> Dict[str, List[Dict[str, Any]]]:
    """Sample server tools data for testing."""
    return {
        "playwright": [
            {
                "name": "playwright__navigate",
                "description": "Navigate to a URL",
                "inputSchema": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"],
                },
            },
            {
                "name": "playwright__click",
                "description": "Click an element",
                "inputSchema": {
                    "type": "object",
                    "properties": {"selector": {"type": "string"}},
                    "required": ["selector"],
                },
            },
            {
                "name": "playwright__screenshot",
                "description": "Take a screenshot",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ],
        "filesystem": [
            {
                "name": "filesystem__read_file",
                "description": "Read file contents",
                "inputSchema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
            {
                "name": "filesystem__write_file",
                "description": "Write content to file",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            },
        ],
        "crypto": [
            {
                "name": "crypto__hash",
                "description": "Hash a string",
                "inputSchema": {
                    "type": "object",
                    "properties": {"data": {"type": "string"}},
                    "required": ["data"],
                },
            },
            {
                "name": "crypto__encrypt",
                "description": "Encrypt data",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "data": {"type": "string"},
                        "key": {"type": "string"},
                    },
                    "required": ["data", "key"],
                },
            },
        ],
        "system": [
            {
                "name": "system__execute",
                "description": "Execute a system command",
                "inputSchema": {
                    "type": "object",
                    "properties": {"cmd": {"type": "string"}},
                    "required": ["cmd"],
                },
            },
        ],
    }


@pytest.fixture
def sample_namespaces() -> Dict[str, Any]:
    """Sample namespace configuration for testing."""
    return {
        "browser": ["playwright"],
        "files": ["filesystem"],
        "security": ["crypto"],
        "admin": ["playwright", "filesystem", "crypto", "system"],
        "browser_and_files": {
            "servers": ["playwright", "filesystem"],
            "extends": [],
        },
        "privileged": {
            "servers": ["system"],
            "extends": ["browser_and_files"],
        },
        "circular_a": {
            "servers": ["playwright"],
            "extends": ["circular_b"],
        },
        "circular_b": {
            "servers": ["filesystem"],
            "extends": ["circular_a"],
        },
    }


@pytest.fixture
def sample_manifest(
    sample_servers_tools: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Built manifest from sample server tools."""
    registry = CapabilityRegistry()
    return registry.build(sample_servers_tools)


@pytest.fixture
def sandbox_manifest(
    sample_servers_tools: Dict[str, List[Dict[str, Any]]],
    sample_namespaces: Dict[str, Any],
) -> SandboxManifest:
    """Sample sandbox manifest for access control testing."""
    servers = {}
    for server_name, tools in sample_servers_tools.items():
        servers[server_name] = {
            "tools": [t["name"] for t in tools],
            "tool_count": len(tools),
        }

    normalized_namespaces = {}
    for ns_name, ns_config in sample_namespaces.items():
        if isinstance(ns_config, list):
            normalized_namespaces[ns_name] = {"servers": ns_config, "extends": []}
        else:
            normalized_namespaces[ns_name] = ns_config

    return SandboxManifest(
        servers=servers,
        namespaces=normalized_namespaces,
    )


@pytest.fixture
def namespace_access_control(
    sandbox_manifest: SandboxManifest,
) -> NamespaceAccessControl:
    """Namespace access control instance for testing."""
    return NamespaceAccessControl(sandbox_manifest)


@pytest.fixture
def sample_v2_config() -> Dict[str, Any]:
    """Sample v2.0 configuration for testing."""
    return {
        "servers": [
            {
                "name": "playwright",
                "command": "npx",
                "args": ["-y", "@anthropic-ai/mcp-server-playwright"],
            },
            {
                "name": "filesystem",
                "command": "npx",
                "args": ["-y", "@anthropic-ai/mcp-server-filesystem"],
            },
        ],
        "namespaces": {
            "browser": ["playwright"],
            "files": ["filesystem"],
            "combined": {
                "servers": ["playwright"],
                "extends": ["files"],
            },
        },
        "manifests": {
            "startup_dwell_secs": 2.0,
            "per_server_ttl": {"default_secs": 300},
        },
        "sandbox": {
            "timeout_secs": 30,
            "memory_mb": 256,
        },
    }
