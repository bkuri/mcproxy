"""Lifecycle management for MCProxy v2.0 components."""

from typing import Any, Callable, Dict, List, Optional

from manifest import CapabilityRegistry, EventHookManager
from sandbox import SandboxExecutor, AccessControlConfig
from logging_config import get_logger

logger = get_logger(__name__)

server_manager: Optional[Any] = None
capability_registry: Optional[CapabilityRegistry] = None
event_hook_manager: Optional[EventHookManager] = None
sandbox_executor: Optional[SandboxExecutor] = None
session_manager: Optional[Any] = None
_tool_executor: Optional[Callable] = None


def set_server_manager(manager: Any) -> None:
    """Set the global server manager reference (for backward compatibility)."""
    global server_manager
    server_manager = manager


def init_v2_components(
    config: Optional[Dict] = None,
    tool_executor: Optional[Callable] = None,
    servers_tools: Optional[Dict[str, List]] = None,
) -> None:
    """Initialize v2.0 components: CapabilityRegistry and SandboxExecutor.

    Args:
        config: Optional configuration dict for components
        tool_executor: Callable to execute tools (server_name, tool_name, args) -> result
        servers_tools: Dict mapping server name to list of tools (from server_manager.get_all_tools())
    """
    global capability_registry, sandbox_executor, event_hook_manager, _tool_executor

    config = config or {}
    _tool_executor = tool_executor

    capability_registry = CapabilityRegistry()

    if config and "namespaces" in config:
        capability_registry._namespaces = config["namespaces"]

    if config and "groups" in config:
        capability_registry._groups = config["groups"]

    if servers_tools:
        logger.info(f"[V2_INIT] Building manifest from {len(servers_tools)} servers")
        capability_registry.build(servers_tools)
    else:
        logger.warning("[V2_INIT] No servers_tools provided, manifest will be empty")

    event_hook_manager = EventHookManager(capability_registry)

    if tool_executor and capability_registry:
        sandbox_manifest = AccessControlConfig(
            servers=capability_registry._manifest.get("servers", {}),
            namespaces=capability_registry._namespaces,
            groups=capability_registry._groups,
        )
        sandbox_executor = SandboxExecutor(
            manifest=sandbox_manifest,
            tool_executor=tool_executor,
            uv_path=config.get("sandbox", {}).get("uv_path", "uv"),
            default_timeout_secs=config.get("sandbox", {}).get("timeout_secs", 30),
            max_concurrency=config.get("max_parallel", 5),
        )

    _log_manifest_stats()


def refresh_manifest(servers_tools: Dict[str, List]) -> None:
    """Refresh the manifest when servers finish loading tools.

    Args:
        servers_tools: Dict mapping server name to list of tools
    """
    global capability_registry, sandbox_executor, _tool_executor

    if capability_registry is None:
        logger.warning("[REFRESH_MANIFEST] CapabilityRegistry not initialized")
        return

    logger.info(
        f"[REFRESH_MANIFEST] Rebuilding manifest from {len(servers_tools)} servers"
    )
    capability_registry.build(servers_tools)

    if sandbox_executor and capability_registry:
        sandbox_executor._manifest = AccessControlConfig(
            servers=capability_registry._manifest.get("servers", {}),
            namespaces=capability_registry._namespaces,
            groups=capability_registry._groups,
        )

    _log_manifest_stats()


def _log_manifest_stats() -> None:
    """Log current manifest statistics."""
    tool_count = (
        capability_registry._manifest.get("tool_count", 0) if capability_registry else 0
    )
    server_count = (
        len(capability_registry._manifest.get("servers", {}))
        if capability_registry
        else 0
    )
    logger.info(f"[MANIFEST_STATS] {server_count} servers, {tool_count} tools")


def on_config_change(new_config: Dict) -> None:
    """Handle config change event - reload manifests and sandbox config.

    Args:
        new_config: New configuration dict
    """
    logger.info("[CONFIG_CHANGE] Reloading v2.0 components")
    if event_hook_manager:
        event_hook_manager.trigger("config_change", {"config": new_config})


def on_server_health(server_name: str, healthy: bool) -> None:
    """Handle server health change event.

    Args:
        server_name: Name of the affected server
        healthy: Whether the server is now healthy
    """
    status = "healthy" if healthy else "unhealthy"
    logger.info(f"[SERVER_HEALTH] {server_name} is now {status}")
    if event_hook_manager:
        event_hook_manager.trigger(
            "server_health", {"server": server_name, "healthy": healthy}
        )


def get_capability_registry() -> Optional[CapabilityRegistry]:
    """Get the global capability registry."""
    return capability_registry


def get_sandbox_executor() -> Optional[SandboxExecutor]:
    """Get the global sandbox executor."""
    return sandbox_executor


def get_session_manager() -> Optional[Any]:
    """Get the global session manager."""
    return session_manager


def get_tool_executor() -> Optional[Callable]:
    """Get the global tool executor."""
    return _tool_executor
