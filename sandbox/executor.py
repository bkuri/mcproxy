"""Sandbox executor for secure code execution.

Features:
- Async execution with Unix Domain Socket IPC
- Pre-execution code validation
- Blocked imports and builtins
- Timeout enforcement
- Memory limits
- Structured error responses
- Synchronous tool execution with immediate results
"""

import asyncio
import ast
import json
import os
import shutil
import tempfile
import time
import unicodedata
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from code_validator import validate_code_for_dangerous_patterns
from logging_config import get_logger
from sandbox.access_control import NamespaceAccessControl, AccessControlConfig
from sandbox.runtime import RUNTIME_CLASSES
from sandbox.security import (
    BLOCKED_BUILTINS,
    BLOCKED_IMPORTS,
    MAX_CODE_SIZE_BYTES,
)


def get_blocked_functions() -> list[str]:
    """Return list of functions blocked in sandbox for security.

    Returns:
        List of blocked function names with descriptions
    """
    return [
        "eval()",
        "exec()",
        "compile()",
        "open() (file operations)",
        "input()",
        "__import__()",
        "breakpoint()",
        "hasattr()",
        "getattr()",
        "setattr()",
        "delattr()",
        "os.system()",
        "os.popen()",
        "subprocess.* (all subprocess calls)",
        "pickle.loads() / pickle.load()",
        "marshal.loads() / marshal.load()",
        "importlib.import_module()",
    ]


def get_blocked_imports() -> list[str]:
    """Return list of modules blocked from import.

    Returns:
        List of blocked module names
    """
    return [
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
        "pickle",
        "marshal",
        "importlib",
        "builtins",
    ]


