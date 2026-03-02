"""Security constants and utilities for sandbox execution."""

from typing import List, Optional

from utils.fuzzy_match import suggest_best_match

FUZZY_MATCH_THRESHOLD: float = 0.6
MAX_SUGGESTIONS: int = 5


def suggest_tool_fix(tool_name: str, available_tools: List[str]) -> Optional[str]:
    """Suggest a tool name correction using fuzzy matching.

    Args:
        tool_name: The misspelled tool name
        available_tools: List of valid tool names to search

    Returns:
        Suggestion string if a close match is found, otherwise list of available tools
    """
    return suggest_best_match(
        tool_name, available_tools, FUZZY_MATCH_THRESHOLD, MAX_SUGGESTIONS
    )


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
