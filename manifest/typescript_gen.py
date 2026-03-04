"""Generate TypeScript definitions from manifest for LLM type awareness."""

from typing import Any, Dict, List


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


def generate_server_interface(server_name: str, tools: List[Dict[str, Any]]) -> str:
    """Generate TypeScript interface for a server.

    Args:
        server_name: Name of the server
        tools: List of tool dictionaries with inputSchema

    Returns:
        TypeScript interface string
    """
    interface_name = "".join(word.capitalize() for word in server_name.split("_"))
    lines = [f"interface {interface_name}API {{"]

    for tool in tools:
        tool_name = tool.get("name", "")
        description = tool.get("description", "")
        input_schema = tool.get("inputSchema", {})

        # Extract parameters
        properties = input_schema.get("properties", {})
        required = set(input_schema.get("required", []))

        # Build parameter list
        params = []
        for prop_name, prop_schema in properties.items():
            prop_type = json_schema_to_ts(prop_schema, 1)
            optional = "?" if prop_name not in required else ""
            params.append(f"{prop_name}{optional}: {prop_type}")

        params_str = ", ".join(params) if params else ""

        # Add method with JSDoc
        if description:
            lines.append(f"  /** {description} */")
        lines.append(f"  {tool_name}({params_str}): Promise<any>;")
        lines.append("")

    lines.append("}")
    return "\n".join(lines)


def generate_typescript_definitions(manifest: Dict[str, Any]) -> str:
    """Generate complete TypeScript definitions from manifest.

    Args:
        manifest: Manifest dictionary with servers and tools

    Returns:
        TypeScript definitions string
    """
    lines = [
        "// MCProxy v2 API Type Definitions",
        "// Auto-generated from manifest",
        "",
        "// Session stash for caching",
        "interface SessionStash {",
        "  put(key: string, value: any, ttl?: number): void;",
        "  get(key: string): any;",
        "  delete(key: string): void;",
        "  clear(): void;",
        "}",
        "",
        "// Parallel execution helper",
        "interface ForgeParallel {",
        "  parallel<T>(calls: (() => Promise<T>)[]): Promise<{ results: T[] }>;",
        "}",
        "",
    ]

    # Generate server interfaces
    servers = manifest.get("servers", {})
    tools_by_server = manifest.get("tools_by_server", {})

    server_names = []
    for server_name in servers.keys():
        tools = tools_by_server.get(server_name, [])
        if tools:
            interface_def = generate_server_interface(server_name, tools)
            lines.append(interface_def)
            lines.append("")
            server_names.append(server_name)

    # Generate main API interface
    lines.append("interface MCProxyAPI {")
    lines.append("  /** Get full manifest of available tools */")
    lines.append("  manifest(): any;")
    lines.append("")
    lines.append("  /** Call tool directly */")
    lines.append(
        "  call_tool(server: string, tool: string, args: Record<string, any>): Promise<any>;"
    )
    lines.append("")

    # Add server methods
    for server_name in server_names:
        interface_name = "".join(word.capitalize() for word in server_name.split("_"))
        lines.append(f"  /** Access {server_name} tools */")
        lines.append(f'  server(name: "{server_name}"): {interface_name}API;')
        lines.append("")

    lines.append("}")
    lines.append("")
    lines.append("// Sandbox globals")
    lines.append("declare const api: MCProxyAPI;")
    lines.append("declare const stash: SessionStash;")
    lines.append("declare const forge: ForgeParallel;")

    return "\n".join(lines)


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
        "⚠️ CRITICAL: Use only the servers listed below!",
        "Server names vary by environment. Do NOT guess names like 'playwright' or 'pure_md'.",
        "The servers available in THIS environment are listed under 'Available servers'.",
        "",
        "Usage: api.server('name').tool(args)",
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

    # Fallback if no servers with tools
    if example_count == 0:
        lines.append('  api.server("server_name").tool_name(param: type): Promise<any>')

    lines.extend(
        [
            "",
            "Note: Hyphenated tool names use underscores (auto-converted):",
            "  get-coins → get_coins()",
            "  get-coin-by-id → get_coin_by_id()",
            "",
            "For read-modify-write: mcproxy_sequence(read, transform, write)",
            "  'read_result' in transform is extracted content",
            "  'result' must be set with write args",
            "",
            "For parameter details: mcproxy_search(query='tool_name', max_depth=3)",
            "",
            "Note: Each execute call is isolated (fresh subprocess).",
            "Use stash for cross-call state:",
            "  stash.put(key, value, ttl?) - Save data",
            "  stash.get(key) - Retrieve data",
            "",
            "Utilities:",
            "  api.manifest() - Get full tool details",
            "  await forge.parallel([...]) - Run calls concurrently",
        ]
    )

    return "\n".join(lines)
