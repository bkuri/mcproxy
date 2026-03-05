"""Tests for mcproxy_sequence meta-tool - read-transform-write pattern."""

import asyncio
import json
import pytest
from typing import Any, Callable, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, patch

from sandbox import SandboxExecutor, AccessControlConfig
from session_stash import SessionManager, SessionStash
from server.handlers import handle_sequence


class TestSequenceBasicReadWrite:
    """Tests for basic read-transform-write operations."""

    @pytest.mark.asyncio
    async def test_sequence_basic_read_write(
        self,
        sandbox_manifest: AccessControlConfig,
        namespace_access_control,
    ):
        """Basic read-transform-write with string transformation."""
        mock_executor = MagicMock()

        def execute_tool(
            server: str, tool: str, args: Dict[str, Any]
        ) -> Dict[str, Any]:
            if server == "test_server" and tool == "read":
                return {"content": "original"}
            elif server == "test_server" and tool == "write":
                return {"status": "ok"}
            return {}

        mock_executor.side_effect = execute_tool

        params = {
            "read": {
                "server": "test_server",
                "tool": "read",
                "args": {"path": "test.txt"},
            },
            "transform": 'result = {"content": read_result.upper()}',
            "write": {
                "server": "test_server",
                "tool": "write",
            },
        }

        result = await handle_sequence(
            msg_id=1,
            params=params,
            connection_namespace="browser",
            session_id=None,
            sandbox_executor=None,
            session_manager=None,
            tool_executor=mock_executor,
        )

        assert result["jsonrpc"] == "2.0"
        assert result["id"] == 1
        assert "result" in result
        content = json.loads(result["result"]["content"][0]["text"])
        assert "error" not in content
        assert content["write_result"]["status"] == "ok"

    @pytest.mark.asyncio
    async def test_sequence_with_json_transform(
        self,
        sandbox_manifest: AccessControlConfig,
        namespace_access_control,
    ):
        """Transform parses JSON, modifies, returns new args."""
        mock_executor = MagicMock()

        def execute_tool(
            server: str, tool: str, args: Dict[str, Any]
        ) -> Dict[str, Any]:
            if server == "config_server" and tool == "read_config":
                return {"content": '{"name": "test", "value": 1}'}
            elif server == "config_server" and tool == "write_config":
                return {"status": "saved"}
            return {}

        mock_executor.side_effect = execute_tool

        params = {
            "read": {
                "server": "config_server",
                "tool": "read_config",
                "args": {"path": "config.json"},
            },
            "transform": """
config = json.loads(read_result)
config["value"] = 42
config["updated"] = True
result = {"content": json.dumps(config)}
""",
            "write": {
                "server": "config_server",
                "tool": "write_config",
            },
        }

        result = await handle_sequence(
            msg_id=2,
            params=params,
            connection_namespace="browser",
            session_id=None,
            sandbox_executor=None,
            session_manager=None,
            tool_executor=mock_executor,
        )

        assert result["jsonrpc"] == "2.0"
        content = json.loads(result["result"]["content"][0]["text"])
        assert "error" not in content
        assert content["write_result"]["status"] == "saved"

        write_call = mock_executor.call_args_list[-1]
        written_content = json.loads(write_call[0][2]["content"])
        assert written_content["value"] == 42
        assert written_content["updated"] is True

    @pytest.mark.asyncio
    async def test_sequence_with_stash(
        self,
        sandbox_manifest: AccessControlConfig,
        namespace_access_control,
    ):
        """Use stash in transform for stateful operations."""
        mock_executor = MagicMock()

        def execute_tool(
            server: str, tool: str, args: Dict[str, Any]
        ) -> Dict[str, Any]:
            if server == "counter_server" and tool == "get":
                return {"content": "5"}
            elif server == "counter_server" and tool == "set":
                return {"status": "ok"}
            return {}

        mock_executor.side_effect = execute_tool

        session_manager = SessionManager()
        session = await session_manager.get_or_create("test-session-stash")

        params = {
            "read": {
                "server": "counter_server",
                "tool": "get",
                "args": {},
            },
            "transform": """
count = int(read_result) + 1
stash.put("call_count", count)
result = {"count": str(count)}
""",
            "write": {
                "server": "counter_server",
                "tool": "set",
            },
        }

        result = await handle_sequence(
            msg_id=3,
            params=params,
            connection_namespace="browser",
            session_id="test-session-stash",
            sandbox_executor=None,
            session_manager=session_manager,
            tool_executor=mock_executor,
        )

        assert result["jsonrpc"] == "2.0"
        content = json.loads(result["result"]["content"][0]["text"])
        assert "error" not in content
        assert content["write_result"]["status"] == "ok"

        await asyncio.sleep(0)
        assert await session.get("call_count") == 6


