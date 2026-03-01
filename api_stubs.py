"""Typed stub generation for MCProxy v2.0.

Generates Python .pyi stub files from MCP tool schemas for IDE support
and type checking.
"""

import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from logging_config import get_logger

logger = get_logger(__name__)

TYPE_MAPPING: Dict[str, str] = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "array": "List[Any]",
    "object": "Dict[str, Any]",
}


class StubGenerator:
    """Generate typed Python stub files from MCP tool schemas.

    Creates .pyi files with proxy classes for each MCP server, enabling
    IDE autocompletion and type checking for tool calls.
    """

    def __init__(
        self,
        manifest: Dict[str, Any],
        output_dir: str = "./generated/stubs",
    ) -> None:
        """Initialize the stub generator.

        Args:
            manifest: Configuration manifest containing servers and namespaces
            output_dir: Directory to write generated stub files
        """
        self.manifest = manifest
        self.output_dir = Path(output_dir)
        self._cache: Dict[str, str] = {}

        stub_config = manifest.get("typed_stub_generation", {})
        self.enabled = stub_config.get("enabled", True)
        self.config_output_dir = stub_config.get("output_dir")
        self.include_deprecated = stub_config.get("include_deprecated", False)

        if self.config_output_dir:
            self.output_dir = Path(self.config_output_dir)

    def generate_all(self) -> List[str]:
        """Generate stubs for all servers in the manifest.

        Returns:
            List of paths to generated stub files
        """
        if not self.enabled:
            logger.info("Stub generation disabled in config")
            return []

        self.output_dir.mkdir(parents=True, exist_ok=True)

        generated_files: List[str] = []
        servers = self.manifest.get("servers", [])

        for server in servers:
            server_name = server.get("name", "")
            if not server_name:
                continue

            tools = self._get_server_tools(server)
            if not tools:
                continue

            try:
                file_path = self.generate_server(server_name, tools)
                generated_files.append(file_path)
            except Exception as e:
                logger.error(f"Failed to generate stub for {server_name}: {e}")

        init_path = self._generate_init_file(generated_files)
        if init_path:
            generated_files.append(init_path)

        namespaces = self.manifest.get("namespaces", {})
        for ns_name, ns_config in namespaces.items():
            try:
                ns_servers = self._resolve_namespace_servers(ns_name, ns_config)
                if ns_servers:
                    ns_path = self.generate_namespace_stub(ns_name, ns_servers)
                    generated_files.append(ns_path)
            except Exception as e:
                logger.error(f"Failed to generate namespace stub for {ns_name}: {e}")

        logger.info(f"Generated {len(generated_files)} stub files")
        return generated_files

    def generate_server(self, server_name: str, tools: List[Dict[str, Any]]) -> str:
        """Generate a stub file for a single server.

        Args:
            server_name: Name of the MCP server
            tools: List of tool definitions from the server

        Returns:
            Path to the generated stub file
        """
        cache_key = f"server:{server_name}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        categorized = self._categorize_tools(tools)

        lines: List[str] = [
            f'"""Proxy stub for {server_name} MCP server."""',
            "",
            "from typing import Any, Dict, List, Optional",
            "",
        ]

        class_name = self._to_class_name(server_name)
        lines.append(f"class {class_name}Proxy:")
        lines.append(f'    """Proxy for {server_name} MCP server tools."""')
        lines.append("")

        root_methods: List[str] = []
        category_classes: Dict[str, List[str]] = {}

        for category, category_tools in categorized.items():
            if category == "_root":
                for tool in category_tools:
                    method_lines = self._generate_method(tool)
                    root_methods.extend(method_lines)
            else:
                category_class_name = self._sanitize_identifier(category)
                category_methods: List[str] = []
                for tool in category_tools:
                    method_lines = self._generate_method(tool, indent=2)
                    category_methods.extend(method_lines)

                category_classes[category_class_name] = category_methods

        for cat_name, cat_methods in sorted(category_classes.items()):
            lines.append(f"    class {cat_name}:")
            lines.append(f'        """Tools in the {cat_name} category."""')
            lines.append("")
            for method_line in cat_methods:
                lines.append(method_line)
            lines.append("")

        for method_line in root_methods:
            lines.append(method_line)

        if not root_methods and not category_classes:
            lines.append("    pass")

        lines.append("")

        content = "\n".join(lines)
        file_path = self.output_dir / f"{self._sanitize_filename(server_name)}.pyi"

        with open(file_path, "w") as f:
            f.write(content)

        self._cache[cache_key] = str(file_path)
        logger.debug(f"Generated stub for {server_name} at {file_path}")
        return str(file_path)

    def generate_namespace_stub(self, namespace: str, servers: List[str]) -> str:
        """Generate a combined stub for a namespace.

        Args:
            namespace: Name of the namespace
            servers: List of server names in the namespace

        Returns:
            Path to the generated stub file
        """
        cache_key = f"namespace:{namespace}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        lines: List[str] = [
            f'"""Combined proxy stub for {namespace} namespace."""',
            "",
            "from typing import Any, Dict, List, Optional",
            "",
        ]

        ns_class_name = self._to_class_name(namespace)
        lines.append(f"class {ns_class_name}Namespace:")
        lines.append(f'    """Combined proxy for {namespace} namespace."""')
        lines.append("")

        for server_name in sorted(servers):
            server_class = f"{self._to_class_name(server_name)}Proxy"
            attr_name = self._sanitize_identifier(server_name)
            lines.append(f"    {attr_name}: {server_class}")
            lines.append(f'        """Access to {server_name} tools."""')
            lines.append("")

        lines.append("")

        content = "\n".join(lines)
        file_path = self.output_dir / f"{self._sanitize_filename(namespace)}_ns.pyi"

        with open(file_path, "w") as f:
            f.write(content)

        self._cache[cache_key] = str(file_path)
        logger.debug(f"Generated namespace stub for {namespace} at {file_path}")
        return str(file_path)

    def _get_server_tools(self, server: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract tools from server configuration.

        Args:
            server: Server configuration dict

        Returns:
            List of tool definitions
        """
        tools = server.get("tools", [])

        if not self.include_deprecated:
            tools = [t for t in tools if not t.get("deprecated", False)]

        return tools

    def _categorize_tools(
        self, tools: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Group tools by category based on naming convention.

        Tools like 'repos_list' are grouped into 'repos' category.
        Tools without underscore prefix go to '_root' category.

        Args:
            tools: List of tool definitions

        Returns:
            Dict mapping category name to list of tools
        """
        categorized: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for tool in tools:
            name = tool.get("name", "")
            parts = name.split("_", 1)

            if len(parts) > 1:
                category = parts[0]
                tool_with_short_name = tool.copy()
                tool_with_short_name["_short_name"] = parts[1]
                categorized[category].append(tool_with_short_name)
            else:
                categorized["_root"].append(tool)

        return dict(categorized)

    def _generate_method(self, tool: Dict[str, Any], indent: int = 1) -> List[str]:
        """Generate method signature lines for a tool.

        Args:
            tool: Tool definition dict
            indent: Indentation level (spaces = indent * 4)

        Returns:
            List of formatted method signature lines
        """
        lines: List[str] = []
        prefix = "    " * indent

        name = tool.get("_short_name", tool.get("name", "unknown"))
        description = tool.get("description", "")
        input_schema = tool.get("inputSchema", {})

        safe_name = self._sanitize_identifier(name)

        params = self._generate_params(input_schema)
        return_type = self._get_return_type(input_schema)

        if description:
            doc_lines = self._wrap_docstring(description, indent + 1)
            lines.append(f"{prefix}@staticmethod")
            lines.append(f"{prefix}async def {safe_name}({params}) -> {return_type}:")
            for doc_line in doc_lines:
                lines.append(doc_line)
            lines.append(f"{prefix}    ...")
        else:
            lines.append(f"{prefix}@staticmethod")
            lines.append(f"{prefix}async def {safe_name}({params}) -> {return_type}:")
            lines.append(f"{prefix}    ...")

        lines.append("")
        return lines

    def _generate_params(self, input_schema: Dict[str, Any]) -> str:
        """Generate parameter string from input schema.

        Args:
            input_schema: JSON Schema for tool input

        Returns:
            Comma-separated parameter string with type hints
        """
        if not input_schema:
            return ""

        properties = input_schema.get("properties", {})
        required = set(input_schema.get("required", []))

        if not properties:
            return ""

        params: List[str] = []

        for prop_name, prop_schema in properties.items():
            safe_name = self._sanitize_identifier(prop_name)
            param_type = self._map_type(prop_schema)
            has_default = "default" in prop_schema

            if prop_name in required and not has_default:
                params.append(f"{safe_name}: {param_type}")
            elif has_default:
                default_value = self._format_default(prop_schema["default"])
                params.append(f"{safe_name}: {param_type} = {default_value}")
            else:
                params.append(f"{safe_name}: Optional[{param_type}] = None")

        return ", ".join(params)

    def _map_type(self, schema: Dict[str, Any]) -> str:
        """Map JSON Schema type to Python type hint.

        Args:
            schema: JSON Schema for a property

        Returns:
            Python type hint string
        """
        json_type = schema.get("type", "any")

        if json_type == "array":
            items = schema.get("items", {})
            if items:
                item_type = self._map_type(items)
                return f"List[{item_type}]"
            return "List[Any]"

        if json_type == "object":
            return "Dict[str, Any]"

        if isinstance(json_type, list):
            non_null = [t for t in json_type if t != "null"]
            if len(non_null) == 1:
                base_type = TYPE_MAPPING.get(non_null[0], "Any")
                return f"Optional[{base_type}]"
            return "Any"

        return TYPE_MAPPING.get(json_type, "Any")

    def _get_return_type(self, input_schema: Dict[str, Any]) -> str:
        """Determine return type for a tool method.

        Args:
            input_schema: Input schema (unused, but kept for API consistency)

        Returns:
            Return type string
        """
        return "Dict[str, Any]"

    def _format_default(self, value: Any) -> str:
        """Format a default value for Python code.

        Args:
            value: Default value

        Returns:
            Formatted string representation
        """
        if value is None:
            return "None"
        if isinstance(value, bool):
            return "True" if value else "False"
        if isinstance(value, str):
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, list):
            return "[]"
        if isinstance(value, dict):
            return "{}"
        return "None"

    def _to_class_name(self, name: str) -> str:
        """Convert server/namespace name to PascalCase class name.

        Args:
            name: Server or namespace name

        Returns:
            PascalCase class name
        """
        parts = name.replace("-", "_").replace(".", "_").split("_")
        return "".join(part.capitalize() for part in parts if part)

    def _sanitize_identifier(self, name: str) -> str:
        """Convert name to valid Python identifier.

        Args:
            name: Original name

        Returns:
            Valid Python identifier
        """
        sanitized = ""
        for char in name:
            if char.isalnum() or char == "_":
                sanitized += char
            else:
                sanitized += "_"

        if sanitized and sanitized[0].isdigit():
            sanitized = "_" + sanitized

        return sanitized or "_"

    def _sanitize_filename(self, name: str) -> str:
        """Convert name to valid filename.

        Args:
            name: Original name

        Returns:
            Valid filename
        """
        sanitized = ""
        for char in name:
            if char.isalnum() or char in "_-":
                sanitized += char
            else:
                sanitized += "_"

        return sanitized.lower().rstrip("_-") or "unnamed"

    def _wrap_docstring(self, text: str, indent: int = 1) -> List[str]:
        """Wrap docstring text with proper formatting.

        Args:
            text: Docstring text
            indent: Indentation level

        Returns:
            List of formatted docstring lines
        """
        prefix = "    " * indent
        max_width = 80 - len(prefix)

        words = text.split()
        lines: List[str] = [f'{prefix}"""']

        current_line = ""
        for word in words:
            if current_line and len(current_line) + len(word) + 1 > max_width:
                lines.append(f"{prefix}{current_line}")
                current_line = word
            else:
                current_line = f"{current_line} {word}".strip()

        if current_line:
            lines.append(f"{prefix}{current_line}")

        lines.append(f'{prefix}"""')
        return lines

    def _generate_init_file(self, stub_files: List[str]) -> Optional[str]:
        """Generate __init__.pyi that exports all proxy classes.

        Args:
            stub_files: List of generated stub file paths

        Returns:
            Path to __init__.pyi or None if no files
        """
        if not stub_files:
            return None

        lines: List[str] = [
            '"""Generated stubs for MCProxy servers."""',
            "",
        ]

        exports: Set[str] = set()

        for file_path in stub_files:
            file_name = Path(file_path).stem
            if file_name.endswith("_ns"):
                ns_name = file_name[:-3]
                exports.add(f"{self._to_class_name(ns_name)}Namespace")
            else:
                exports.add(f"{self._to_class_name(file_name)}Proxy")

        for export in sorted(exports):
            lines.append(f"from .{file_name} import {export}")

        lines.append("")
        lines.append("__all__ = [")
        for export in sorted(exports):
            lines.append(f'    "{export}",')
        lines.append("]")
        lines.append("")

        init_path = self.output_dir / "__init__.pyi"
        content = "\n".join(lines)

        with open(init_path, "w") as f:
            f.write(content)

        return str(init_path)

    def _resolve_namespace_servers(self, ns_name: str, ns_config: Any) -> List[str]:
        """Resolve list of server names in a namespace.

        Args:
            ns_name: Namespace name
            ns_config: Namespace configuration

        Returns:
            List of server names in the namespace
        """
        if isinstance(ns_config, list):
            return ns_config
        elif isinstance(ns_config, dict):
            servers = ns_config.get("servers", [])
            if isinstance(servers, list):
                return servers
        return []
