"""Tests for code_validator.py - AST-based dangerous pattern detection."""

import pytest

from code_validator import (
    DangerousPatternValidator,
    Severity,
    Violation,
    DANGEROUS_CALLS,
    DANGEROUS_ATTRIBUTES,
    DANGEROUS_MODULES,
    validate_code_for_dangerous_patterns,
)


class TestDangerousPatternValidatorBasics:
    """Tests for basic validator functionality."""

    def test_safe_code_passes(self):
        validator = DangerousPatternValidator()
        code = "x = 1 + 2\nresult = x * 3"
        is_valid, violations = validator.validate(code)
        assert is_valid is True
        assert violations == []

    def test_safe_code_with_imports(self):
        validator = DangerousPatternValidator()
        code = "import json\nimport math\nx = json.dumps({'a': 1})"
        is_valid, violations = validator.validate(code)
        assert is_valid is True
        assert violations == []

    def test_safe_code_with_classes(self):
        validator = DangerousPatternValidator()
        code = """
class MyClass:
    def __init__(self, value):
        self.value = value
    
    def get_value(self):
        return self.value
"""
        is_valid, violations = validator.validate(code)
        assert is_valid is True
        assert violations == []

    def test_syntax_error_returns_valid(self):
        validator = DangerousPatternValidator()
        code = "def broken(\npass"
        is_valid, violations = validator.validate(code)
        assert is_valid is True


class TestOsSystemCalls:
    """Tests for os.system and related dangerous calls."""

    def test_os_system(self):
        validator = DangerousPatternValidator()
        code = "import os\nos.system('ls')"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert len(violations) >= 1
        assert any("os.system" in v.pattern for v in violations)

    def test_os_popen(self):
        validator = DangerousPatternValidator()
        code = "import os\nos.popen('ls')"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("os.popen" in v.pattern for v in violations)

    def test_os_spawnl(self):
        validator = DangerousPatternValidator()
        code = "import os\nos.spawnl(os.P_WAIT, 'ls')"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("os.spawn" in v.pattern for v in violations)

    def test_os_execl(self):
        validator = DangerousPatternValidator()
        code = "import os\nos.execl('/bin/ls', 'ls')"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("os.exec" in v.pattern for v in violations)


class TestSubprocessCalls:
    """Tests for subprocess module dangerous calls."""

    def test_subprocess_run(self):
        validator = DangerousPatternValidator()
        code = "import subprocess\nsubprocess.run(['ls'])"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("subprocess.run" in v.pattern for v in violations)

    def test_subprocess_call(self):
        validator = DangerousPatternValidator()
        code = "import subprocess\nsubprocess.call(['ls'])"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("subprocess.call" in v.pattern for v in violations)

    def test_subprocess_popen(self):
        validator = DangerousPatternValidator()
        code = "import subprocess\nsubprocess.Popen(['ls'])"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("subprocess.Popen" in v.pattern for v in violations)

    def test_subprocess_check_output(self):
        validator = DangerousPatternValidator()
        code = "import subprocess\nsubprocess.check_output(['ls'])"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("subprocess.check_output" in v.pattern for v in violations)

    def test_subprocess_check_call(self):
        validator = DangerousPatternValidator()
        code = "import subprocess\nsubprocess.check_call(['ls'])"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("subprocess.check_call" in v.pattern for v in violations)


class TestPickleMarshalDeserialization:
    """Tests for pickle/marshal deserialization attacks."""

    def test_pickle_loads(self):
        validator = DangerousPatternValidator()
        code = "import pickle\npickle.loads(data)"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("pickle.loads" in v.pattern for v in violations)

    def test_pickle_load(self):
        validator = DangerousPatternValidator()
        code = "import pickle\npickle.load(file)"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("pickle.load" in v.pattern for v in violations)

    def test_marshal_loads(self):
        validator = DangerousPatternValidator()
        code = "import marshal\nmarshal.loads(data)"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("marshal.loads" in v.pattern for v in violations)

    def test_marshal_load(self):
        validator = DangerousPatternValidator()
        code = "import marshal\nmarshal.load(file)"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("marshal.load" in v.pattern for v in violations)

    def test_pickle_module_import(self):
        validator = DangerousPatternValidator()
        code = "import pickle"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("pickle" in v.pattern for v in violations)

    def test_marshal_module_import(self):
        validator = DangerousPatternValidator()
        code = "import marshal"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("marshal" in v.pattern for v in violations)

    def test_from_pickle_import(self):
        validator = DangerousPatternValidator()
        code = "from pickle import loads"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("pickle" in v.pattern for v in violations)


