"""Code validation utilities for sandbox execution.

Provides pre-execution validation to ensure code meets security requirements
before being executed in the sandbox.
"""

import ast
import unicodedata
from typing import Optional, Tuple

from code_validator import validate_code_for_dangerous_patterns
from sandbox.constants import (
    BLOCKED_BUILTINS,
    BLOCKED_IMPORTS,
    MAX_CODE_SIZE_BYTES,
)

__all__ = [
    "validate_code",
    "_check_blocked_imports",
    "_check_blocked_builtins",
]


def validate_code(code: str) -> Tuple[bool, str]:
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

    code_for_analysis = _strip_comments(normalized)

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

    blocked = _check_blocked_imports(tree)
    if blocked:
        return (
            False,
            f"Blocked import detected: {blocked}. Call get_blocked_imports() for full list.",
        )

    blocked_builtin = _check_blocked_builtins(tree)
    if blocked_builtin:
        return (
            False,
            f"Blocked builtin detected: {blocked_builtin}(). Call get_blocked_functions() for full list.",
        )

    return True, ""


def _strip_comments(code: str) -> str:
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


def _check_blocked_imports(tree: ast.AST) -> Optional[str]:
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


def _check_blocked_builtins(tree: ast.AST) -> Optional[str]:
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