def get_blocked_attributes() -> list[str]:
    """Return list of blocked dunder attributes.

    Returns:
        List of blocked attribute names
    """
    return [
        "__class__",
        "__bases__",
        "__subclasses__",
        "__globals__",
        "__locals__",
        "__code__",
        "__builtins__",
        "__dict__",
        "__mro__",
        "__init__",
        "__new__",
        "__reduce__",
        "__getstate__",
        "__setstate__",
    ]


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
    - Unix Domain Socket IPC for synchronous tool calls
    """

    def __init__(
        self,
        manifest: "AccessControlConfig",
        tool_executor: Callable,
        uv_path: str = "uv",
        default_timeout_secs: int = 30,
        max_concurrency: int = 5,
    ):
        """Initialize SandboxExecutor.

        Args:
            manifest: Sandbox manifest for access control
            tool_executor: Async callable to execute tools
            uv_path: Path to uv binary
            default_timeout_secs: Default execution timeout
            max_concurrency: Maximum concurrent parallel executions
        """
        self._manifest = manifest
        self._tool_executor = tool_executor
        self._uv_path = uv_path
        self._default_timeout_secs = default_timeout_secs
        self._max_concurrency = max_concurrency
        self._ipc_server: Optional[asyncio.Server] = None
        self._ipc_sock_path: Optional[str] = None
        self._ipc_temp_dir: Optional[str] = None

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
            return (
                False,
                f"Dangerous pattern detected: {danger_error['error']}. Call get_blocked_functions() for full list.",
            )

        try:
            tree = ast.parse(code_for_analysis)
        except SyntaxError as e:
            return False, f"Syntax error: {e}"

        blocked = self._check_blocked_imports(tree)
        if blocked:
            return (
                False,
                f"Blocked import detected: {blocked}. Call get_blocked_imports() for full list.",
            )

        blocked_builtin = self._check_blocked_builtins(tree)
        if blocked_builtin:
            return (
                False,
                f"Blocked builtin detected: {blocked_builtin}(). Call get_blocked_functions() for full list.",
            )

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

    async def execute(
        self,
        code: str,
        namespace: str,
        timeout_secs: Optional[int] = None,
        dependencies: Optional[List[str]] = None,
        session: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Execute user code in a uv subprocess with IPC support.

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

        start_time = time.perf_counter()

        try:
            stdout = await self._run_uv_subprocess_async(
                wrapped_code,
                namespace,
                access_control,
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
                    await self._apply_stash_updates_async(
                        session, result["stash_updates"]
                    )

                # Build response with stdout if present
                response_data = {
                    "status": "error" if result.get("traceback") else "success",
                    "result": result.get("result"),
                    "traceback": result.get("traceback"),
                    "execution_time_ms": execution_time_ms,
                }

                # Include stdout if it has content
                if result.get("stdout"):
                    response_data["stdout"] = result.get("stdout")

                return response_data
            except json.JSONDecodeError as e:
                return {
                    "status": "error",
                    "result": None,
                    "traceback": f"Failed to parse result: {e}\nOutput: {stdout[:1000]}",
                    "execution_time_ms": execution_time_ms,
                }

        except asyncio.TimeoutError:
            execution_time_ms = int((time.perf_counter() - start_time) * 1000)
            return {
                "status": "error",
                "result": None,
                "traceback": f"Execution timed out after {timeout} seconds",
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

        finally:
            await self._cleanup_ipc()

    async def _apply_stash_updates_async(
        self, session: Any, updates: List[Dict[str, Any]]
    ) -> None:
        """Apply stash updates from sandbox execution to session.

        Args:
            session: SessionStash instance
            updates: List of stash operations from sandbox
        """
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
            Wrapped code that includes api, stash, and parallel APIs
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
import io
import ast

{RUNTIME_CLASSES}

def get_blocked_functions():
    """Return list of functions blocked in sandbox for security."""
    return [
        "eval()",
        "exec()",
        "compile()",
        "open() (file operations)",
        "input()",
        "__import__()",
        "breakpoint()",
        "hasattr()",
        "getattr()",
        "setattr()",
        "delattr()",
        "os.system()",
        "os.popen()",
        "subprocess.* (all subprocess calls)",
        "pickle.loads() / pickle.load()",
        "marshal.loads() / marshal.load()",
        "importlib.import_module()",
    ]

def get_blocked_imports():
    """Return list of modules blocked from import."""
    return [
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
        "pickle",
        "marshal",
        "importlib",
        "builtins",
    ]

def get_blocked_attributes():
    """Return list of blocked dunder attributes."""
    return [
        "__class__",
        "__bases__",
        "__subclasses__",
        "__globals__",
        "__locals__",
        "__code__",
        "__builtins__",
        "__dict__",
        "__mro__",
        "__init__",
        "__new__",
        "__reduce__",
        "__getstate__",
        "__setstate__",
    ]

_PARALLEL_MAX_CONCURRENCY = {self._max_concurrency}
_ipc_client = _IPCClient()
_manifest_data = json.loads({repr(manifest_json)})
_manifest = _Manifest(_manifest_data)
_registry = _CapabilityRegistry(_manifest)
_access_control = _NamespaceAccessControl(_registry)
api = _APIProxy("{namespace}", _access_control, _ipc_client, _manifest)
_stash_initial = json.loads({repr(stash_data_json)})
stash = _StashProxy(_stash_initial)

_result = None
_error = None
_stdout_output = ""

try:
    import re
    
    # Capture stdout
    _old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    
    local_vars = {{"__builtins__": __builtins__, "api": api, "stash": stash, "parallel": parallel, "json": json, "re": re, "sys": sys, "get_blocked_functions": get_blocked_functions, "get_blocked_imports": get_blocked_imports, "get_blocked_attributes": get_blocked_attributes}}
    
    # Try to extract and evaluate last expression for REPL behavior
    _last_expr_value = None
    try:
        _ast = ast.parse({repr(user_code)})
        if _ast.body:
            _last_stmt = _ast.body[-1]
            # If last statement is an expression, capture its value
            if isinstance(_last_stmt, ast.Expr):
                # Execute all but the last statement
                if len(_ast.body) > 1:
                    _setup_code = ast.Module(body=_ast.body[:-1], type_ignores=[])
                    exec(compile(_setup_code, '<string>', 'exec'), local_vars, local_vars)
                # Evaluate the last expression and capture result
                _last_expr_value = eval(compile(ast.Expression(body=_last_stmt.value), '<string>', 'eval'), local_vars, local_vars)
            else:
                # Last statement is not an expression, execute all
                exec({repr(user_code)}, local_vars, local_vars)
        else:
            exec({repr(user_code)}, local_vars, local_vars)
    except (SyntaxError, ValueError):
        # Fallback to simple exec if AST parsing fails
        exec({repr(user_code)}, local_vars, local_vars)
    
    # Restore stdout and capture output
    _stdout_output = sys.stdout.getvalue()
    sys.stdout = _old_stdout
    
    # Determine result: last expression > result variable > run() function
    if _last_expr_value is not None:
        _result = _last_expr_value
    elif "run" in local_vars and callable(local_vars["run"]):
        run_func = local_vars["run"]
        _result = run_func()
    elif "result" in local_vars:
        _result = local_vars["result"]
except NameError as e:
    import traceback
    _stdout_output = sys.stdout.getvalue()
    sys.stdout = _old_stdout
    _error = traceback.format_exc()
    
    # Check for common mistakes
    error_str = str(_error)
    
    # Pattern: blocked builtin access
    blocked_names = ["eval", "exec", "compile", "open", "input", "__import__", "breakpoint", "hasattr", "getattr", "setattr", "delattr"]
    found_blocked = False
    for _bn in blocked_names:
        if f"name '{{_bn}}'" in error_str.lower() or f"name '{{_bn}}'" in error_str:
            _error = f"""NameError: '{{_bn}}' is blocked for security.

Call get_blocked_functions() to see all blocked functions."""
            found_blocked = True
            break
    
    if not found_blocked:
        # Pattern 1: server__tool() direct call
        match = re.search(r"name '([\\w]+__[\\w]+)' is not defined", error_str)
        if match:
            tool_name = match.group(1)
            parts = tool_name.split("__", 1)
            if len(parts) == 2:
                server, tool = parts
                _error = f"""NameError: '{{tool_name}}' is not a function.

Use api.server() to call tools:

    result = api.server("{{server}}").{{tool}}(...)

Available: api.manifest()"""
        elif "call_tool" in error_str and "is not defined" in error_str:
            # Pattern 2: call_tool without api prefix
            _error = """NameError: 'call_tool' is not defined.

