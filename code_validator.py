"""AST-based code validation for detecting dangerous patterns.

Catches security issues that string-based checks miss, including:
- Dynamic imports via importlib
- Reflection/dunder attribute access
- Pickle/marshal deserialization
- Type manipulation attacks
"""

import ast
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Set, Tuple


class Severity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Violation:
    pattern: str
    message: str
    line: int
    severity: Severity = Severity.HIGH


DANGEROUS_CALLS: dict[str, Severity] = {
    "os.system": Severity.CRITICAL,
    "os.popen": Severity.CRITICAL,
    "os.spawnl": Severity.CRITICAL,
    "os.spawnle": Severity.CRITICAL,
    "os.spawnlp": Severity.CRITICAL,
    "os.spawnlpe": Severity.CRITICAL,
    "os.spawnv": Severity.CRITICAL,
    "os.spawnve": Severity.CRITICAL,
    "os.spawnvp": Severity.CRITICAL,
    "os.spawnvpe": Severity.CRITICAL,
    "os.execl": Severity.CRITICAL,
    "os.execle": Severity.CRITICAL,
    "os.execlp": Severity.CRITICAL,
    "os.execlpe": Severity.CRITICAL,
    "os.execv": Severity.CRITICAL,
    "os.execve": Severity.CRITICAL,
    "os.execvp": Severity.CRITICAL,
    "os.execvpe": Severity.CRITICAL,
    "subprocess.run": Severity.CRITICAL,
    "subprocess.call": Severity.CRITICAL,
    "subprocess.Popen": Severity.CRITICAL,
    "subprocess.check_output": Severity.CRITICAL,
    "subprocess.check_call": Severity.CRITICAL,
    "pickle.loads": Severity.CRITICAL,
    "pickle.load": Severity.CRITICAL,
    "marshal.loads": Severity.CRITICAL,
    "marshal.load": Severity.CRITICAL,
    "importlib.import_module": Severity.CRITICAL,
    "importlib.__import__": Severity.CRITICAL,
    "eval": Severity.CRITICAL,
    "exec": Severity.CRITICAL,
    "compile": Severity.HIGH,
    "type.__new__": Severity.CRITICAL,
    "object.__setattr__": Severity.HIGH,
    "object.__getattribute__": Severity.HIGH,
    "object.__delattr__": Severity.HIGH,
    "setattr": Severity.HIGH,
    "delattr": Severity.HIGH,
    "hasattr": Severity.MEDIUM,
    "__import__": Severity.CRITICAL,
    "breakpoint": Severity.MEDIUM,
    "open": Severity.HIGH,
    "input": Severity.LOW,
}

DANGEROUS_ATTRIBUTES: set[str] = {
    "__class__",
    "__bases__",
    "__subclasses__",
    "__globals__",
    "__locals__",
    "__code__",
    "__builtins__",
    "__import__",
    "__dict__",
    "__mro__",
    "__init__",
    "__new__",
    "__reduce__",
    "__reduce_ex__",
    "__getstate__",
    "__setstate__",
}

DANGEROUS_MODULES: set[str] = {
    "pickle",
    "marshal",
    "shelve",
    "dill",
    "jsonpickle",
    "importlib",
}


