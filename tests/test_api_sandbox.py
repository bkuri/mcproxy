"""Tests for api_sandbox.py - Sandbox Executor and Access Control."""

import pytest
from typing import Any, Dict, List
from unittest.mock import patch, MagicMock

from api_sandbox import (
    SandboxExecutor,
    SandboxManifest,
    NamespaceAccessControl,
    ProxyAPI,
    DynamicProxy,
    BLOCKED_IMPORTS,
    BLOCKED_BUILTINS,
    MAX_CODE_SIZE_BYTES,
    create_sandbox_executor,
)


class TestSandboxExecutorValidation:
    """Tests for SandboxExecutor.validate_code()."""

    def test_validate_code_valid(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        code = "x = 1 + 2\nresult = x * 3"
        is_valid, error = executor.validate_code(code)

        assert is_valid is True
        assert error == ""

    def test_validate_code_syntax_error(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        code = "def broken(\n  pass"
        is_valid, error = executor.validate_code(code)

        assert is_valid is False
        assert "Syntax error" in error

    def test_validate_code_size_limit(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        large_code = "x = 1\n" * (MAX_CODE_SIZE_BYTES // 4)
        is_valid, error = executor.validate_code(large_code)

        assert is_valid is False
        assert "exceeds maximum size" in error

    def test_validate_code_size_exactly_at_limit(
        self, sandbox_manifest: SandboxManifest
    ):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        code_size = MAX_CODE_SIZE_BYTES - 100
        code = "x = 1\n" * (code_size // 6)
        is_valid, error = executor.validate_code(code)

        assert is_valid is True

    def test_validate_code_unicode_normalization(
        self, sandbox_manifest: SandboxManifest
    ):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        code = "x = '\uff41'"  # Full-width 'a'
        is_valid, error = executor.validate_code(code)

        assert is_valid is True


class TestBlockedImports:
    """Tests for blocked import detection."""

    def test_blocked_import_os(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        code = "import os"
        is_valid, error = executor.validate_code(code)

        assert is_valid is False
        assert "Blocked import detected" in error
        assert "os" in error

    def test_blocked_import_sys(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        code = "import sys"
        is_valid, error = executor.validate_code(code)

        assert is_valid is False
        assert "sys" in error

    def test_blocked_import_subprocess(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        code = "import subprocess"
        is_valid, error = executor.validate_code(code)

        assert is_valid is False
        assert "subprocess" in error

    def test_blocked_import_socket(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        code = "import socket"
        is_valid, error = executor.validate_code(code)

        assert is_valid is False
        assert "socket" in error

    def test_blocked_import_http(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        code = "import http.client"
        is_valid, error = executor.validate_code(code)

        assert is_valid is False
        assert "http" in error

    def test_blocked_import_urllib(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        code = "from urllib.request import urlopen"
        is_valid, error = executor.validate_code(code)

        assert is_valid is False
        assert "urllib" in error

    def test_blocked_import_requests(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        code = "import requests"
        is_valid, error = executor.validate_code(code)

        assert is_valid is False
        assert "requests" in error

    def test_blocked_import_shutil(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        code = "import shutil"
        is_valid, error = executor.validate_code(code)

        assert is_valid is False
        assert "shutil" in error

    def test_blocked_import_tempfile(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        code = "import tempfile"
        is_valid, error = executor.validate_code(code)

        assert is_valid is False
        assert "tempfile" in error

    def test_blocked_import_multiprocessing(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        code = "import multiprocessing"
        is_valid, error = executor.validate_code(code)

        assert is_valid is False
        assert "multiprocessing" in error

    def test_blocked_import_from_syntax(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        code = "from os import path"
        is_valid, error = executor.validate_code(code)

        assert is_valid is False
        assert "os" in error

    def test_allowed_import(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        code = "import json\nimport math"
        is_valid, error = executor.validate_code(code)

        assert is_valid is True

    def test_blocked_import_in_comment_ignored(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        code = "# import os\nimport json"
        is_valid, error = executor.validate_code(code)

        assert is_valid is True


class TestBlockedBuiltins:
    """Tests for blocked builtin detection."""

    def test_blocked_builtin_eval(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        code = "x = eval('1+1')"
        is_valid, error = executor.validate_code(code)

        assert is_valid is False
        assert "Blocked builtin detected" in error
        assert "eval" in error

    def test_blocked_builtin_exec(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        code = "exec('x = 1')"
        is_valid, error = executor.validate_code(code)

        assert is_valid is False
        assert "exec" in error

    def test_blocked_builtin_compile(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        code = "compile('x = 1', '<string>', 'exec')"
        is_valid, error = executor.validate_code(code)

        assert is_valid is False
        assert "compile" in error

    def test_blocked_builtin_open(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        code = "f = open('file.txt')"
        is_valid, error = executor.validate_code(code)

        assert is_valid is False
        assert "open" in error

    def test_blocked_builtin_input(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        code = "x = input('prompt')"
        is_valid, error = executor.validate_code(code)

        assert is_valid is False
        assert "input" in error

    def test_blocked_builtin_breakpoint(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        code = "breakpoint()"
        is_valid, error = executor.validate_code(code)

        assert is_valid is False
        assert "breakpoint" in error

    def test_allowed_builtin_call(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        code = "x = len([1, 2, 3])\ny = str(x)"
        is_valid, error = executor.validate_code(code)

        assert is_valid is True


class TestNamespaceAccessControl:
    """Tests for NamespaceAccessControl."""

    def test_can_access_allowed(self, namespace_access_control: NamespaceAccessControl):
        allowed, error = namespace_access_control.can_access("browser", "playwright")

        assert allowed is True
        assert error == ""

    def test_can_access_denied(self, namespace_access_control: NamespaceAccessControl):
        allowed, error = namespace_access_control.can_access("browser", "filesystem")

        assert allowed is False
        assert "does not have access" in error

    def test_can_access_namespace_not_found(
        self, namespace_access_control: NamespaceAccessControl
    ):
        allowed, error = namespace_access_control.can_access(
            "nonexistent", "playwright"
        )

        assert allowed is False
        assert "not found" in error

    def test_can_access_inheritance(
        self, namespace_access_control: NamespaceAccessControl
    ):
        allowed, error = namespace_access_control.can_access("privileged", "playwright")

        assert allowed is True

        allowed, error = namespace_access_control.can_access("privileged", "filesystem")

        assert allowed is True

        allowed, error = namespace_access_control.can_access("privileged", "system")

        assert allowed is True

    def test_can_access_crypto_namespace(
        self, namespace_access_control: NamespaceAccessControl
    ):
        allowed, _ = namespace_access_control.can_access("security", "crypto")
        assert allowed is True

        allowed, _ = namespace_access_control.can_access("security", "playwright")
        assert allowed is False

    def test_get_allowed_tools(self, namespace_access_control: NamespaceAccessControl):
        tools, error = namespace_access_control.get_allowed_tools(
            "browser", "playwright"
        )

        assert error == ""
        assert "playwright__navigate" in tools
        assert "playwright__click" in tools

    def test_get_allowed_tools_denied(
        self, namespace_access_control: NamespaceAccessControl
    ):
        tools, error = namespace_access_control.get_allowed_tools(
            "browser", "filesystem"
        )

        assert tools == []
        assert "does not have access" in error

    def test_resolve_allowed_servers_circular(
        self, namespace_access_control: NamespaceAccessControl
    ):
        servers = namespace_access_control._resolve_allowed_servers("circular_a")

        assert "playwright" in servers or "filesystem" in servers


class TestSandboxManifest:
    """Tests for SandboxManifest dataclass."""

    def test_get_server(self, sandbox_manifest: SandboxManifest):
        server = sandbox_manifest.get_server("playwright")

        assert server is not None
        assert "tools" in server

    def test_get_server_not_found(self, sandbox_manifest: SandboxManifest):
        server = sandbox_manifest.get_server("nonexistent")

        assert server is None

    def test_get_namespace(self, sandbox_manifest: SandboxManifest):
        ns = sandbox_manifest.get_namespace("browser")

        assert ns is not None

    def test_get_namespace_not_found(self, sandbox_manifest: SandboxManifest):
        ns = sandbox_manifest.get_namespace("nonexistent")

        assert ns is None

    def test_get_tools_for_server(self, sandbox_manifest: SandboxManifest):
        tools = sandbox_manifest.get_tools_for_server("playwright")

        assert len(tools) == 3
        assert "playwright__navigate" in tools

    def test_get_tools_for_server_not_found(self, sandbox_manifest: SandboxManifest):
        tools = sandbox_manifest.get_tools_for_server("nonexistent")

        assert tools == []


class TestProxyAPI:
    """Tests for ProxyAPI."""

    def test_server_returns_proxy(
        self, namespace_access_control: NamespaceAccessControl
    ):
        api = ProxyAPI("browser", namespace_access_control, lambda *args: None)
        proxy = api.server("playwright")

        assert isinstance(proxy, DynamicProxy)
        assert proxy._server_name == "playwright"

    def test_server_access_denied(
        self, namespace_access_control: NamespaceAccessControl
    ):
        api = ProxyAPI("browser", namespace_access_control, lambda *args: None)

        with pytest.raises(PermissionError):
            api.server("filesystem")

    def test_call_tool(self, namespace_access_control: NamespaceAccessControl):
        mock_executor = MagicMock(return_value={"result": "ok"})
        api = ProxyAPI("browser", namespace_access_control, mock_executor)

        result = api.call_tool("playwright", "navigate", {"url": "http://example.com"})

        assert result == {"result": "ok"}
        mock_executor.assert_called_once_with(
            "playwright", "navigate", {"url": "http://example.com"}
        )

    def test_call_tool_access_denied(
        self, namespace_access_control: NamespaceAccessControl
    ):
        api = ProxyAPI("browser", namespace_access_control, lambda *args: None)

        with pytest.raises(PermissionError):
            api.call_tool("filesystem", "read_file", {"path": "/etc/passwd"})

    def test_manifest(self, namespace_access_control: NamespaceAccessControl):
        api = ProxyAPI("browser", namespace_access_control, lambda *args: None)
        manifest = api.manifest()

        assert manifest["namespace"] == "browser"
        assert "playwright" in manifest["allowed_servers"]
        assert "filesystem" not in manifest["allowed_servers"]

    def test_manifest_with_inheritance(
        self, namespace_access_control: NamespaceAccessControl
    ):
        api = ProxyAPI("privileged", namespace_access_control, lambda *args: None)
        manifest = api.manifest()

        assert manifest["namespace"] == "privileged"
        assert "playwright" in manifest["allowed_servers"]
        assert "filesystem" in manifest["allowed_servers"]
        assert "system" in manifest["allowed_servers"]


class TestDynamicProxy:
    """Tests for DynamicProxy."""

    def test_getattr_returns_callable(
        self, namespace_access_control: NamespaceAccessControl
    ):
        mock_executor = MagicMock()
        proxy = DynamicProxy(
            "playwright", "browser", namespace_access_control, mock_executor
        )

        navigate = proxy.navigate
        assert callable(navigate)

    def test_call_forwards_to_executor(
        self, namespace_access_control: NamespaceAccessControl
    ):
        mock_executor = MagicMock(return_value="result")
        proxy = DynamicProxy(
            "playwright", "browser", namespace_access_control, mock_executor
        )

        result = proxy.navigate(url="http://example.com")

        assert result == "result"
        mock_executor.assert_called_once_with(
            "playwright", "navigate", {"url": "http://example.com"}
        )

    def test_repr(self, namespace_access_control: NamespaceAccessControl):
        proxy = DynamicProxy(
            "playwright", "browser", namespace_access_control, lambda *args: None
        )

        assert repr(proxy) == "<DynamicProxy server='playwright'>"


class TestSandboxExecutorExecute:
    """Tests for SandboxExecutor.execute()."""

    def test_execute_returns_validation_error(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        result = executor.execute("import os", "browser")

        assert result["status"] == "error"
        assert "Validation error" in result["traceback"]
        assert result["result"] is None

    def test_execute_result_format(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)

        with patch.object(
            executor,
            "_run_uv_subprocess",
            return_value='{"result": 42, "traceback": null}',
        ):
            result = executor.execute("x = 1", "browser")

            assert result["status"] == "success"
            assert result["result"] == 42
            assert "execution_time_ms" in result

    def test_execute_timeout(self, sandbox_manifest: SandboxManifest):
        import subprocess

        executor = SandboxExecutor(
            sandbox_manifest, lambda *args: None, default_timeout_secs=1
        )

        with patch.object(
            executor,
            "_run_uv_subprocess",
            side_effect=subprocess.TimeoutExpired(cmd=[], timeout=1),
        ):
            result = executor.execute("x = 1", "browser")

            assert result["status"] == "error"
            assert "timed out" in result["traceback"]

    def test_execute_process_error(self, sandbox_manifest: SandboxManifest):
        import subprocess

        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)

        with patch.object(
            executor,
            "_run_uv_subprocess",
            side_effect=subprocess.CalledProcessError(1, [], stderr="Error output"),
        ):
            result = executor.execute("x = 1", "browser")

            assert result["status"] == "error"
            assert "Error output" in result["traceback"]

    def test_execute_json_decode_error(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)

        with patch.object(executor, "_run_uv_subprocess", return_value="invalid json{"):
            result = executor.execute("x = 1", "browser")

            assert result["status"] == "error"
            assert "Failed to parse result" in result["traceback"]


class TestSandboxExecutorHelpers:
    """Tests for SandboxExecutor helper methods."""

    def test_strip_comments_single_line(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)

        code = "x = 1  # comment\ny = 2"
        stripped = executor._strip_comments(code)

        assert "#" not in stripped
        assert "x = 1" in stripped
        assert "y = 2" in stripped

    def test_strip_comments_preserves_strings(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)

        code = 'x = "# not a comment"'
        stripped = executor._strip_comments(code)

        assert '"# not a comment"' in stripped

    def test_strip_comments_multiline_string(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)

        code = 'x = """multi\\n# line\\nstring"""'
        stripped = executor._strip_comments(code)

        assert '"""multi' in stripped

    def test_build_env(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        access_control = NamespaceAccessControl(sandbox_manifest)

        env = executor._build_env("test_namespace", access_control)

        assert env["PYTHONIOENCODING"] == "utf-8"
        assert env["PYTHONUNBUFFERED"] == "1"
        assert env["SANDBOX_NAMESPACE"] == "test_namespace"

    def test_wrap_code_includes_namespace(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        access_control = NamespaceAccessControl(sandbox_manifest)

        wrapped = executor._wrap_code("x = 1", "my_namespace", access_control)

        assert "my_namespace" in wrapped
        assert "api" in wrapped
        assert "_APIProxy" in wrapped


class TestCreateSandboxExecutor:
    """Tests for factory function."""

    def test_create_sandbox_executor(self, sandbox_manifest: SandboxManifest):
        executor = create_sandbox_executor(sandbox_manifest, lambda *args: None)

        assert isinstance(executor, SandboxExecutor)

    def test_create_sandbox_executor_with_kwargs(
        self, sandbox_manifest: SandboxManifest
    ):
        executor = create_sandbox_executor(
            sandbox_manifest,
            lambda *args: None,
            uv_path="/custom/uv",
            default_timeout_secs=60,
        )

        assert executor._uv_path == "/custom/uv"
        assert executor._default_timeout_secs == 60


class TestErrorFormat:
    """Tests for structured error response format."""

    def test_error_response_has_traceback(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        result = executor.execute("import os", "browser")

        assert "traceback" in result
        assert isinstance(result["traceback"], str)
        assert len(result["traceback"]) > 0

    def test_error_response_has_status(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        result = executor.execute("import os", "browser")

        assert "status" in result
        assert result["status"] == "error"

    def test_error_response_has_execution_time(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        result = executor.execute("import os", "browser")

        assert "execution_time_ms" in result
        assert isinstance(result["execution_time_ms"], int)

    def test_error_response_result_is_none(self, sandbox_manifest: SandboxManifest):
        executor = SandboxExecutor(sandbox_manifest, lambda *args: None)
        result = executor.execute("import os", "browser")

        assert "result" in result
        assert result["result"] is None
