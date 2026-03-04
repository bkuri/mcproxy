"""Generate TypeScript definitions from manifest for LLM type awareness."""

from typing import Any, Dict


def json_schema_to_ts(schema: Dict[str, Any], indent: int = 0) -> str:
    """Convert JSON Schema to TypeScript type string.

    Args:
        schema: JSON Schema object
        indent: Indentation level

    Returns:
        TypeScript type string
    """
    if not schema:
        return "any"

    schema_type = schema.get("type", "any")

    if schema_type == "string":
        if "enum" in schema:
            return " | ".join(f'"{v}"' for v in schema["enum"])
        return "string"
    elif schema_type == "number" or schema_type == "integer":
        return "number"
    elif schema_type == "boolean":
        return "boolean"
    elif schema_type == "array":
        items = schema.get("items", {})
        item_type = json_schema_to_ts(items, indent)
        return f"{item_type}[]"
    elif schema_type == "object":
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))

        if not properties:
            return "Record<string, any>"

        lines = []
        indent_str = "  " * indent
        for prop_name, prop_schema in properties.items():
            prop_type = json_schema_to_ts(prop_schema, indent + 1)
            optional = "?" if prop_name not in required else ""
            lines.append(f"{indent_str}  {prop_name}{optional}: {prop_type};")

        return "{\n" + "\n".join(lines) + f"\n{indent_str}}}"

    return "any"


def generate_compact_instructions(
    manifest: Dict[str, Any], detailed: bool = False
) -> str:
    """Generate compact instructions with TypeScript-style type hints.

    This is a middle ground: TypeScript syntax but more compact than full definitions.

    Args:
        manifest: Manifest dictionary
        detailed: If True, include parameter signatures for all tools

    Returns:
        Compact instruction string
    """
    tools_by_server = manifest.get("tools_by_server", {})
    servers = manifest.get("servers", {})

    lines = [
        "MCProxy v2 Code Mode API",
        "",
        "Tool selection:",
        "  execute  - Run Python code accessing multiple servers or with logic",
        "  sequence - Single read / read-modify-write (no code logic needed)",
        "  search   - Discover tool names when unknown (skip if server name is known)",
        "",
        "Usage: api.server('server_name').tool_name(arg=value)",
        "Example: api.server('wikipedia').search(query='python')",
        "Discovery: api.manifest() returns all servers with full tool schemas",
        "",
        "Available servers and tools:",
    ]

    # If tools_by_server is empty, fall back to showing server names
    if tools_by_server:
        for server_name, tools in sorted(tools_by_server.items()):
            if detailed:
                lines.append(f"  {server_name}:")
                # Show all tools with parameter signatures
                if tools:
                    if isinstance(tools[0], dict):
                        for tool in tools:
                            tool_name = tool.get("name", "")
                            input_schema = tool.get("inputSchema", {})

                            properties = input_schema.get("properties", {})
                            required = set(input_schema.get("required", []))

                            params = []
                            for prop_name, prop_schema in properties.items():
                                prop_type = json_schema_to_ts(prop_schema, 0)
                                optional = "?" if prop_name not in required else ""
                                # Simplify complex types for display
                                if "|" in prop_type and len(prop_type) > 30:
                                    prop_type = (
                                        prop_type.split("|")[0].strip().strip('"')
                                    )
                                params.append(f"{prop_name}{optional}: {prop_type}")

                            params_str = ", ".join(params) if params else ""
                            lines.append(f"    {tool_name}({params_str})")
                    else:
                        for tool in tools:
                            lines.append(f"    {tool}")
            else:
                # Compact mode: just tool names
                if tools and isinstance(tools[0], dict):
                    tool_names = [t.get("name", "") for t in tools]
                else:
                    tool_names = [str(t) for t in tools]
                lines.append(f"  {server_name}: {', '.join(tool_names)}")
    else:
        # Fallback: show server names with tool counts
        for server_name, server_info in sorted(servers.items()):
            tool_count = server_info.get("tool_count", 0)
            lines.append(f"  {server_name}: {tool_count} tools")

    lines.extend(
        [
            "",
            "Cross-call state (execute runs in isolated subprocess):",
            "  stash.put(key, value, ttl?)  - Save between calls",
            "  stash.get(key)               - Retrieve saved data",
        ]
    )

    # Generate dynamic examples based on available servers
    lines.append("")
    lines.append("Examples:")

    # Show 1-2 examples from available servers
    example_count = 0
    for server_name, tools in sorted(tools_by_server.items()):
        if example_count >= 2:
            break
        if tools and isinstance(tools[0], dict):
            first_tool = tools[0]
            tool_name = first_tool.get("name", "tool")
            input_schema = first_tool.get("inputSchema", {})
            properties = input_schema.get("properties", {})
            required = set(input_schema.get("required", []))

            # Build parameter hint
            params = []
            for prop_name, prop_schema in list(properties.items())[
                :2
            ]:  # Show first 2 params
                prop_type = json_schema_to_ts(prop_schema, 0)
                optional = "?" if prop_name not in required else ""
                params.append(f"{prop_name}{optional}: {prop_type}")

            params_str = ", ".join(params) if params else ""
            lines.append(
                f'  api.server("{server_name}").{tool_name}({params_str}): Promise<any>'
            )
            example_count += 1

    lines.extend(
        [
            "",
            "Utilities:",
            "  forge.parallel([...])    - Run calls concurrently",
            "",
            "Note: Hyphenated tool names use underscores: get-coins → get_coins()",
        ]
    )

    return "\n".join(lines)
