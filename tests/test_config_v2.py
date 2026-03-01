"""Tests for config_watcher.py - v2.0 Configuration Validation."""

import json
import os
import pytest
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch, mock_open

from config_watcher import (
    load_config,
    validate_schema,
    validate_server,
    validate_namespaces,
    validate_namespace_servers,
    validate_namespace_extends,
    validate_manifests,
    validate_sandbox,
    interpolate_env_vars,
    ConfigError,
)


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_config_valid(self, sample_v2_config: Dict[str, Any], tmp_path: Path):
        config_file = tmp_path / "test-config.json"
        config_file.write_text(json.dumps(sample_v2_config))

        config = load_config(str(config_file))

        assert "servers" in config
        assert len(config["servers"]) == 2

    def test_load_config_file_not_found(self):
        with pytest.raises(ConfigError) as exc_info:
            load_config("/nonexistent/path/config.json")

        assert "Config file not found" in str(exc_info.value)

    def test_load_config_invalid_json(self, tmp_path: Path):
        config_file = tmp_path / "invalid.json"
        config_file.write_text("{invalid json}")

        with pytest.raises(ConfigError) as exc_info:
            load_config(str(config_file))

        assert "Invalid JSON" in str(exc_info.value)

    def test_load_config_with_env_vars(self, tmp_path: Path):
        config_file = tmp_path / "config.json"
        config_file.write_text(
            json.dumps(
                {
                    "servers": [
                        {
                            "name": "test",
                            "command": "${TEST_CMD}",
                            "args": ["${TEST_ARG}"],
                        }
                    ]
                }
            )
        )

        with patch.dict(os.environ, {"TEST_CMD": "node", "TEST_ARG": "script.js"}):
            config = load_config(str(config_file))

            assert config["servers"][0]["command"] == "node"
            assert config["servers"][0]["args"][0] == "script.js"


