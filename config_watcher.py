"""Configuration loading and validation for MCProxy.

Handles loading mcp-servers.json, validating schema, and interpolating
environment variables.
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List

from logging_config import get_logger

logger = get_logger(__name__)


class ConfigError(Exception):
    """Error loading or validating configuration."""

    pass


def load_config(path: str) -> Dict[str, Any]:
    """Load and validate configuration from JSON file.

    Args:
        path: Path to mcp-servers.json file

    Returns:
        Validated configuration dictionary

    Raises:
        ConfigError: If config is invalid or file cannot be read
    """
    config_path = Path(path)

    if not config_path.exists():
        raise ConfigError(f"Config file not found: {path}")

    try:
        with open(config_path, "r") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in {path}: {e}")
    except Exception as e:
        raise ConfigError(f"Failed to read {path}: {e}")

    validate_schema(config)
    config = interpolate_env_vars(config)

    logger.info(
        f"Loaded config from {path} with {len(config.get('servers', []))} servers"
    )
    return config


def validate_schema(config: Dict[str, Any]) -> None:
    """Validate configuration schema.

    Args:
        config: Configuration dictionary to validate

    Raises:
        ConfigError: If schema validation fails
    """
    if not isinstance(config, dict):
        raise ConfigError("Config must be a JSON object")

    if "servers" not in config:
        raise ConfigError("Config missing required 'servers' field")

    if not isinstance(config["servers"], list):
        raise ConfigError("'servers' must be an array")

    for i, server in enumerate(config["servers"]):
        if not isinstance(server, dict):
            raise ConfigError(f"Server {i} must be an object")

        required_fields = ["name", "command"]
        for field in required_fields:
            if field not in server:
                raise ConfigError(f"Server {i} missing required field '{field}'")

        if not isinstance(server["name"], str) or not server["name"]:
            raise ConfigError(f"Server {i} 'name' must be a non-empty string")

        if not isinstance(server["command"], str) or not server["command"]:
            raise ConfigError(f"Server {i} 'command' must be a non-empty string")

        # Validate optional fields
        if "args" in server and not isinstance(server["args"], list):
            raise ConfigError(f"Server {i} 'args' must be an array")

        if "env" in server and not isinstance(server["env"], dict):
            raise ConfigError(f"Server {i} 'env' must be an object")

        if "timeout" in server and not isinstance(server["timeout"], int):
            raise ConfigError(f"Server {i} 'timeout' must be an integer")


def interpolate_env_vars(config: Dict[str, Any]) -> Dict[str, Any]:
    """Interpolate environment variables in config values.

    Replaces ${VAR_NAME} with the value of the environment variable.

    Args:
        config: Configuration dictionary

    Returns:
        Config with interpolated environment variables
    """
    env_pattern = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

    def interpolate(value: Any) -> Any:
        if isinstance(value, str):

            def replace_var(match: re.Match) -> str:
                var_name = match.group(1)
                var_value = os.environ.get(var_name)
                if var_value is None:
                    logger.warning(
                        f"Environment variable {var_name} not found, using empty string"
                    )
                    return ""
                return var_value

            return env_pattern.sub(replace_var, value)
        elif isinstance(value, dict):
            return {k: interpolate(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [interpolate(v) for v in value]
        return value

    return interpolate(config)