class TestImportlibDynamicImports:
    """Tests for importlib dynamic import attacks."""

    def test_importlib_import_module(self):
        validator = DangerousPatternValidator()
        code = "import importlib\nimportlib.import_module('os')"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("importlib.import_module" in v.pattern for v in violations)

    def test_importlib_module_import(self):
        validator = DangerousPatternValidator()
        code = "import importlib"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("importlib" in v.pattern for v in violations)

    def test_from_importlib_import(self):
        validator = DangerousPatternValidator()
        code = "from importlib import import_module"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("importlib" in v.pattern for v in violations)


class TestEvalExecCompile:
    """Tests for eval/exec/compile dangerous calls."""

    def test_eval_call(self):
        validator = DangerousPatternValidator()
        code = "eval('1 + 1')"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("eval" in v.pattern for v in violations)

    def test_exec_call(self):
        validator = DangerousPatternValidator()
        code = "exec('x = 1')"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("exec" in v.pattern for v in violations)

    def test_compile_call(self):
        validator = DangerousPatternValidator()
        code = "compile('x = 1', '<string>', 'exec')"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("compile" in v.pattern for v in violations)

    def test_eval_with_variable(self):
        validator = DangerousPatternValidator()
        code = "code = '1+1'\nresult = eval(code)"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("eval" in v.pattern for v in violations)


class TestReflectionAttributeAccess:
    """Tests for dangerous dunder attribute access."""

    def test_class_attribute(self):
        validator = DangerousPatternValidator()
        code = "x = obj.__class__"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("__class__" in v.pattern for v in violations)

    def test_globals_attribute(self):
        validator = DangerousPatternValidator()
        code = "x = func.__globals__"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("__globals__" in v.pattern for v in violations)

    def test_dict_attribute(self):
        validator = DangerousPatternValidator()
        code = "x = obj.__dict__"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("__dict__" in v.pattern for v in violations)

    def test_code_attribute(self):
        validator = DangerousPatternValidator()
        code = "x = func.__code__"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("__code__" in v.pattern for v in violations)

    def test_builtins_attribute(self):
        validator = DangerousPatternValidator()
        code = "x = __builtins__"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("__builtins__" in v.pattern for v in violations)

    def test_bases_attribute(self):
        validator = DangerousPatternValidator()
        code = "x = cls.__bases__"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("__bases__" in v.pattern for v in violations)

    def test_subclasses_attribute(self):
        validator = DangerousPatternValidator()
        code = "x = cls.__subclasses__()"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("__subclasses__" in v.pattern for v in violations)

    def test_mro_attribute(self):
        validator = DangerousPatternValidator()
        code = "x = cls.__mro__"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("__mro__" in v.pattern for v in violations)

    def test_init_attribute(self):
        validator = DangerousPatternValidator()
        code = "x = obj.__init__"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("__init__" in v.pattern for v in violations)

    def test_reduce_attribute(self):
        validator = DangerousPatternValidator()
        code = "x = obj.__reduce__"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("__reduce__" in v.pattern for v in violations)

    def test_reduce_ex_attribute(self):
        validator = DangerousPatternValidator()
        code = "x = obj.__reduce_ex__"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("__reduce_ex__" in v.pattern for v in violations)

    def test_getstate_attribute(self):
        validator = DangerousPatternValidator()
        code = "x = obj.__getstate__"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("__getstate__" in v.pattern for v in violations)

    def test_setstate_attribute(self):
        validator = DangerousPatternValidator()
        code = "x = obj.__setstate__"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("__setstate__" in v.pattern for v in violations)


class TestGetattrSetattrDelattr:
    """Tests for dynamic attribute access via getattr/setattr."""

    def test_getattr_with_dangerous_string(self):
        validator = DangerousPatternValidator()
        code = "getattr(obj, '__class__')"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("__class__" in v.pattern for v in violations)

    def test_getattr_with_globals_string(self):
        validator = DangerousPatternValidator()
        code = "getattr(func, '__globals__')"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("__globals__" in v.pattern for v in violations)

    def test_getattr_dynamic(self):
        validator = DangerousPatternValidator()
        code = "attr = input()\ngetattr(obj, attr)"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("dynamic" in v.pattern.lower() for v in violations)

    def test_getattr_safe_string_passes(self):
        validator = DangerousPatternValidator()
        code = "getattr(obj, 'safe_attr')"
        is_valid, violations = validator.validate(code)
        assert is_valid is True

    def test_setattr_call(self):
        validator = DangerousPatternValidator()
        code = "setattr(obj, 'x', 1)"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("setattr" in v.pattern for v in violations)

    def test_delattr_call(self):
        validator = DangerousPatternValidator()
        code = "delattr(obj, 'x')"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("delattr" in v.pattern for v in violations)

    def test_hasattr_call(self):
        validator = DangerousPatternValidator()
        code = "hasattr(obj, 'x')"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("hasattr" in v.pattern for v in violations)


