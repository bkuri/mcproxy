"""Configuration loading and validation for MCProxy v2.0.

Handles loading mcproxy.json, validating schema, and interpolating
environment variables. Supports v2.0 features: namespaces, groups, manifests, sandbox.
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from logging_config import get_logger

logger = get_logger(__name__)


class ConfigError(Exception):
    """Error loading or validating configuration."""

    pass


def load_config(path: str) -> Dict[str, Any]:
    """Load and validate configuration from JSON file.

    Args:
        path: Path to mcproxy.json file

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

    server_count = len(config.get("servers", []))
    namespace_count = len(config.get("namespaces", {}))
    logger.info(
        f"Loaded config from {path} with {server_count} servers, "
        f"{namespace_count} namespaces"
    )
    return config


def validate_schema(config: Dict[str, Any]) -> None:
    """Validate configuration schema (v2.0).

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
        validate_server(server, i)

    if "namespaces" in config:
        validate_namespaces(config["namespaces"], config["servers"])

    if "groups" in config:
        validate_groups(config["groups"], config.get("namespaces", {}))

    if "manifests" in config:
        validate_manifests(config["manifests"])

    if "sandbox" in config:
        validate_sandbox(config["sandbox"])


def validate_config_with_result(
    config: Dict[str, Any],
) -> Tuple[bool, List[str], List[str]]:
    """Validate configuration and return result with errors and warnings.

    Args:
        config: Configuration dictionary to validate

    Returns:
        Tuple of (is_valid, errors, warnings)
    """
    errors: List[str] = []
    warnings: List[str] = []

    if not isinstance(config, dict):
        return (False, ["Config must be a JSON object"], [])

    if "servers" not in config:
        return (False, ["Config missing required 'servers' field"], [])

    if not isinstance(config["servers"], list):
        return (False, ["'servers' must be an array"], [])

    for i, server in enumerate(config["servers"]):
        try:
            validate_server(server, i)
        except ConfigError as e:
            errors.append(str(e))

    namespaces = config.get("namespaces", {})
    if "namespaces" in config:
        ns_warnings = validate_namespaces_with_result(
            config["namespaces"], config["servers"]
        )
        warnings.extend(ns_warnings)

    if "groups" in config:
        group_errors, group_warnings = validate_groups_with_result(
            config["groups"], namespaces
        )
        errors.extend(group_errors)
        warnings.extend(group_warnings)

    if "manifests" in config:
        try:
            validate_manifests(config["manifests"])
        except ConfigError as e:
            errors.append(str(e))

    if "sandbox" in config:
        try:
            validate_sandbox(config["sandbox"])
        except ConfigError as e:
            errors.append(str(e))

    return (len(errors) == 0, errors, warnings)


def validate_namespaces_with_result(
    namespaces: Dict[str, Any], servers: List[Dict]
) -> List[str]:
    """Validate namespace configuration and return warnings.

    Args:
        namespaces: Namespace configuration dict
        servers: List of server configs

    Returns:
        List of warning messages
    """
    warnings: List[str] = []

    if not isinstance(namespaces, dict):
        return warnings

    server_names = {s["name"] for s in servers}

    for ns_name, ns_config in namespaces.items():
        if ns_config is None:
            continue

        if isinstance(ns_config, dict):
            if "isolated" in ns_config and ns_config.get("isolated"):
                warnings.append(f"Namespace '{ns_name}' is marked as isolated")

    return warnings


def validate_groups_with_result(
    groups: Dict[str, Any], namespaces: Dict[str, Any]
) -> Tuple[List[str], List[str]]:
    """Validate groups configuration and return errors and warnings.

    Args:
        groups: Groups configuration dict
        namespaces: Namespace configuration dict

    Returns:
        Tuple of (errors, warnings)
    """
    errors: List[str] = []
    warnings: List[str] = []

    if not isinstance(groups, dict):
        errors.append("'groups' must be an object")
        return (errors, warnings)

    for group_name, group_config in groups.items():
        if group_config is None:
            errors.append(f"Group '{group_name}' cannot be null")
            continue

        if not isinstance(group_config, dict):
            errors.append(f"Group '{group_name}' must be an object")
            continue

        if "namespaces" not in group_config:
            errors.append(f"Group '{group_name}' must have a 'namespaces' array")
            continue

        if not isinstance(group_config["namespaces"], list):
            errors.append(f"Group '{group_name}' 'namespaces' must be an array")
            continue

        for ns_ref in group_config["namespaces"]:
            if not isinstance(ns_ref, str):
                errors.append(
                    f"Group '{group_name}' has non-string namespace reference: {ns_ref}"
                )
                continue

            has_force_prefix = ns_ref.startswith("!")
            actual_ns_name = ns_ref[1:] if has_force_prefix else ns_ref

            if actual_ns_name not in namespaces:
                errors.append(
                    f"Group '{group_name}' references unknown namespace '{actual_ns_name}'"
                )
                continue

            ns_def = namespaces.get(actual_ns_name)
            is_isolated = False
            if isinstance(ns_def, dict):
                is_isolated = ns_def.get("isolated", False)

            if is_isolated:
                if has_force_prefix:
                    warnings.append(
                        f"Group '{group_name}' forcefully includes isolated namespace '{actual_ns_name}'"
                    )
                else:
                    errors.append(
                        f"Group '{group_name}' references isolated namespace '{actual_ns_name}' "
                        f"without '!' prefix. Use '!{actual_ns_name}' to force inclusion."
                    )
                    warnings.append(
                        f"Group '{group_name}' references isolated namespace '{actual_ns_name}' "
                        f"without '!' prefix - rejecting group"
                    )

    return (errors, warnings)


def validate_server(server: Dict[str, Any], index: int) -> None:
    """Validate a single server configuration.

    Args:
        server: Server configuration dict
        index: Server index for error messages

    Raises:
        ConfigError: If server config is invalid
    """
    if not isinstance(server, dict):
        raise ConfigError(f"Server {index} must be an object")

    required_fields = ["name", "command"]
    for field in required_fields:
        if field not in server:
            raise ConfigError(f"Server {index} missing required field '{field}'")

    if not isinstance(server["name"], str) or not server["name"]:
        raise ConfigError(f"Server {index} 'name' must be a non-empty string")

    if not isinstance(server["command"], str) or not server["command"]:
        raise ConfigError(f"Server {index} 'command' must be a non-empty string")

    if "args" in server and not isinstance(server["args"], list):
        raise ConfigError(f"Server {index} 'args' must be an array")

    if "env" in server and not isinstance(server["env"], dict):
        raise ConfigError(f"Server {index} 'env' must be an object")

    if "timeout" in server and not isinstance(server["timeout"], int):
        raise ConfigError(f"Server {index} 'timeout' must be an integer")


def validate_namespaces(namespaces: Dict[str, Any], servers: List[Dict]) -> None:
    """Validate namespace configuration.

    Args:
        namespaces: Namespace configuration dict
        servers: List of server configs

    Raises:
        ConfigError: If namespace config is invalid
    """
    if not isinstance(namespaces, dict):
        raise ConfigError("'namespaces' must be an object")

    server_names = {s["name"] for s in servers}

    for ns_name, ns_config in namespaces.items():
        if ns_config is None:
            raise ConfigError(f"Namespace '{ns_name}' cannot be null")

        if isinstance(ns_config, list):
            validate_namespace_servers(ns_name, ns_config, server_names)
        elif isinstance(ns_config, dict):
            if "servers" in ns_config:
                validate_namespace_servers(ns_name, ns_config["servers"], server_names)
            else:
                raise ConfigError(f"Namespace '{ns_name}' must have a 'servers' array")
            if "isolated" in ns_config:
                if not isinstance(ns_config["isolated"], bool):
                    raise ConfigError(
                        f"Namespace '{ns_name}' 'isolated' must be a boolean"
                    )
            if "extends" in ns_config:
                validate_namespace_extends(ns_name, ns_config["extends"], namespaces)
        else:
            raise ConfigError(f"Namespace '{ns_name}' must be an array or object")


def validate_namespace_servers(
    ns_name: str, servers: List[str], all_server_names: Set[str]
) -> None:
    """Validate servers list in a namespace.

    Args:
        ns_name: Namespace name
        servers: List of server names
        all_server_names: Set of all valid server names

    Raises:
        ConfigError: If servers list is invalid
    """
    if not isinstance(servers, list):
        raise ConfigError(f"Namespace '{ns_name}' servers must be an array")

    for server_name in servers:
        if not isinstance(server_name, str):
            raise ConfigError(
                f"Namespace '{ns_name}' has non-string server name: {server_name}"
            )
        if server_name not in all_server_names:
            raise ConfigError(
                f"Namespace '{ns_name}' references unknown server '{server_name}'"
            )


def validate_namespace_extends(
    ns_name: str, extends: Any, namespaces: Dict[str, Any]
) -> None:
    """Validate extends field in a namespace.

    Args:
        ns_name: Namespace name
        extends: Value of extends field
        namespaces: All namespace configurations

    Raises:
        ConfigError: If extends is invalid
    """
    if extends is None:
        return

    if isinstance(extends, str):
        extends = [extends]
    elif not isinstance(extends, list):
        raise ConfigError(
            f"Namespace '{ns_name}' extends must be a string, array, or null"
        )

    for parent in extends:
        if not isinstance(parent, str):
            raise ConfigError(
                f"Namespace '{ns_name}' extends has non-string value: {parent}"
            )
        if parent not in namespaces:
            raise ConfigError(
                f"Namespace '{ns_name}' extends unknown namespace '{parent}'"
            )


def validate_groups(groups: Dict[str, Any], namespaces: Dict[str, Any]) -> None:
    """Validate groups configuration.

    Args:
        groups: Groups configuration dict
        namespaces: Namespace configuration dict

    Raises:
        ConfigError: If groups config is invalid
    """
    if not isinstance(groups, dict):
        raise ConfigError("'groups' must be an object")

    for group_name, group_config in groups.items():
        if group_config is None:
            raise ConfigError(f"Group '{group_name}' cannot be null")

        if not isinstance(group_config, dict):
            raise ConfigError(f"Group '{group_name}' must be an object")

        if "namespaces" not in group_config:
            raise ConfigError(f"Group '{group_name}' must have a 'namespaces' array")

        if not isinstance(group_config["namespaces"], list):
            raise ConfigError(f"Group '{group_name}' 'namespaces' must be an array")

        for ns_ref in group_config["namespaces"]:
            if not isinstance(ns_ref, str):
                raise ConfigError(
                    f"Group '{group_name}' has non-string namespace reference: {ns_ref}"
                )

            has_force_prefix = ns_ref.startswith("!")
            actual_ns_name = ns_ref[1:] if has_force_prefix else ns_ref

            if actual_ns_name not in namespaces:
                raise ConfigError(
                    f"Group '{group_name}' references unknown namespace '{actual_ns_name}'"
                )

            ns_def = namespaces.get(actual_ns_name)
            is_isolated = False
            if isinstance(ns_def, dict):
                is_isolated = ns_def.get("isolated", False)

            if is_isolated:
                if has_force_prefix:
                    logger.warning(
                        f"Group '{group_name}' forcefully includes isolated namespace '{actual_ns_name}'"
                    )
                else:
                    logger.warning(
                        f"Group '{group_name}' references isolated namespace '{actual_ns_name}' "
                        f"without '!' prefix - rejecting group"
                    )
                    raise ConfigError(
                        f"Group '{group_name}' references isolated namespace '{actual_ns_name}' "
                        f"without '!' prefix. Use '!{actual_ns_name}' to force inclusion."
                    )


def validate_manifests(manifests: Dict[str, Any]) -> None:
    """Validate manifests configuration.

    Args:
        manifests: Manifests configuration dict

    Raises:
        ConfigError: If manifests config is invalid
    """
    if not isinstance(manifests, dict):
        raise ConfigError("'manifests' must be an object")

    if "startup_dwell_secs" in manifests:
        if not isinstance(manifests["startup_dwell_secs"], (int, float)):
            raise ConfigError("manifests.startup_dwell_secs must be a number")
        if manifests["startup_dwell_secs"] < 0:
            raise ConfigError("manifests.startup_dwell_secs must be non-negative")

    if "per_server_ttl" in manifests:
        ttl = manifests["per_server_ttl"]
        if isinstance(ttl, dict):
            if "default_secs" in ttl and not isinstance(
                ttl["default_secs"], (int, float)
            ):
                raise ConfigError("per_server_ttl.default_secs must be a number")
        elif ttl is not None and not isinstance(ttl, (int, float)):
            raise ConfigError("per_server_ttl must be a number, object, or null")


def validate_sandbox(sandbox: Dict[str, Any]) -> None:
    """Validate sandbox configuration.

    Args:
        sandbox: Sandbox configuration dict

    Raises:
        ConfigError: If sandbox config is invalid
    """
    if not isinstance(sandbox, dict):
        raise ConfigError("'sandbox' must be an object")

    if "timeout_secs" in sandbox:
        if not isinstance(sandbox["timeout_secs"], int):
            raise ConfigError("sandbox.timeout_secs must be an integer")
        if sandbox["timeout_secs"] < 1:
            raise ConfigError("sandbox.timeout_secs must be at least 1")

    if "memory_mb" in sandbox:
        if not isinstance(sandbox["memory_mb"], int):
            raise ConfigError("sandbox.memory_mb must be an integer")
        if sandbox["memory_mb"] < 1:
            raise ConfigError("sandbox.memory_mb must be at least 1")


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
