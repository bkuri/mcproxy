"""Reusable validation utilities for MCProxy configuration.

Provides type validation functions that raise ConfigError on validation failures.
"""

from typing import Any


class ConfigError(Exception):
    """Error loading or validating configuration."""

    pass


def require_type(value: Any, expected_type: type, field_name: str) -> None:
    """Validate that a value is of the expected type.

    Args:
        value: The value to validate
        expected_type: The expected type (e.g., str, int, dict)
        field_name: The field name for error messages

    Raises:
        ConfigError: If value is not of the expected type
    """
    if not isinstance(value, expected_type):
        type_name = expected_type.__name__
        raise ConfigError(f"'{field_name}' must be a {type_name}")


def require_string(value: Any, field_name: str) -> None:
    """Validate that a value is a non-empty string.

    Args:
        value: The value to validate
        field_name: The field name for error messages

    Raises:
        ConfigError: If value is not a string or is empty
    """
    if not isinstance(value, str) or not value:
        raise ConfigError(f"'{field_name}' must be a non-empty string")


def require_dict(value: Any, field_name: str) -> None:
    """Validate that a value is a dict.

    Args:
        value: The value to validate
        field_name: The field name for error messages

    Raises:
        ConfigError: If value is not a dict
    """
    require_type(value, dict, field_name)


def require_list(value: Any, field_name: str) -> None:
    """Validate that a value is a list.

    Args:
        value: The value to validate
        field_name: The field name for error messages

    Raises:
        ConfigError: If value is not a list
    """
    require_type(value, list, field_name)


def require_int(value: Any, field_name: str) -> None:
    """Validate that a value is an int.

    Args:
        value: The value to validate
        field_name: The field name for error messages

    Raises:
        ConfigError: If value is not an int
    """
    require_type(value, int, field_name)


def require_bool(value: Any, field_name: str) -> None:
    """Validate that a value is a bool.

    Args:
        value: The value to validate
        field_name: The field name for error messages

    Raises:
        ConfigError: If value is not a bool
    """
    require_type(value, bool, field_name)