class DangerousPatternValidator(ast.NodeVisitor):
    """AST visitor that detects dangerous code patterns.

    Detects:
    - Dangerous function/method calls (os.system, eval, etc.)
    - Reflection via dunder attributes
    - String-based namespace access (getattr with string)
    - Imports of dangerous modules
    """

    def __init__(self):
        self.violations: List[Violation] = []
        self._imported_modules: Set[str] = set()

    def validate(self, code: str) -> Tuple[bool, List[Violation]]:
        """Validate code for dangerous patterns.

        Args:
            code: Python source code to validate

        Returns:
            Tuple of (is_valid, violations_list)
        """
        self.violations = []
        self._imported_modules = set()

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return True, []

        self.visit(tree)
        return len(self.violations) == 0, self.violations

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            module_base = alias.name.split(".")[0]
            self._imported_modules.add(module_base)
            if module_base in DANGEROUS_MODULES:
                self.violations.append(
                    Violation(
                        pattern=f"import {module_base}",
                        message=f"Dangerous module import: '{module_base}'",
                        line=node.lineno,
                        severity=Severity.CRITICAL,
                    )
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            module_base = node.module.split(".")[0]
            self._imported_modules.add(module_base)
            if module_base in DANGEROUS_MODULES:
                self.violations.append(
                    Violation(
                        pattern=f"from {module_base} import",
                        message=f"Dangerous module import: '{module_base}'",
                        line=node.lineno,
                        severity=Severity.CRITICAL,
                    )
                )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        call_name = self._get_call_name(node.func)

        if call_name:
            if call_name in DANGEROUS_CALLS:
                self.violations.append(
                    Violation(
                        pattern=call_name,
                        message=f"Dangerous function call: '{call_name}()' at line {node.lineno}",
                        line=node.lineno,
                        severity=DANGEROUS_CALLS[call_name],
                    )
                )
            elif call_name == "getattr":
                if len(node.args) >= 2:
                    if isinstance(node.args[1], ast.Constant) and isinstance(
                        node.args[1].value, str
                    ):
                        attr_name = node.args[1].value
                        if attr_name in DANGEROUS_ATTRIBUTES:
                            self.violations.append(
                                Violation(
                                    pattern=f"getattr(*, '{attr_name}')",
                                    message=f"Dangerous attribute access via getattr: '{attr_name}'",
                                    line=node.lineno,
                                    severity=Severity.CRITICAL,
                                )
                            )
                    elif not isinstance(node.args[1], ast.Constant):
                        self.violations.append(
                            Violation(
                                pattern="getattr(*, dynamic)",
                                message="Dynamic attribute access via getattr (potential bypass)",
                                line=node.lineno,
                                severity=Severity.HIGH,
                            )
                        )

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in DANGEROUS_ATTRIBUTES:
            self.violations.append(
                Violation(
                    pattern=f".{node.attr}",
                    message=f"Dangerous attribute access: '.{node.attr}'",
                    line=node.lineno,
                    severity=Severity.CRITICAL,
                )
            )
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in DANGEROUS_ATTRIBUTES:
            self.violations.append(
                Violation(
                    pattern=node.id,
                    message=f"Dangerous name reference: '{node.id}'",
                    line=node.lineno,
                    severity=Severity.CRITICAL,
                )
            )
        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            key = node.slice.value
            if key in DANGEROUS_ATTRIBUTES:
                self.violations.append(
                    Violation(
                        pattern=f'["{key}"]',
                        message=f"Dangerous attribute access via subscript: '[\"{key}\"]'",
                        line=node.lineno,
                        severity=Severity.CRITICAL,
                    )
                )
        self.generic_visit(node)

    def _get_call_name(self, node: ast.expr) -> Optional[str]:
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            parts = []
            current = node
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            parts.reverse()
            return ".".join(parts)
        return None


def validate_code_for_dangerous_patterns(code: str) -> Tuple[bool, Optional[dict]]:
    """Validate code for dangerous patterns.

    Args:
        code: Python source code to validate

    Returns:
        Tuple of (is_valid, error_dict or None)
        error_dict format: {
            "status": "error",
            "error": "Dangerous pattern detected: 'os.system()' at line 5",
            "line": 5,
            "pattern": "os.system"
        }
    """
    validator = DangerousPatternValidator()
    is_valid, violations = validator.validate(code)

    if is_valid:
        return True, None

    critical_violations = [
        v for v in violations if v.severity in (Severity.CRITICAL, Severity.HIGH)
    ]
    if critical_violations:
        v = critical_violations[0]
        return False, {
            "status": "error",
            "error": v.message,
            "line": v.line,
            "pattern": v.pattern,
        }

    v = violations[0]
    return False, {
        "status": "error",
        "error": v.message,
        "line": v.line,
        "pattern": v.pattern,
    }
