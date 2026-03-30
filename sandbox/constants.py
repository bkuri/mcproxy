"""Security constants and blocklist definitions for sandbox execution.

Contains blocklists for imports, builtins, and attributes that are restricted
for security purposes.
"""

from typing import List

# Constants from security.py (re-exported for backward compatibility)
from sandbox.security import BLOCKED_BUILTINS, BLOCKED_IMPORTS, MAX_CODE_SIZE_BYTES

__all__ = [
    "BLOCKED_BUILTINS",
    "BLOCKED_IMPORTS",
    "MAX_CODE_SIZE_BYTES",
    "get_blocked_functions",
    "get_blocked_imports",
    "get_blocked_attributes",
]


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
