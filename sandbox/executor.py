"""Sandbox executor for secure code execution."""

import ast
import json
import subprocess
import time
import unicodedata
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from code_validator import validate_code_for_dangerous_patterns
from logging_config import get_logger
from sandbox.access_control import NamespaceAccessControl, SandboxManifest
from sandbox.runtime import RUNTIME_CLASSES
from sandbox.security import (
    BLOCKED_BUILTINS,
    BLOCKED_IMPORTS,
    MAX_CODE_SIZE_BYTES,
)

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


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
        max_concurrency: int = 5,
    ):
        """Initialize SandboxExecutor.

        Args:
            manifest: Sandbox manifest for access control
            tool_executor: Callable to execute tools
            uv_path: Path to uv binary
            default_timeout_secs: Default execution timeout
            max_concurrency: Maximum concurrent parallel executions
        """
        self._manifest = manifest
        self._tool_executor = tool_executor
        self._uv_path = uv_path
        self._default_timeout_secs = default_timeout_secs
        self._max_concurrency = max_concurrency

    def validate_code(self, code: str) -> tuple[bool, str]:
        """Validate code before execution.

        Performs:
        - Size check
        - Unicode normalization
        - Comment stripping for analysis
        - AST-based dangerous pattern detection
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

        is_safe, danger_error = validate_code_for_dangerous_patterns(code_for_analysis)
        if not is_safe and danger_error:
            return False, f"Dangerous pattern detected: {danger_error['error']}"

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
        session: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Execute user code in a uv subprocess.

        Args:
            code: Python code to execute
            namespace: Namespace for access control
            timeout_secs: Execution timeout (uses default if None)
            dependencies: Optional list of pip dependencies
            session: Optional SessionStash for session-scoped storage

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

        wrapped_code = self._wrap_code(code, namespace, access_control, session)

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
                lines = stdout.strip().split("\n")
                json_line = None
                for line in reversed(lines):
                    line = line.strip()
                    if line.startswith("{") and line.endswith("}"):
                        try:
                            json.loads(line)
                            json_line = line
                            break
                        except json.JSONDecodeError:
                            continue

                if not json_line:
                    return {
                        "status": "error",
                        "result": None,
                        "traceback": f"No JSON output found. Output: {stdout[:1000]}",
                        "execution_time_ms": execution_time_ms,
                    }

                result = json.loads(json_line)

                if session is not None and "stash_updates" in result:
                    self._apply_stash_updates(session, result["stash_updates"])

                return {
                    "status": "success",
                    "result": result.get("result"),
                    "traceback": result.get("traceback"),
                    "pending_calls": result.get("pending_calls", []),
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

    def _apply_stash_updates(self, session: Any, updates: List[Dict[str, Any]]) -> None:
        """Apply stash updates from sandbox execution to session.

        Args:
            session: SessionStash instance
            updates: List of stash operations from sandbox
        """
        import asyncio

        async def _apply():
            for update in updates:
                op = update.get("op")
                key = update.get("key")
                if op == "put":
                    value = update.get("value")
                    ttl = update.get("ttl_seconds")
                    await session.put(key, value, ttl_seconds=ttl)
                elif op == "delete":
                    await session.delete(key)
                elif op == "clear":
                    await session.clear()

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(_apply())
            else:
                loop.run_until_complete(_apply())
        except Exception as e:
            logger.error(f"[STASH] Failed to apply updates: {e}")

    def _wrap_code(
        self,
        user_code: str,
        namespace: str,
        access_control: NamespaceAccessControl,
        session: Optional[Any] = None,
    ) -> str:
        """Wrap user code with sandbox infrastructure.

        Args:
            user_code: User's Python code
            namespace: Namespace for access control
            access_control: Access control instance
            session: Optional SessionStash for session-scoped storage

        Returns:
            Wrapped code that includes api, stash, and forge APIs

        NOTE: Internal class definitions (_CapabilityRegistry, _NamespaceAccessControl,
        _DynamicProxy, _APIProxy) are intentionally duplicated from top-level classes.
        This is NOT a bug - the sandbox runs in a separate subprocess via `uv run`,
        so it cannot import or reference the parent process's classes. These internal
        classes:

        1. Work with JSON-serialized manifest data (not live objects)
        2. Include additional features needed in sandbox context (e.g., group resolution
           in _NamespaceAccessControl which the top-level version lacks)
        3. Use _ToolExecutor that collects pending calls instead of executing tools

        The top-level classes (SandboxManifest, NamespaceAccessControl, DynamicProxy,
        ProxyAPI) are used by the parent process for validation and setup, while the
        internal underscore-prefixed versions are the standalone implementations that
        run inside the sandbox subprocess.
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
                "groups": self._manifest.groups,
            }
        )

        stash_data_json = "{}"
        if session is not None:
            import asyncio

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    stash_data_json = "{}"
                else:
                    keys = loop.run_until_complete(session.keys())
                    stash_data = {}
                    for key in keys:
                        val = loop.run_until_complete(session.get(key))
                        if val is not None:
                            stash_data[key] = val
                    stash_data_json = json.dumps(stash_data)
            except Exception:
                stash_data_json = "{}"

        return f'''
import json
import sys

{RUNTIME_CLASSES}

_executor = _ToolExecutor()
_manifest_data = {manifest_json}
_manifest = _Manifest(_manifest_data)
_registry = _CapabilityRegistry(_manifest)
_access_control = _NamespaceAccessControl(_registry)
api = _APIProxy("{namespace}", _access_control, _executor, _manifest)
_stash_initial = {stash_data_json}
stash = _StashProxy(_stash_initial)
forge = _ForgeProxy(max_concurrency={self._max_concurrency})

_result = None
_error = None

try:
    import asyncio
    local_vars = {{"__builtins__": __builtins__, "api": api, "stash": stash, "asyncio": asyncio, "forge": forge}}
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
    "stash_updates": stash._get_updates(),
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
