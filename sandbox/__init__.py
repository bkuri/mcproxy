"""Sandbox execution system for MCProxy v2.0.

Provides secure code execution via uv subprocess with namespace-based access control.
"""

from sandbox.access_control import NamespaceAccessControl, SandboxManifest
from sandbox.executor import SandboxExecutor
from sandbox.factory import create_sandbox_executor
from sandbox.proxy import DynamicProxy, ProxyAPI
from sandbox.security import (
    BLOCKED_BUILTINS,
    BLOCKED_IMPORTS,
    FUZZY_MATCH_THRESHOLD,
    MAX_CODE_SIZE_BYTES,
    MAX_SUGGESTIONS,
    suggest_tool_fix,
)

__all__ = [
    "SandboxExecutor",
    "SandboxManifest",
    "NamespaceAccessControl",
    "ProxyAPI",
    "DynamicProxy",
    "create_sandbox_executor",
    "suggest_tool_fix",
    "BLOCKED_IMPORTS",
    "BLOCKED_BUILTINS",
    "MAX_CODE_SIZE_BYTES",
    "FUZZY_MATCH_THRESHOLD",
    "MAX_SUGGESTIONS",
]