class TestValidateSchema:
    """Tests for validate_schema function."""

    def test_validate_schema_valid(self, sample_v2_config: Dict[str, Any]):
        validate_schema(sample_v2_config)

    def test_validate_schema_not_dict(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_schema(["not", "a", "dict"])

        assert "must be a JSON object" in str(exc_info.value)

    def test_validate_schema_missing_servers(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_schema({"namespaces": {}})

        assert "missing required 'servers' field" in str(exc_info.value)

    def test_validate_schema_servers_not_array(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_schema({"servers": "not an array"})

        assert "'servers' must be an array" in str(exc_info.value)


class TestValidateServer:
    """Tests for validate_server function."""

    def test_validate_server_valid(self):
        server = {"name": "test", "command": "node", "args": ["script.js"]}
        validate_server(server, 0)

    def test_validate_server_not_dict(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_server("not a dict", 0)

        assert "must be an object" in str(exc_info.value)

    def test_validate_server_missing_name(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_server({"command": "node"}, 0)

        assert "missing required field 'name'" in str(exc_info.value)

    def test_validate_server_missing_command(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_server({"name": "test"}, 0)

        assert "missing required field 'command'" in str(exc_info.value)

    def test_validate_server_empty_name(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_server({"name": "", "command": "node"}, 0)

        assert "'name' must be a non-empty string" in str(exc_info.value)

    def test_validate_server_empty_command(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_server({"name": "test", "command": ""}, 0)

        assert "'command' must be a non-empty string" in str(exc_info.value)

    def test_validate_server_invalid_args(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_server({"name": "test", "command": "node", "args": "not array"}, 0)

        assert "'args' must be an array" in str(exc_info.value)

    def test_validate_server_invalid_env(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_server({"name": "test", "command": "node", "env": "not dict"}, 0)

        assert "'env' must be an object" in str(exc_info.value)

    def test_validate_server_invalid_timeout(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_server({"name": "test", "command": "node", "timeout": "30"}, 0)

        assert "'timeout' must be an integer" in str(exc_info.value)


class TestValidateNamespaces:
    """Tests for namespace validation."""

    def test_validate_namespaces_valid(self):
        servers = [{"name": "s1"}, {"name": "s2"}]
        namespaces = {
            "ns1": ["s1"],
            "ns2": {"servers": ["s2"], "extends": ["ns1"]},
        }
        validate_namespaces(namespaces, servers)

    def test_validate_namespaces_not_dict(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_namespaces(["not", "dict"], [])

        assert "'namespaces' must be an object" in str(exc_info.value)

    def test_validate_namespace_null(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_namespaces({"ns1": None}, [])

        assert "cannot be null" in str(exc_info.value)

    def test_validate_namespace_invalid_type(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_namespaces({"ns1": "invalid"}, [])

        assert "must be an array or object" in str(exc_info.value)

    def test_validate_namespace_unknown_server(self):
        servers = [{"name": "s1"}]
        namespaces = {"ns1": ["s1", "unknown"]}

        with pytest.raises(ConfigError) as exc_info:
            validate_namespaces(namespaces, servers)

        assert "references unknown server" in str(exc_info.value)
        assert "unknown" in str(exc_info.value)

    def test_validate_namespace_extends_unknown(self):
        servers = [{"name": "s1"}]
        namespaces = {
            "ns1": ["s1"],
            "ns2": {"servers": ["s1"], "extends": ["unknown_ns"]},
        }

        with pytest.raises(ConfigError) as exc_info:
            validate_namespaces(namespaces, servers)

        assert "extends unknown namespace" in str(exc_info.value)
        assert "unknown_ns" in str(exc_info.value)


class TestValidateNamespaceServers:
    """Tests for validate_namespace_servers function."""

    def test_validate_namespace_servers_valid(self):
        validate_namespace_servers("ns1", ["s1", "s2"], {"s1", "s2", "s3"})

    def test_validate_namespace_servers_not_array(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_namespace_servers("ns1", "not array", set())

        assert "servers must be an array" in str(exc_info.value)

    def test_validate_namespace_servers_non_string(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_namespace_servers("ns1", [123], set())

        assert "non-string server name" in str(exc_info.value)

    def test_validate_namespace_servers_unknown(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_namespace_servers("ns1", ["unknown"], {"s1"})

        assert "references unknown server" in str(exc_info.value)


class TestValidateNamespaceExtends:
    """Tests for validate_namespace_extends function."""

    def test_validate_extends_valid(self):
        namespaces = {"ns1": ["s1"], "ns2": ["s2"]}
        validate_namespace_extends("ns2", ["ns1"], namespaces)

    def test_validate_extends_string(self):
        namespaces = {"ns1": ["s1"], "ns2": ["s2"]}
        validate_namespace_extends("ns2", "ns1", namespaces)

    def test_validate_extends_none(self):
        validate_namespace_extends("ns", None, {})

    def test_validate_extends_invalid_type(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_namespace_extends("ns", 123, {})

        assert "must be a string, array, or null" in str(exc_info.value)

    def test_validate_extends_non_string_item(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_namespace_extends("ns", [123], {})

        assert "non-string value" in str(exc_info.value)


class TestValidateManifests:
    """Tests for validate_manifests function."""

    def test_validate_manifests_valid(self):
        validate_manifests({"startup_dwell_secs": 2.0})

    def test_validate_manifests_per_server_ttl(self):
        validate_manifests({"per_server_ttl": {"default_secs": 300}})

    def test_validate_manifests_invalid_startup_dwell(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_manifests({"startup_dwell_secs": "invalid"})

        assert "must be a number" in str(exc_info.value)

    def test_validate_manifests_negative_startup_dwell(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_manifests({"startup_dwell_secs": -1})

        assert "must be non-negative" in str(exc_info.value)

    def test_validate_manifests_invalid_ttl(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_manifests({"per_server_ttl": {"default_secs": "invalid"}})

        assert "default_secs must be a number" in str(exc_info.value)

    def test_validate_manifests_not_dict(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_manifests("not dict")

        assert "'manifests' must be an object" in str(exc_info.value)


class TestValidateSandbox:
    """Tests for validate_sandbox function."""

    def test_validate_sandbox_valid(self):
        validate_sandbox({"timeout_secs": 30, "memory_mb": 256})

    def test_validate_sandbox_invalid_timeout(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_sandbox({"timeout_secs": "invalid"})

        assert "timeout_secs must be an integer" in str(exc_info.value)

    def test_validate_sandbox_timeout_too_low(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_sandbox({"timeout_secs": 0})

        assert "timeout_secs must be at least 1" in str(exc_info.value)

    def test_validate_sandbox_invalid_memory(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_sandbox({"memory_mb": "invalid"})

        assert "memory_mb must be an integer" in str(exc_info.value)

    def test_validate_sandbox_memory_too_low(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_sandbox({"memory_mb": 0})

        assert "memory_mb must be at least 1" in str(exc_info.value)

    def test_validate_sandbox_not_dict(self):
        with pytest.raises(ConfigError) as exc_info:
            validate_sandbox("not dict")

        assert "'sandbox' must be an object" in str(exc_info.value)


class TestInterpolateEnvVars:
    """Tests for interpolate_env_vars function."""

    def test_interpolate_string(self):
        with patch.dict(os.environ, {"MY_VAR": "my_value"}):
            result = interpolate_env_vars({"key": "${MY_VAR}"})
            assert result["key"] == "my_value"

    def test_interpolate_nested(self):
        with patch.dict(os.environ, {"HOST": "localhost", "PORT": "8080"}):
            result = interpolate_env_vars(
                {
                    "server": {
                        "host": "${HOST}",
                        "config": {"port": "${PORT}"},
                    }
                }
            )
            assert result["server"]["host"] == "localhost"
            assert result["server"]["config"]["port"] == "8080"

    def test_interpolate_in_list(self):
        with patch.dict(os.environ, {"ARG": "value"}):
            result = interpolate_env_vars({"args": ["${ARG}", "static"]})
            assert result["args"] == ["value", "static"]

    def test_interpolate_missing_var(self):
        result = interpolate_env_vars({"key": "${MISSING_VAR}"})
        assert result["key"] == ""

    def test_interpolate_partial_match(self):
        with patch.dict(os.environ, {"NAME": "test"}):
            result = interpolate_env_vars({"cmd": "prefix-${NAME}-suffix"})
            assert result["cmd"] == "prefix-test-suffix"

    def test_interpolate_no_match(self):
        result = interpolate_env_vars({"key": "no vars here"})
        assert result["key"] == "no vars here"

    def test_interpolate_non_string_values(self):
        result = interpolate_env_vars(
            {
                "int": 42,
                "bool": True,
                "null": None,
            }
        )
        assert result["int"] == 42
        assert result["bool"] is True
        assert result["null"] is None


class TestV2ConfigIntegration:
    """Integration tests for v2.0 config validation."""

    def test_full_v2_config_valid(self, sample_v2_config: Dict[str, Any]):
        validate_schema(sample_v2_config)

    def test_minimal_v2_config(self):
        config = {"servers": [{"name": "test", "command": "echo"}]}
        validate_schema(config)

    def test_config_with_empty_namespaces(self):
        config = {"servers": [{"name": "test", "command": "echo"}], "namespaces": {}}
        validate_schema(config)

    def test_config_with_circular_inheritance_allowed(self):
        config = {
            "servers": [{"name": "s1", "command": "echo"}],
            "namespaces": {
                "ns1": {"servers": ["s1"], "extends": ["ns2"]},
                "ns2": {"servers": ["s1"], "extends": ["ns1"]},
            },
        }
        validate_schema(config)

    def test_config_with_deep_inheritance(self):
        config = {
            "servers": [{"name": "s1", "command": "echo"}],
            "namespaces": {
                "base": ["s1"],
                "mid": {"servers": [], "extends": ["base"]},
                "top": {"servers": [], "extends": ["mid"]},
            },
        }
        validate_schema(config)