class TestSequenceErrors:
    """Tests for error handling in sequence operations."""

    @pytest.mark.asyncio
    async def test_sequence_read_error(
        self,
        sandbox_manifest: AccessControlConfig,
        namespace_access_control,
    ):
        """Read step error should return error with step='read'."""
        mock_executor = MagicMock()

        def execute_tool(
            server: str, tool: str, args: Dict[str, Any]
        ) -> Dict[str, Any]:
            raise RuntimeError("File not found")

        mock_executor.side_effect = execute_tool

        params = {
            "read": {
                "server": "file_server",
                "tool": "read_file",
                "args": {"path": "/nonexistent.txt"},
            },
            "transform": 'result = {"content": read_result}',
            "write": {
                "server": "file_server",
                "tool": "write_file",
            },
        }

        result = await handle_sequence(
            msg_id=4,
            params=params,
            connection_namespace="browser",
            session_id=None,
            sandbox_executor=None,
            session_manager=None,
            tool_executor=mock_executor,
        )

        assert result["jsonrpc"] == "2.0"
        content = json.loads(result["result"]["content"][0]["text"])
        assert "error" in content
        assert content["error"]["step"] == "read"
        assert "File not found" in content["error"]["message"]

    @pytest.mark.asyncio
    async def test_sequence_transform_error(
        self,
        sandbox_manifest: AccessControlConfig,
        namespace_access_control,
    ):
        """Transform syntax error should return error with step='transform' and traceback."""
        mock_executor = MagicMock()

        def execute_tool(
            server: str, tool: str, args: Dict[str, Any]
        ) -> Dict[str, Any]:
            return {"content": "test data"}

        mock_executor.side_effect = execute_tool

        params = {
            "read": {
                "server": "test_server",
                "tool": "read",
                "args": {},
            },
            "transform": 'result = {"content": undefined_var}',
            "write": {
                "server": "test_server",
                "tool": "write",
            },
        }

        result = await handle_sequence(
            msg_id=5,
            params=params,
            connection_namespace="browser",
            session_id=None,
            sandbox_executor=None,
            session_manager=None,
            tool_executor=mock_executor,
        )

        assert result["jsonrpc"] == "2.0"
        content = json.loads(result["result"]["content"][0]["text"])
        assert "error" in content
        assert content["error"]["step"] == "transform"
        assert "traceback" in content["error"]
        assert (
            "undefined_var" in content["error"]["traceback"]
            or "NameError" in content["error"]["traceback"]
        )

    @pytest.mark.asyncio
    async def test_sequence_write_error(
        self,
        sandbox_manifest: AccessControlConfig,
        namespace_access_control,
    ):
        """Write step error should return error with step='write'."""
        mock_executor = MagicMock()

        def execute_tool(
            server: str, tool: str, args: Dict[str, Any]
        ) -> Dict[str, Any]:
            if tool == "read":
                return {"content": "data"}
            elif tool == "write":
                raise PermissionError("Write access denied")

        mock_executor.side_effect = execute_tool

        params = {
            "read": {
                "server": "file_server",
                "tool": "read",
                "args": {"path": "test.txt"},
            },
            "transform": 'result = {"content": read_result.upper()}',
            "write": {
                "server": "file_server",
                "tool": "write",
            },
        }

        result = await handle_sequence(
            msg_id=6,
            params=params,
            connection_namespace="browser",
            session_id=None,
            sandbox_executor=None,
            session_manager=None,
            tool_executor=mock_executor,
        )

        assert result["jsonrpc"] == "2.0"
        content = json.loads(result["result"]["content"][0]["text"])
        assert "error" in content
        assert content["error"]["step"] == "write"
        assert "Write access denied" in content["error"]["message"]

    @pytest.mark.asyncio
    async def test_sequence_missing_result_variable(
        self,
        sandbox_manifest: AccessControlConfig,
        namespace_access_control,
    ):
        """Transform without setting result should return clear error."""
        mock_executor = MagicMock()

        def execute_tool(
            server: str, tool: str, args: Dict[str, Any]
        ) -> Dict[str, Any]:
            return {"content": "test data"}

        mock_executor.side_effect = execute_tool

        params = {
            "read": {
                "server": "test_server",
                "tool": "read",
                "args": {},
            },
            "transform": "x = read_result.upper()",
            "write": {
                "server": "test_server",
                "tool": "write",
            },
        }

        result = await handle_sequence(
            msg_id=7,
            params=params,
            connection_namespace="browser",
            session_id=None,
            sandbox_executor=None,
            session_manager=None,
            tool_executor=mock_executor,
        )

        assert result["jsonrpc"] == "2.0"
        content = json.loads(result["result"]["content"][0]["text"])
        assert "error" in content
        assert content["error"]["step"] == "transform"
        assert "result" in content["error"]["message"].lower()