class TestTypeManipulation:
    """Tests for type manipulation attacks."""

    def test_type_new(self):
        validator = DangerousPatternValidator()
        code = "type.__new__(type, 'X', (), {})"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("type.__new__" in v.pattern for v in violations)

    def test_object_setattr(self):
        validator = DangerousPatternValidator()
        code = "object.__setattr__(obj, 'x', 1)"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("object.__setattr__" in v.pattern for v in violations)

    def test_object_getattribute(self):
        validator = DangerousPatternValidator()
        code = "object.__getattribute__(obj, 'x')"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("object.__getattribute__" in v.pattern for v in violations)

    def test_object_delattr(self):
        validator = DangerousPatternValidator()
        code = "object.__delattr__(obj, 'x')"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("object.__delattr__" in v.pattern for v in violations)


class TestSubscriptAccess:
    """Tests for string-based subscript access to dangerous attributes."""

    def test_subscript_globals(self):
        validator = DangerousPatternValidator()
        code = "x = obj['__globals__']"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("__globals__" in v.pattern for v in violations)

    def test_subscript_class(self):
        validator = DangerousPatternValidator()
        code = "x = obj['__class__']"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("__class__" in v.pattern for v in violations)

    def test_subscript_builtins(self):
        validator = DangerousPatternValidator()
        code = "x = d['__builtins__']"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("__builtins__" in v.pattern for v in violations)

    def test_safe_subscript(self):
        validator = DangerousPatternValidator()
        code = "x = d['key']"
        is_valid, violations = validator.validate(code)
        assert is_valid is True


class TestImportFunction:
    """Tests for __import__ function calls."""

    def test_import_function(self):
        validator = DangerousPatternValidator()
        code = "__import__('os')"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("__import__" in v.pattern for v in violations)

    def test_import_function_with_variable(self):
        validator = DangerousPatternValidator()
        code = "mod = 'os'\n__import__(mod)"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("__import__" in v.pattern for v in violations)


class TestOtherDangerousCalls:
    """Tests for other dangerous function calls."""

    def test_breakpoint(self):
        validator = DangerousPatternValidator()
        code = "breakpoint()"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("breakpoint" in v.pattern for v in violations)

    def test_open_call(self):
        validator = DangerousPatternValidator()
        code = "f = open('file.txt')"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("open" in v.pattern for v in violations)

    def test_input_call(self):
        validator = DangerousPatternValidator()
        code = "x = input('prompt')"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("input" in v.pattern for v in violations)


class TestOtherDangerousModules:
    """Tests for other dangerous module imports."""

    def test_shelve_import(self):
        validator = DangerousPatternValidator()
        code = "import shelve"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("shelve" in v.pattern for v in violations)

    def test_dill_import(self):
        validator = DangerousPatternValidator()
        code = "import dill"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("dill" in v.pattern for v in violations)

    def test_jsonpickle_import(self):
        validator = DangerousPatternValidator()
        code = "import jsonpickle"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("jsonpickle" in v.pattern for v in violations)


class TestLineNumbers:
    """Tests for accurate line number tracking."""

    def test_line_number_tracking(self):
        validator = DangerousPatternValidator()
        code = "x = 1\ny = 2\neval('bad')\nz = 4"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert len(violations) >= 1
        assert violations[0].line == 3

    def test_line_number_multiline(self):
        validator = DangerousPatternValidator()
        code = """
def foo():
    pass

eval('bad')
"""
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert violations[0].line == 5


class TestMultipleViolations:
    """Tests for code with multiple violations."""

    def test_multiple_violations_detected(self):
        validator = DangerousPatternValidator()
        code = """
import pickle
eval('bad')
obj.__class__
"""
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert len(violations) >= 3