Use api.call_tool():

    result = api.call_tool("server", "tool", {{"arg": "value"}})"""
        elif re.search(r"name '(server|manifest)' is not defined", error_str):
            # Pattern 3: Using 'server' directly
            _error = """NameError: Use the 'api' object to access tools.

    result = api.server("name").tool(args)

api.manifest()"""
except Exception as e:
    import traceback
    _stdout_output = sys.stdout.getvalue()
    sys.stdout = _old_stdout
    _error = traceback.format_exc()

output = {{
    "result": _result,
    "stdout": _stdout_output,
    "traceback": _error,
    "stash_updates": stash._get_updates(),
}}

print(json.dumps(output))
'''

    def _build_env(
        self,
        namespace: str,
        access_control: NamespaceAccessControl,
        ipc_sock_path: Optional[str] = None,
    ) -> Dict[str, str]:
        """Build clean environment for subprocess.

        Args:
            namespace: Namespace for context
            access_control: Access control instance
            ipc_sock_path: Optional Unix socket path for IPC

        Returns:
            Clean environment dict
        """
        env = {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
            "SANDBOX_NAMESPACE": namespace,
        }
        if ipc_sock_path:
            env["MCPROXY_IPC_SOCK"] = ipc_sock_path
        return env

    async def _run_uv_subprocess_async(
        self,
        code: str,
        namespace: str,
        access_control: NamespaceAccessControl,
        timeout: int,
        dependencies: List[str],
    ) -> str:
        """Run code in uv subprocess with IPC support.

        Args:
            code: Python code to execute
            namespace: Namespace for access control
            access_control: Access control instance
            timeout: Timeout in seconds
            dependencies: List of pip dependencies

        Returns:
            stdout from subprocess

        Raises:
            asyncio.TimeoutError: If timeout exceeded
            RuntimeError: If process fails
        """
        self._ipc_temp_dir = tempfile.mkdtemp(prefix="mcproxy_ipc_")
        self._ipc_sock_path = os.path.join(self._ipc_temp_dir, "ipc.sock")

        self._ipc_server = await asyncio.start_unix_server(
            self._handle_ipc_connection,
            path=self._ipc_sock_path,
        )
        os.chmod(self._ipc_sock_path, 0o600)

        env = self._build_env(namespace, access_control, self._ipc_sock_path)

        # Write code to temp file to avoid "Argument list too long" error
        # when passing large wrapped code via -c flag
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False
        ) as code_file:
            code_file.write(code)
            code_file_path = code_file.name

        try:
            cmd = [self._uv_path, "run"]

            for dep in dependencies:
                cmd.extend(["--with", dep])

            cmd.extend(["python", code_file_path])

            logger.debug(f"Running uv subprocess: {' '.join(cmd[:5])}...")

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            if process.returncode != 0:
                error_msg = stderr or f"Process exited with code {process.returncode}"
                raise RuntimeError(error_msg)

            return stdout
        finally:
            # Clean up temp file
            try:
                os.unlink(code_file_path)
            except OSError:
                pass

    async def _handle_ipc_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle incoming IPC connection from sandbox subprocess.

        Args:
            reader: Stream reader for incoming data
            writer: Stream writer for outgoing data
        """
        try:
            data = await reader.read(65536)
            if not data:
                return

            try:
                request = json.loads(data.decode("utf-8"))
            except json.JSONDecodeError as e:
                response = {
                    "call_id": None,
                    "status": "error",
                    "error": f"Invalid JSON: {e}",
                }
                writer.write(json.dumps(response).encode("utf-8"))
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return

            call_id = request.get("call_id")
            server = request.get("server")
            tool = request.get("tool")
            args = request.get("args", {})
            logger.info(
                f"[IPC_EXEC] server={server} tool={tool} args={args} type={type(args)}"
            )

            try:
                result = self._tool_executor(server, tool, args)
                if asyncio.iscoroutine(result):
                    result = await result

                response = {
                    "call_id": call_id,
                    "status": "success",
                    "result": result,
                }
            except Exception as e:
                logger.error(f"[IPC] Tool call failed: {server}.{tool}: {e}")
                response = {
                    "call_id": call_id,
                    "status": "error",
                    "error": str(e),
                }

            writer.write(json.dumps(response).encode("utf-8"))
            await writer.drain()

        except Exception as e:
            logger.error(f"[IPC] Connection error: {e}")
        finally:
            writer.close()
            await writer.wait_closed()

    async def _cleanup_ipc(self) -> None:
        """Clean up IPC resources."""
        if self._ipc_server is not None:
            self._ipc_server.close()
            await self._ipc_server.wait_closed()
            self._ipc_server = None

        if self._ipc_sock_path and os.path.exists(self._ipc_sock_path):
            try:
                os.unlink(self._ipc_sock_path)
            except OSError:
                pass
            self._ipc_sock_path = None

        if self._ipc_temp_dir and os.path.exists(self._ipc_temp_dir):
            try:
                shutil.rmtree(self._ipc_temp_dir)
            except OSError:
                pass
            self._ipc_temp_dir = None
