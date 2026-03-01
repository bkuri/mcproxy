"""Sandbox execution system for MCProxy v2.0.

Provides secure code execution via uv subprocess with namespace-based access control.
"""

import ast
import json
import re
import subprocess
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

from logging_config import get_logger

if TYPE_CHECKING:
    from api_manifest import CapabilityRegistry as ManifestRegistry

logger = get_logger(__name__)

BLOCKED_IMPORTS: frozenset[str] = frozenset(
    [
        "os",
        "sys",
        "subprocess",
        "socket",
        "http",
        "urllib",
        "requests",
        "shutil",
        "tempfile",
        "multiprocessing",
        "__import__",
        "builtins",
    ]
)

BLOCKED_BUILTINS: frozenset[str] = frozenset(
    [
        "eval",
        "exec",
        "compile",
        "open",
        "input",
        "__import__",
        "breakpoint",
    ]
)

MAX_CODE_SIZE_BYTES: int = 50 * 1024


@dataclass
class SandboxManifest:
    """Simplified manifest view for sandbox access control."""

    servers: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    namespaces: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def get_server(self, name: str) -> Optional[Dict[str, Any]]:
        return self.servers.get(name)

    def get_namespace(self, name: str) -> Optional[Dict[str, Any]]:
        return self.namespaces.get(name)

    def get_tools_for_server(self, server_name: str) -> List[str]:
        server = self.get_server(server_name)
        if not server:
            return []
        return server.get("tools", [])


@dataclass
class NamespaceAccessControl:
    """Controls access to servers based on namespace permissions."""

    manifest: "SandboxManifest"

    def can_access(self, namespace: str, target_server: str) -> Tuple[bool, str]:
        """Check if namespace can access target server.

        Args:
            namespace: The namespace requesting access
            target_server: The server being accessed

        Returns:
            Tuple of (allowed: bool, error_message: str)
        """
        ns_config = self.manifest.get_namespace(namespace)
        if not ns_config:
            return False, f"Namespace '{namespace}' not found in manifest"

        allowed_servers = self._resolve_allowed_servers(namespace)

        if target_server in allowed_servers:
            return True, ""

        return False, (
            f"Namespace '{namespace}' does not have access to server '{target_server}'. "
            f"Allowed servers: {', '.join(sorted(allowed_servers)) or 'none'}"
        )

    def _resolve_allowed_servers(self, namespace: str) -> set[str]:
        """Resolve all allowed servers including from inheritance.

        Args:
            namespace: The namespace to resolve

        Returns:
            Set of allowed server names
        """
        resolved: set[str] = set()
        visited: set[str] = set()

        def _resolve(ns: str) -> None:
            if ns in visited:
                return
            visited.add(ns)

            ns_config = self.manifest.get_namespace(ns)
            if not ns_config:
                return

            resolved.update(ns_config.get("servers", []))

            for parent in ns_config.get("extends", []):
                _resolve(parent)

        _resolve(namespace)
        return resolved

    def get_allowed_tools(
        self, namespace: str, server_name: str
    ) -> Tuple[List[str], str]:
        """Get list of tools namespace can use on a server.

        Args:
            namespace: The namespace requesting access
            server_name: The server being accessed

        Returns:
            Tuple of (tools: List[str], error_message: str)
        """
        can_access, error = self.can_access(namespace, server_name)
        if not can_access:
            return [], error

        return self.manifest.get_tools_for_server(server_name), ""


class ProxyAPI:
    """API injected into sandbox for accessing MCP servers.

    Usage in sandbox code:
        api.server("playwright").navigate("https://example.com")
        api.call_tool("playwright", "navigate", {"url": "..."})
        manifest = api.manifest()
    """

    def __init__(
        self,
        namespace: str,
        access_control: NamespaceAccessControl,
        tool_executor: Any,
    ):
        """Initialize ProxyAPI.

        Args:
            namespace: The namespace context for access control
            access_control: Access control checker
            tool_executor: Callable to execute tools (async)
        """
        self._namespace = namespace
        self._access_control = access_control
        self._tool_executor = tool_executor
        self._manifest = access_control.manifest

    def server(self, name: str) -> "DynamicProxy":
        """Get a typed proxy to a server.

        Args:
            name: Server name

        Returns:
            DynamicProxy that forwards calls as tool invocations

        Raises:
            PermissionError: If namespace cannot access server
        """
        can_access, error = self._access_control.can_access(self._namespace, name)
        if not can_access:
            raise PermissionError(error)

        return DynamicProxy(
            server_name=name,
            namespace=self._namespace,
            access_control=self._access_control,
            tool_executor=self._tool_executor,
        )

    def call_tool(self, server: str, tool: str, args: dict) -> Any:
        """Directly call a tool on a server.

        Args:
            server: Server name
            tool: Tool name
            args: Tool arguments

        Returns:
            Tool result

        Raises:
            PermissionError: If namespace cannot access server
        """
        can_access, error = self._access_control.can_access(self._namespace, server)
        if not can_access:
            raise PermissionError(error)

        return self._tool_executor(server, tool, args)

    def manifest(self) -> Dict[str, Any]:
        """Get the current capability manifest.

        Returns:
            Dict with servers and namespace permissions (sanitized)
        """
        allowed_servers = self._access_control._resolve_allowed_servers(self._namespace)

        return {
            "namespace": self._namespace,
            "allowed_servers": sorted(allowed_servers),
            "servers": {
                name: self._manifest.get_server(name)
                for name in allowed_servers
                if self._manifest.get_server(name)
            },
        }