class TestSequenceValidation:
    """Tests for parameter validation."""

    @pytest.mark.asyncio
    async def test_sequence_missing_read_param(self):
        """Missing read parameter should return error."""
        params = {
            "transform": 'result = {"content": read_result}',
            "write": {"server": "test", "tool": "write"},
        }

        result = await handle_sequence(
            msg_id=8,
            params=params,
            connection_namespace="browser",
            session_id=None,
            sandbox_executor=None,
            session_manager=None,
            tool_executor=None,
        )

        assert "error" in result
        assert result["error"]["code"] == -32602

    @pytest.mark.asyncio
    async def test_sequence_missing_transform_param(self):
        """Missing transform should pass data through unchanged."""
        mock_executor = MagicMock(return_value={"content": "original"})

        params = {
            "read": {"server": "test", "tool": "read"},
            # No transform
        }

        result = await handle_sequence(
            msg_id=9,
            params=params,
            connection_namespace="browser",
            session_id=None,
            sandbox_executor=None,
            session_manager=None,
            tool_executor=mock_executor,
        )

        assert "result" in result
        content = json.loads(result["result"]["content"][0]["text"])
        assert "error" not in content
        # read_result is extracted from {"content": "original"} -> "original"
        assert content["read_result"] == "original"
        assert content["transform_result"] == "original"  # Passed through

    @pytest.mark.asyncio
    async def test_sequence_missing_namespace(self):
        """Missing namespace should return error."""
        params = {
            "read": {"server": "test", "tool": "read"},
            "transform": 'result = {"content": read_result}',
            "write": {"server": "test", "tool": "write"},
        }

        result = await handle_sequence(
            msg_id=11,
            params=params,
            connection_namespace=None,
            session_id=None,
            sandbox_executor=None,
            session_manager=None,
            tool_executor=None,
        )

        assert "error" in result


class TestSequenceDataExtraction:
    """Tests for data extraction from read results."""

    @pytest.mark.asyncio
    async def test_sequence_extracts_content_field(
        self,
        sandbox_manifest: AccessControlConfig,
        namespace_access_control,
    ):
        """Transform receives 'content' field from read result."""
        mock_executor = MagicMock()

        def execute_tool(
            server: str, tool: str, args: Dict[str, Any]
        ) -> Dict[str, Any]:
            if tool == "read":
                return {"content": "extracted content", "metadata": "ignored"}
            return {"status": "ok"}

        mock_executor.side_effect = execute_tool

        params = {
            "read": {
                "server": "test_server",
                "tool": "read",
                "args": {},
            },
            "transform": 'result = {"transformed": read_result}',
            "write": {
                "server": "test_server",
                "tool": "write",
            },
        }

        result = await handle_sequence(
            msg_id=12,
            params=params,
            connection_namespace="browser",
            session_id=None,
            sandbox_executor=None,
            session_manager=None,
            tool_executor=mock_executor,
        )

        assert result["jsonrpc"] == "2.0"
        content = json.loads(result["result"]["content"][0]["text"])
        assert "error" not in content

        write_call = mock_executor.call_args_list[-1]
        assert write_call[0][2]["transformed"] == "extracted content"

    @pytest.mark.asyncio
    async def test_sequence_extracts_tool_results_array(
        self,
        sandbox_manifest: AccessControlConfig,
        namespace_access_control,
    ):
        """Transform receives result.content when read returns nested structure."""
        mock_executor = MagicMock()

        def execute_tool(
            server: str, tool: str, args: Dict[str, Any]
        ) -> Dict[str, Any]:
            if tool == "read":
                return {"result": {"content": "from array"}}
            return {"status": "ok"}

        mock_executor.side_effect = execute_tool

        params = {
            "read": {
                "server": "test_server",
                "tool": "read",
                "args": {},
            },
            "transform": 'result = {"value": read_result}',
            "write": {
                "server": "test_server",
                "tool": "write",
            },
        }

        result = await handle_sequence(
            msg_id=13,
            params=params,
            connection_namespace="browser",
            session_id=None,
            sandbox_executor=None,
            session_manager=None,
            tool_executor=mock_executor,
        )

        assert result["jsonrpc"] == "2.0"
        content = json.loads(result["result"]["content"][0]["text"])
        assert "error" not in content

        write_call = mock_executor.call_args_list[-1]
        assert write_call[0][2]["value"] == "from array"