class TestValidateCodeForDangerousPatterns:
    """Tests for the convenience function."""

    def test_returns_valid_for_safe_code(self):
        is_valid, error = validate_code_for_dangerous_patterns("x = 1 + 2")
        assert is_valid is True
        assert error is None

    def test_returns_error_dict_for_dangerous_code(self):
        is_valid, error = validate_code_for_dangerous_patterns("eval('bad')")
        assert is_valid is False
        assert error is not None
        assert error["status"] == "error"
        assert "line" in error
        assert "pattern" in error

    def test_error_format_matches_spec(self):
        is_valid, error = validate_code_for_dangerous_patterns("eval('bad')")
        assert is_valid is False
        assert error["status"] == "error"
        assert "eval" in error["error"]
        assert error["line"] == 1
        assert error["pattern"] == "eval"


class TestSeverityLevels:
    """Tests for severity level assignment."""

    def test_critical_severity_for_eval(self):
        validator = DangerousPatternValidator()
        code = "eval('x')"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert violations[0].severity == Severity.CRITICAL

    def test_critical_severity_for_pickle(self):
        validator = DangerousPatternValidator()
        code = "import pickle"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert violations[0].severity == Severity.CRITICAL

    def test_high_severity_for_open(self):
        validator = DangerousPatternValidator()
        code = "open('file')"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert violations[0].severity == Severity.HIGH

    def test_medium_severity_for_hasattr(self):
        validator = DangerousPatternValidator()
        code = "hasattr(obj, 'x')"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert violations[0].severity == Severity.MEDIUM


class TestEdgeCases:
    """Tests for edge cases and potential bypasses."""

    def test_nested_attribute_access(self):
        validator = DangerousPatternValidator()
        code = "x = a.b.__class__"
        is_valid, violations = validator.validate(code)
        assert is_valid is False

    def test_chained_calls(self):
        validator = DangerousPatternValidator()
        code = "eval(exec('x'))"
        is_valid, violations = validator.validate(code)
        assert is_valid is False
        assert any("eval" in v.pattern for v in violations)

    def test_in_function(self):
        validator = DangerousPatternValidator()
        code = """
def foo():
    eval('bad')
"""
        is_valid, violations = validator.validate(code)
        assert is_valid is False

    def test_in_class_method(self):
        validator = DangerousPatternValidator()
        code = """
class Foo:
    def bar(self):
        eval('bad')
"""
        is_valid, violations = validator.validate(code)
        assert is_valid is False

    def test_safe_method_named_eval(self):
        validator = DangerousPatternValidator()
        code = "obj.eval('safe')"
        is_valid, violations = validator.validate(code)
        assert is_valid is True

    def test_safe_method_named_exec(self):
        validator = DangerousPatternValidator()
        code = "obj.exec('safe')"
        is_valid, violations = validator.validate(code)
        assert is_valid is True

    def test_lambda_with_dangerous_code(self):
        validator = DangerousPatternValidator()
        code = "f = lambda: eval('x')"
        is_valid, violations = validator.validate(code)
        assert is_valid is False


class TestIntegrationWithSandbox:
    """Tests that would be caught by integration with SandboxExecutor."""

    def test_combined_importlib_and_os(self):
        validator = DangerousPatternValidator()
        code = "import importlib\nimportlib.import_module('os').system('ls')"
        is_valid, violations = validator.validate(code)
        assert is_valid is False

    def test_pickle_exploit_pattern(self):
        validator = DangerousPatternValidator()
        code = """
import pickle
class Exploit:
    def __reduce__(self):
        return (eval, ('print("owned")',))
pickle.dumps(Exploit())
"""
        is_valid, violations = validator.validate(code)
        assert is_valid is False

    def test_sandbox_escape_via_subclasses(self):
        validator = DangerousPatternValidator()
        code = "object.__subclasses__()"
        is_valid, violations = validator.validate(code)
        assert is_valid is False


class TestConstantsExports:
    """Tests for exported constants."""

    def test_dangerous_calls_dict(self):
        assert "eval" in DANGEROUS_CALLS
        assert "exec" in DANGEROUS_CALLS
        assert "os.system" in DANGEROUS_CALLS
        assert "subprocess.run" in DANGEROUS_CALLS
        assert "pickle.loads" in DANGEROUS_CALLS

    def test_dangerous_attributes_set(self):
        assert "__class__" in DANGEROUS_ATTRIBUTES
        assert "__globals__" in DANGEROUS_ATTRIBUTES
        assert "__builtins__" in DANGEROUS_ATTRIBUTES

    def test_dangerous_modules_set(self):
        assert "pickle" in DANGEROUS_MODULES
        assert "marshal" in DANGEROUS_MODULES
        assert "importlib" in DANGEROUS_MODULES