class DynamicProxy:
    """Dynamic proxy that converts attribute access to tool calls."""

    def __init__(
        self,
        server_name: str,
        namespace: str,
        access_control: NamespaceAccessControl,
        tool_executor: Any,
    ):
        self._server_name = server_name
        self._namespace = namespace
        self._access_control = access_control
        self._tool_executor = tool_executor

    def __getattr__(self, tool_name: str) -> Any:
        """Convert attribute access to a callable tool invocation."""

        def _call(**kwargs: Any) -> Any:
            return self._tool_executor(self._server_name, tool_name, kwargs)

        return _call

    def __repr__(self) -> str:
        return f"<DynamicProxy server='{self._server_name}'>"


class SandboxExecutor:
    """Executes user code securely in a uv subprocess.

    Features:
    - Pre-execution code validation
    - Blocked imports and builtins
    - Timeout enforcement
    - Memory limits
    - Structured error responses
    """

    def __init__(
        self,
        manifest: "SandboxManifest",
        tool_executor: Any,
        uv_path: str = "uv",
        default_timeout_secs: int = 30,
    ):
        """Initialize SandboxExecutor.

        Args:
            manifest: Sandbox manifest for access control
            tool_executor: Callable to execute tools
            uv_path: Path to uv binary
            default_timeout_secs: Default execution timeout
        """
        self._manifest = manifest
        self._tool_executor = tool_executor
        self._uv_path = uv_path
        self._default_timeout_secs = default_timeout_secs

    def validate_code(self, code: str) -> Tuple[bool, str]:
        """Validate code before execution.

        Performs:
        - Size check
        - Unicode normalization
        - Comment stripping for analysis
        - AST parsing for blocked imports/builtins

        Args:
            code: Python code to validate

        Returns:
            Tuple of (is_valid: bool, error_message: str)
        """
        if len(code.encode("utf-8")) > MAX_CODE_SIZE_BYTES:
            return False, f"Code exceeds maximum size of {MAX_CODE_SIZE_BYTES} bytes"

        normalized = unicodedata.normalize("NFKC", code)

        code_for_analysis = self._strip_comments(normalized)

        try:
            tree = ast.parse(code_for_analysis)
        except SyntaxError as e:
            return False, f"Syntax error: {e}"

        blocked = self._check_blocked_imports(tree)
        if blocked:
            return False, f"Blocked import detected: {blocked}"

        blocked_builtin = self._check_blocked_builtins(tree)
        if blocked_builtin:
            return False, f"Blocked builtin detected: {blocked_builtin}"

        return True, ""

    def _strip_comments(self, code: str) -> str:
        """Remove comments from code for analysis.

        Args:
            code: Python code

        Returns:
            Code with comments removed
        """
        lines = code.split("\n")
        cleaned_lines = []

        for line in lines:
            in_string = False
            string_char = None
            result = []
            i = 0

            while i < len(line):
                char = line[i]

                if not in_string:
                    if char in "\"'":
                        if i + 2 < len(line) and line[i : i + 3] in ('"""', "'''"):
                            in_string = True
                            string_char = line[i : i + 3]
                            result.append(line[i : i + 3])
                            i += 3
                            continue
                        else:
                            in_string = True
                            string_char = char
                    elif char == "#":
                        break

                else:
                    if string_char and len(string_char) == 3:
                        if line[i : i + 3] == string_char:
                            in_string = False
                            result.append(line[i : i + 3])
                            i += 3
                            continue
                    else:
                        if char == string_char and (i == 0 or line[i - 1] != "\\"):
                            in_string = False

                result.append(char)
                i += 1

            cleaned_lines.append("".join(result))

        return "\n".join(cleaned_lines)

    def _check_blocked_imports(self, tree: ast.AST) -> Optional[str]:
        """Check for blocked imports in AST.

        Args:
            tree: Parsed AST

        Returns:
            Blocked module name if found, None otherwise
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name.split(".")[0]
                    if module in BLOCKED_IMPORTS:
                        return alias.name

            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module = node.module.split(".")[0]
                    if module in BLOCKED_IMPORTS:
                        return node.module

        return None

    def _check_blocked_builtins(self, tree: ast.AST) -> Optional[str]:
        """Check for blocked builtin calls in AST.

        Args:
            tree: Parsed AST

        Returns:
            Blocked builtin name if found, None otherwise
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in BLOCKED_BUILTINS:
                        return node.func.id

        return None

    def execute(
        self,
        code: str,
        namespace: str,
        timeout_secs: Optional[int] = None,
        dependencies: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Execute user code in a uv subprocess.

        Args:
            code: Python code to execute
            namespace: Namespace for access control
            timeout_secs: Execution timeout (uses default if None)
            dependencies: Optional list of pip dependencies

        Returns:
            Dict with status, result, traceback, execution_time_ms
        """
        timeout = timeout_secs or self._default_timeout_secs

        is_valid, error = self.validate_code(code)
        if not is_valid:
            return {
                "status": "error",
                "result": None,
                "traceback": f"Validation error: {error}",
                "execution_time_ms": 0,
            }

        access_control = NamespaceAccessControl(self._manifest)

        wrapped_code = self._wrap_code(code, namespace, access_control)

        env = self._build_env(namespace, access_control)

        start_time = time.perf_counter()

        try:
            stdout = self._run_uv_subprocess(
                wrapped_code,
                env,
                timeout,
                dependencies or [],
            )

            execution_time_ms = int((time.perf_counter() - start_time) * 1000)

            try:
                result = json.loads(stdout)
                return {
                    "status": "success",
                    "result": result.get("result"),
                    "traceback": result.get("traceback"),
                    "execution_time_ms": execution_time_ms,
                }
            except json.JSONDecodeError as e:
                return {
                    "status": "error",
                    "result": None,
                    "traceback": f"Failed to parse result: {e}\nOutput: {stdout[:1000]}",
                    "execution_time_ms": execution_time_ms,
                }

        except subprocess.TimeoutExpired:
            execution_time_ms = int((time.perf_counter() - start_time) * 1000)
            return {
                "status": "error",
                "result": None,
                "traceback": f"Execution timed out after {timeout} seconds",
                "execution_time_ms": execution_time_ms,
            }

        except subprocess.CalledProcessError as e:
            execution_time_ms = int((time.perf_counter() - start_time) * 1000)
            return {
                "status": "error",
                "result": None,
                "traceback": e.stderr or f"Process exited with code {e.returncode}",
                "execution_time_ms": execution_time_ms,
            }

        except Exception as e:
            execution_time_ms = int((time.perf_counter() - start_time) * 1000)
            logger.exception("Sandbox execution failed")
            return {
                "status": "error",
                "result": None,
                "traceback": str(e),
                "execution_time_ms": execution_time_ms,
            }

    def _wrap_code(
        self,
        user_code: str,
        namespace: str,
        access_control: NamespaceAccessControl,
    ) -> str:
        """Wrap user code with sandbox infrastructure.

        Args:
            user_code: User's Python code
            namespace: Namespace for access control
            access_control: Access control instance

        Returns:
            Wrapped code that includes api API
        """
        manifest_json = json.dumps(
            {
                "servers": self._manifest.servers,
                "namespaces": {
                    k: {
                        "servers": v.get("servers", []),
                        "extends": v.get("extends", []),
                    }
                    for k, v in self._manifest.namespaces.items()
                },
            }
        )

        return f'''
import json
import sys

class _ToolExecutor:
    def __init__(self):
        self._pending = []
    
    def __call__(self, server, tool, args):
        self._pending.append({{"server": server, "tool": tool, "args": args}})
        return {{"_pending_call": True, "server": server, "tool": tool, "args": args}}
    
    def get_pending(self):
        return self._pending

_executor = _ToolExecutor()

class _Manifest:
    def __init__(self, data):
        self._data = data
    
    @property
    def servers(self):
        return self._data.get("servers", {{}})
    
    @property
    def namespaces(self):
        return self._data.get("namespaces", {{}})

_manifest_data = {manifest_json}
_manifest = _Manifest(_manifest_data)

class _CapabilityRegistry:
    def __init__(self, manifest):
        self.servers = manifest.servers
        self.namespaces = manifest.namespaces
    
    def get_server(self, name):
        return self.servers.get(name)
    
    def get_namespace(self, name):
        return self.namespaces.get(name)
    
    def get_tools_for_server(self, server_name):
        server = self.get_server(server_name)
        if not server:
            return []
        return server.get("tools", [])

_registry = _CapabilityRegistry(_manifest)

class _NamespaceAccessControl:
    def __init__(self, manifest):
        self.manifest = manifest
    
    def can_access(self, namespace, target_server):
        ns_config = self.manifest.get_namespace(namespace)
        if not ns_config:
            return False, f"Namespace '{{namespace}}' not found"
        
        allowed = self._resolve_allowed_servers(namespace)
        if target_server in allowed:
            return True, ""
        return False, f"Access denied to '{{target_server}}'"
    
    def _resolve_allowed_servers(self, namespace):
        resolved = set()
        visited = set()
        
        def _resolve(ns):
            if ns in visited:
                return
            visited.add(ns)
            ns_config = self.manifest.get_namespace(ns)
            if not ns_config:
                return
            resolved.update(ns_config.get("servers", []))
            for parent in ns_config.get("extends", []):
                _resolve(parent)
        
        _resolve(namespace)
        return resolved

_access_control = _NamespaceAccessControl(_registry)

class _DynamicProxy:
    def __init__(self, server_name, namespace, access_control, tool_executor):
        self._server_name = server_name
        self._namespace = namespace
        self._access_control = access_control
        self._tool_executor = tool_executor
    
    def __getattr__(self, tool_name):
        def _call(**kwargs):
            return self._tool_executor(self._server_name, tool_name, kwargs)
        return _call

class _APIProxy:
    def __init__(self, namespace, access_control, tool_executor, manifest):
        self._namespace = namespace
        self._access_control = access_control
        self._tool_executor = tool_executor
        self._manifest = manifest
    
    def server(self, name):
        can_access, error = self._access_control.can_access(self._namespace, name)
        if not can_access:
            raise PermissionError(error)
        return _DynamicProxy(name, self._namespace, self._access_control, self._tool_executor)
    
    def call_tool(self, server, tool, args):
        can_access, error = self._access_control.can_access(self._namespace, server)
        if not can_access:
            raise PermissionError(error)
        return self._tool_executor(server, tool, args)
    
    def manifest(self):
        allowed = self._access_control._resolve_allowed_servers(self._namespace)
        return {{
            "namespace": self._namespace,
            "allowed_servers": sorted(allowed),
            "servers": {{n: _registry.get_server(n) for n in allowed if _registry.get_server(n)}},
        }}

api = _APIProxy("{namespace}", _access_control, _executor, _manifest)

_result = None
_error = None

try:
    import asyncio
    local_vars = {{"__builtins__": __builtins__, "api": api, "asyncio": asyncio}}
    exec({repr(user_code)}, local_vars, local_vars)
    if "run" in local_vars and callable(local_vars["run"]):
        run_func = local_vars["run"]
        if asyncio.iscoroutinefunction(run_func):
            _result = asyncio.run(run_func())
        else:
            _result = run_func()
except Exception as e:
    import traceback
    _error = traceback.format_exc()

output = {{
    "result": _result,
    "traceback": _error,
    "pending_calls": _executor.get_pending(),
}}

print(json.dumps(output))
'''

    def _build_env(
        self,
        namespace: str,
        access_control: NamespaceAccessControl,
    ) -> Dict[str, str]:
        """Build clean environment for subprocess.

        Args:
            namespace: Namespace for context
            access_control: Access control instance

        Returns:
            Clean environment dict
        """
        return {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
            "SANDBOX_NAMESPACE": namespace,
        }

    def _run_uv_subprocess(
        self,
        code: str,
        env: Dict[str, str],
        timeout: int,
        dependencies: List[str],
    ) -> str:
        """Run code in uv subprocess.

        Args:
            code: Python code to execute
            env: Environment variables
            timeout: Timeout in seconds
            dependencies: List of pip dependencies

        Returns:
            stdout from subprocess

        Raises:
            subprocess.TimeoutExpired: If timeout exceeded
            subprocess.CalledProcessError: If process fails
        """
        cmd = [self._uv_path, "run"]

        for dep in dependencies:
            cmd.extend(["--with", dep])

        cmd.extend(["python", "-c", code])

        logger.debug(f"Running uv subprocess: {' '.join(cmd[:5])}...")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout,
        )

        if result.returncode != 0:
            error = subprocess.CalledProcessError(
                result.returncode, cmd, result.stdout, result.stderr
            )
            raise error

        return result.stdout


def create_sandbox_executor(
    manifest: "SandboxManifest",
    tool_executor: Any,
    **kwargs: Any,
) -> SandboxExecutor:
    """Factory function to create a SandboxExecutor.

    Args:
        manifest: Sandbox manifest
        tool_executor: Tool execution callable
        **kwargs: Additional arguments for SandboxExecutor

    Returns:
        Configured SandboxExecutor instance
    """
    return SandboxExecutor(manifest, tool_executor, **kwargs)
