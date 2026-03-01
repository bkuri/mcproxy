"""Manifest system v2.0 for MCProxy.

Provides capability registry, manifest queries, event hooks, and namespace inheritance.
"""

import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from logging_config import get_logger

logger = get_logger(__name__)

CACHE_DIR = Path("./cache")
CACHE_FILE = CACHE_DIR / "manifest.json"
CACHE_TTL_SECONDS = 3600


class ManifestError(Exception):
    """Error in manifest operations."""

    pass


class NamespaceInheritanceError(ManifestError):
    """Error in namespace inheritance resolution."""

    pass


def validate_group(
    name: str, group_def: dict, namespaces: dict
) -> tuple[bool, list[str]]:
    """Validate a group definition.

    Args:
        name: Group name
        group_def: Group definition with 'namespaces' key
        namespaces: All namespace definitions

    Returns:
        (is_valid, warnings)
    """
    warnings: list[str] = []
    is_valid = True

    ns_refs = group_def.get("namespaces", [])
    if not ns_refs:
        warnings.append(f"Group '{name}' has no namespaces defined")
        return False, warnings

    for ns_ref in ns_refs:
        explicit_isolated = ns_ref.startswith("!")
        actual_name = ns_ref[1:] if explicit_isolated else ns_ref

        if actual_name not in namespaces:
            warnings.append(
                f"Group '{name}' references unknown namespace '{actual_name}'"
            )
            is_valid = False
            continue

        ns_def = namespaces.get(actual_name, {})
        is_isolated = (
            ns_def.get("isolated", False) if isinstance(ns_def, dict) else False
        )

        if is_isolated and not explicit_isolated:
            warnings.append(
                f"Group '{name}' references isolated namespace '{actual_name}' "
                f"without '!' prefix - this is not allowed"
            )
            is_valid = False
        elif is_isolated and explicit_isolated:
            warnings.append(
                f"Group '{name}' explicitly includes isolated namespace '{actual_name}'"
            )

    return is_valid, warnings


class CapabilityRegistry:
    """Registry for building and managing capability manifests.

    Handles server tools aggregation, namespace inheritance, and manifest caching.
    """

    def __init__(self) -> None:
        """Initialize the capability registry."""
        self._manifest: Dict[str, Any] = {}
        self._namespaces: Dict[str, Any] = {}
        self._groups: Dict[str, Any] = {}
        self._server_tools: Dict[str, List[Dict]] = {}
        self._cache_enabled: bool = True

    def build(self, servers_tools: Dict[str, List]) -> Dict:
        """Build manifest from server tools.

        Args:
            servers_tools: Dict mapping server name to list of tools

        Returns:
            Built manifest dictionary with servers, tools, and metadata
        """
        self._server_tools = servers_tools
        manifest: Dict[str, Any] = {
            "version": "2.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "servers": {},
            "tools_by_server": {},
            "tool_count": 0,
            "server_count": len(servers_tools),
        }

        for server_name, tools in servers_tools.items():
            tool_list = []
            categories: Set[str] = set()

            for tool in tools:
                if not isinstance(tool, dict) or "name" not in tool:
                    logger.warning(f"Invalid tool from {server_name}: {tool}")
                    continue

                tool_entry = {
                    "name": tool.get("name"),
                    "description": tool.get("description", ""),
                    "inputSchema": tool.get("inputSchema", {}),
                }
                tool_list.append(tool_entry)

                category = self._extract_category(tool)
                if category:
                    categories.add(category)

            manifest["servers"][server_name] = {
                "tool_count": len(tool_list),
                "categories": sorted(list(categories)),
                "status": "active",
            }
            manifest["tools_by_server"][server_name] = tool_list
            manifest["tool_count"] += len(tool_list)

        self._manifest = manifest
        self._save_cache()

        logger.info(
            f"Built manifest with {manifest['tool_count']} tools from "
            f"{manifest['server_count']} servers"
        )
        return manifest

    def _extract_category(self, tool: Dict) -> Optional[str]:
        """Extract category from tool name or description.

        Args:
            tool: Tool dictionary

        Returns:
            Category string or None
        """
        name = tool.get("name", "")
        if "__" in name:
            prefix = name.split("__")[0]
            return prefix.replace("_", " ").title()
        return None

    def get_servers(self, namespace: Optional[str] = None) -> List:
        """Get filtered server list based on namespace.

        Args:
            namespace: Optional namespace to filter by

        Returns:
            List of server names
        """
        if not self._manifest:
            logger.warning("Manifest not built, returning empty server list")
            return []

        if namespace is None:
            return list(self._manifest.get("servers", {}).keys())

        resolved_servers = self.resolve_namespace(namespace)
        return [s for s in resolved_servers if s in self._manifest.get("servers", {})]

    def get_tools(self, server: str, namespace: Optional[str] = None) -> List:
        """Get filtered tools for a server.

        Args:
            server: Server name to get tools for
            namespace: Optional namespace filter

        Returns:
            List of tools for the server
        """
        if not self._manifest:
            logger.warning("Manifest not built, returning empty tools list")
            return []

        if namespace is not None:
            allowed_servers = self.resolve_namespace(namespace)
            if server not in allowed_servers:
                logger.warning(f"Server '{server}' not in namespace '{namespace}'")
                return []

        return self._manifest.get("tools_by_server", {}).get(server, [])

    def validate_inheritance(self, namespaces: Dict) -> List[str]:
        """Validate namespace inheritance for cycles and missing refs.

        Args:
            namespaces: Dict of namespace definitions

        Returns:
            List of warning messages (cycles detected, etc.)
        """
        warnings: List[str] = []
        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        def detect_cycle(ns_name: str, path: List[str]) -> bool:
            """Detect circular inheritance.

            Args:
                ns_name: Current namespace name
                path: Current path of namespace names

            Returns:
                True if cycle detected
            """
            if ns_name in rec_stack:
                cycle_path = " -> ".join(path + [ns_name])
                warnings.append(f"Circular inheritance detected: {cycle_path}")
                return True

            if ns_name in visited:
                return False

            visited.add(ns_name)
            rec_stack.add(ns_name)

            ns_def = namespaces.get(ns_name)
            if ns_def is None:
                warnings.append(f"Missing namespace reference: '{ns_name}'")
                return False

            extends = self._get_extends(ns_def)
            for ext in extends:
                if ext not in namespaces:
                    raise NamespaceInheritanceError(
                        f"Missing extends reference: '{ext}' in namespace '{ns_name}'"
                    )
                detect_cycle(ext, path + [ns_name])

            rec_stack.remove(ns_name)
            return False

        for ns_name in namespaces:
            if ns_name not in visited:
                detect_cycle(ns_name, [])

        self._namespaces = namespaces
        return warnings

    def _get_extends(self, ns_def: Any) -> List[str]:
        """Get extends list from namespace definition.

        Args:
            ns_def: Namespace definition (list or dict)

        Returns:
            List of extended namespace names
        """
        if isinstance(ns_def, list):
            return []
        elif isinstance(ns_def, dict):
            return ns_def.get("extends", [])
        return []

    def _get_servers_from_ns(self, ns_def: Any) -> List[str]:
        """Get servers list from namespace definition.

        Args:
            ns_def: Namespace definition (list or dict)

        Returns:
            List of server names
        """
        if isinstance(ns_def, list):
            return ns_def
        elif isinstance(ns_def, dict):
            return ns_def.get("servers", [])
        return []

    def resolve_namespace(self, namespace: str) -> List[str]:
        """Resolve namespace inheritance to get all accessible servers.

        Args:
            namespace: Namespace name to resolve

        Returns:
            List of all accessible server names (including inherited)

        Raises:
            NamespaceInheritanceError: If namespace not found
        """
        if not self._namespaces:
            self._load_namespaces_from_config()

        if namespace not in self._namespaces:
            raise NamespaceInheritanceError(f"Namespace not found: '{namespace}'")

        resolved: Set[str] = set()
        self._resolve_recursive(namespace, resolved, set())
        return sorted(list(resolved))

    def _resolve_recursive(
        self, namespace: str, resolved: Set[str], visiting: Set[str]
    ) -> None:
        """Recursively resolve namespace inheritance.

        Args:
            namespace: Current namespace to resolve
            resolved: Set of resolved server names
            visiting: Set of currently visiting namespaces (for cycle detection)
        """
        if namespace in visiting:
            logger.warning(f"Skipping circular reference to '{namespace}'")
            return

        ns_def = self._namespaces.get(namespace)
        if ns_def is None:
            logger.warning(f"Namespace '{namespace}' not found during resolution")
            return

        visiting.add(namespace)

        servers = self._get_servers_from_ns(ns_def)
        resolved.update(servers)

        extends = self._get_extends(ns_def)
        for ext in extends:
            self._resolve_recursive(ext, resolved, visiting)

        visiting.remove(namespace)

    def _load_namespaces_from_config(self) -> None:
        """Load namespaces and groups from config file if available."""
        config_path = Path("mcproxy.json")
        if config_path.exists():
            try:
                with open(config_path) as f:
                    config = json.load(f)
                self._namespaces = config.get("namespaces", {})
                self._groups = config.get("groups", {})
            except Exception as e:
                logger.warning(f"Failed to load namespaces from config: {e}")

    def _save_cache(self) -> None:
        """Save manifest to cache file."""
        if not self._cache_enabled:
            return

        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_data = {
                "manifest": self._manifest,
                "namespaces": self._namespaces,
                "cached_at": datetime.now(timezone.utc).isoformat(),
            }
            with open(CACHE_FILE, "w") as f:
                json.dump(cache_data, f, indent=2)
            logger.debug(f"Manifest cached to {CACHE_FILE}")
        except Exception as e:
            logger.warning(f"Failed to cache manifest: {e}")

    def load_cache(self) -> Optional[Dict]:
        """Load manifest from cache if fresh.

        Returns:
            Cached manifest or None if not available/stale
        """
        if not self._cache_enabled or not CACHE_FILE.exists():
            return None

        try:
            with open(CACHE_FILE) as f:
                cache_data = json.load(f)

            cached_at_str = cache_data.get("cached_at")
            if cached_at_str:
                cached_at = datetime.fromisoformat(cached_at_str)
                age = (datetime.now(timezone.utc) - cached_at).total_seconds()
                if age > CACHE_TTL_SECONDS:
                    logger.debug("Cache expired, rebuilding")
                    return None

            self._manifest = cache_data.get("manifest", {})
            self._namespaces = cache_data.get("namespaces", {})
            logger.info(f"Loaded manifest from cache ({len(self._manifest)} entries)")
            return self._manifest
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
            return None

    def invalidate_cache(self) -> None:
        """Invalidate the manifest cache."""
        self._manifest = {}
        try:
            if CACHE_FILE.exists():
                CACHE_FILE.unlink()
                logger.debug("Cache invalidated")
        except Exception as e:
            logger.warning(f"Failed to invalidate cache: {e}")

    def resolve_group_to_servers(self, group_name: str) -> list[str]:
        """Resolve a group to merged list of server names.

        Args:
            group_name: Name of the group to resolve

        Returns:
            Sorted list of unique server names from all namespaces in the group
        """
        if not self._groups:
            self._load_namespaces_from_config()

        group_def = self._groups.get(group_name)
        if not group_def:
            logger.warning(f"Group '{group_name}' not found")
            return []

        all_servers: set[str] = set()
        ns_refs = group_def.get("namespaces", [])

        for ns_ref in ns_refs:
            actual_name = ns_ref[1:] if ns_ref.startswith("!") else ns_ref
            try:
                servers = self.resolve_namespace(actual_name)
                all_servers.update(servers)
            except NamespaceInheritanceError as e:
                logger.warning(
                    f"Failed to resolve namespace '{actual_name}' in group: {e}"
                )

        return sorted(list(all_servers))

    def get_default_servers(self) -> list[str]:
        """Get servers for unnamespaced /sse endpoint.

        Returns unnamespaced servers plus all non-isolated namespace servers.

        Returns:
            Sorted list of server names accessible via default endpoint
        """
        if not self._namespaces:
            self._load_namespaces_from_config()

        all_servers: set[str] = set()

        for ns_name, ns_def in self._namespaces.items():
            is_isolated = (
                ns_def.get("isolated", False) if isinstance(ns_def, dict) else False
            )
            if not is_isolated:
                try:
                    servers = self.resolve_namespace(ns_name)
                    all_servers.update(servers)
                except NamespaceInheritanceError as e:
                    logger.warning(f"Failed to resolve namespace '{ns_name}': {e}")

        return sorted(list(all_servers))

    def is_namespace_isolated(self, namespace: str) -> bool:
        """Check if namespace requires explicit endpoint.

        Args:
            namespace: Namespace name to check

        Returns:
            True if namespace is isolated, False otherwise
        """
        if not self._namespaces:
            self._load_namespaces_from_config()

        ns_def = self._namespaces.get(namespace)
        if ns_def is None:
            return False

        if isinstance(ns_def, dict):
            return ns_def.get("isolated", False)
        return False

    def resolve_endpoint_to_servers(
        self, endpoint_name: Optional[str]
    ) -> tuple[list[str], Optional[str]]:
        """Resolve endpoint name (namespace or group) to servers.

        Args:
            endpoint_name: Namespace name, group name, or None for default

        Returns:
            (servers, error_message) - error_message is None on success
        """
        if not self._namespaces:
            self._load_namespaces_from_config()

        if endpoint_name is None:
            return self.get_default_servers(), None

        if endpoint_name in self._groups:
            servers = self.resolve_group_to_servers(endpoint_name)
            if not servers:
                return [], f"Group '{endpoint_name}' resolved to no servers"
            return servers, None

        if endpoint_name in self._namespaces:
            try:
                servers = self.resolve_namespace(endpoint_name)
                return servers, None
            except NamespaceInheritanceError as e:
                return [], str(e)

        return [], f"Unknown endpoint: '{endpoint_name}'"


class ManifestQuery:
    """Query interface for manifest data.

    Supports hierarchical search with depth levels and fuzzy matching.
    """

    def __init__(self, registry: CapabilityRegistry) -> None:
        """Initialize query interface.

        Args:
            registry: CapabilityRegistry instance to query
        """
        self._registry = registry

    def search(
        self,
        query: str,
        namespace: Optional[str] = None,
        max_depth: int = 2,
    ) -> Dict:
        """Search manifest with fuzzy matching.

        Depth levels:
            0: Server names only
            1: Server names + categories
            2: Server names + categories + tool names
            3: Full tool schemas

        Args:
            query: Search query string
            namespace: Optional namespace filter
            max_depth: Maximum depth level (0-3)
            Returns:
            Search results dictionary
        """
        manifest = self._registry._manifest
        if not manifest:
            return {"error": "Manifest not built", "results": []}

        results: Dict[str, Any] = {
            "query": query,
            "namespace": namespace,
            "max_depth": max_depth,
            "results": [],
            "matches": {
                "servers": [],
                "categories": [],
                "tools": [],
            },
        }

        servers = self._registry.get_servers(namespace)
        query_lower = query.lower() if query else ""
        min_similarity = 0.4

        # Empty/short queries show all results at higher depths
        show_all = max_depth >= 1 and (not query_lower or len(query_lower) <= 1)

        for server_name in servers:
            # For show_all mode (empty query + max_depth >= 1), match everything
            if show_all:
                server_match_score = 1.0
            else:
                server_match_score = self._fuzzy_match(
                    query_lower, server_name.lower(), min_similarity
                )

            if server_match_score >= min_similarity or max_depth >= 1 or show_all:
                server_entry: Dict[str, Any] = {
                    "server": server_name,
                    "match_score": server_match_score,
                }

                if server_match_score >= min_similarity:
                    results["matches"]["servers"].append(server_name)

                if max_depth >= 1:
                    server_info = manifest.get("servers", {}).get(server_name, {})
                    categories = server_info.get("categories", [])
                    matched_categories = []

                    for cat in categories:
                        cat_score = self._fuzzy_match(
                            query_lower, cat.lower(), min_similarity
                        )
                        if cat_score >= min_similarity:
                            matched_categories.append(cat)
                            results["matches"]["categories"].append(
                                f"{server_name}:{cat}"
                            )

                    server_entry["categories"] = categories
                    server_entry["matched_categories"] = matched_categories

                if max_depth >= 2:
                    tools = self._registry.get_tools(server_name, namespace)
                    matched_tools = []

                    for tool in tools:
                        tool_name = tool.get("name", "")
                        tool_desc = tool.get("description", "")

                        name_score = self._fuzzy_match(
                            query_lower, tool_name.lower(), min_similarity
                        )
                        desc_score = self._fuzzy_match(
                            query_lower, tool_desc.lower(), min_similarity * 0.7
                        )

                        best_score = max(name_score, desc_score)
                        if best_score >= min_similarity:
                            tool_match = {
                                "name": tool_name,
                                "match_score": best_score,
                            }

                            if max_depth >= 3:
                                tool_match["description"] = tool_desc
                                tool_match["inputSchema"] = tool.get("inputSchema", {})

                            matched_tools.append(tool_match)
                            results["matches"]["tools"].append(
                                f"{server_name}:{tool_name}"
                            )

                    server_entry["tools"] = len(tools)
                    server_entry["matched_tools"] = matched_tools

                # Add to results if: query matches OR showing all (max_depth >= 1 without specific match)
                should_include = (
                    server_match_score >= min_similarity
                    or server_entry.get("matched_categories")
                    or server_entry.get("matched_tools")
                    or show_all
                )

                if should_include:
                    results["results"].append(server_entry)

        results["total_matches"] = sum(
            len(results["matches"][k]) for k in results["matches"]
        )
        return results

    def _fuzzy_match(self, query: str, target: str, threshold: float) -> float:
        """Calculate fuzzy match score between query and target.

        Args:
            query: Query string
            target: Target string to match against
            threshold: Minimum similarity threshold

        Returns:
            Similarity score (0.0 to 1.0)
        """
        if query in target:
            return 1.0

        query_words = query.split()
        target_words = target.split()

        if not query_words or not target_words:
            return SequenceMatcher(None, query, target).ratio()

        word_matches = 0
        for qw in query_words:
            for tw in target_words:
                if qw in tw or SequenceMatcher(None, qw, tw).ratio() >= threshold:
                    word_matches += 1
                    break

        return word_matches / len(query_words)


class EventHookManager:
    """Manager for event hooks that trigger manifest rebuilds.

    Supports event-driven manifest updates with incremental rebuilding.
    """

    VALID_EVENTS = {"startup", "config_change", "server_health", "manual"}

    def __init__(self, registry: CapabilityRegistry) -> None:
        """Initialize event hook manager.

        Args:
            registry: CapabilityRegistry instance to manage
        """
        self._registry = registry
        self._hooks: Dict[str, List[Callable]] = defaultdict(list)
        self._last_event: Optional[Dict[str, Any]] = None
        self._event_history: List[Dict[str, Any]] = []
        self._max_history = 100

    def register_hook(self, event_type: str, callback: Callable) -> None:
        """Register a callback for an event type.

        Args:
            event_type: Event type name
            callback: Callback function to execute

        Raises:
            ValueError: If event type is invalid
        """
        if event_type not in self.VALID_EVENTS:
            raise ValueError(
                f"Invalid event type '{event_type}'. Valid types: {self.VALID_EVENTS}"
            )

        self._hooks[event_type].append(callback)
        logger.debug(f"Registered hook for event '{event_type}'")

    def trigger(self, event_type: str, data: Any = None) -> Dict[str, Any]:
        """Fire an event and execute all registered hooks.

        Triggers manifest rebuild (incremental if possible).

        Args:
            event_type: Event type to trigger
            data: Event data payload

        Returns:
            Trigger result with execution status
        """
        if event_type not in self.VALID_EVENTS:
            logger.warning(f"Attempted to trigger invalid event: {event_type}")
            return {"error": f"Invalid event type: {event_type}"}

        event_record = {
            "event_type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "results": [],
        }

        for callback in self._hooks[event_type]:
            try:
                result = callback(data) if data is not None else callback()
                event_record["results"].append(
                    {
                        "callback": callback.__name__,
                        "status": "success",
                        "result": result,
                    }
                )
            except Exception as e:
                logger.error(f"Hook callback failed for {event_type}: {e}")
                event_record["results"].append(
                    {"callback": callback.__name__, "status": "error", "error": str(e)}
                )

        self._rebuild_manifest(event_type, data)

        self._last_event = event_record
        self._event_history.append(event_record)
        if len(self._event_history) > self._max_history:
            self._event_history.pop(0)

        logger.info(
            f"Triggered event '{event_type}' with {len(event_record['results'])} hooks"
        )

        return {
            "event_type": event_type,
            "hooks_executed": len(event_record["results"]),
            "timestamp": event_record["timestamp"],
        }

    def _rebuild_manifest(self, event_type: str, data: Any) -> None:
        """Rebuild manifest after event.

        Attempts incremental rebuild when possible.

        Args:
            event_type: Event that triggered rebuild
            data: Event data
        """
        if event_type == "config_change":
            self._registry.invalidate_cache()
            logger.info("Manifest cache invalidated due to config change")

        elif event_type == "server_health":
            if isinstance(data, dict):
                server_name = data.get("server")
                status = data.get("status")
                if server_name and status:
                    manifest = self._registry._manifest
                    if server_name in manifest.get("servers", {}):
                        manifest["servers"][server_name]["status"] = status
                        logger.debug(
                            f"Updated server '{server_name}' status to '{status}'"
                        )

        elif event_type == "startup":
            cached = self._registry.load_cache()
            if cached:
                logger.info("Loaded manifest from cache on startup")
            else:
                logger.info("No valid cache found on startup, manifest needs building")

        elif event_type == "manual":
            self._registry.invalidate_cache()
            logger.info("Manifest invalidated by manual trigger")

    def get_event_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent event history.

        Args:
            limit: Maximum number of events to return

        Returns:
            List of recent event records
        """
        return self._event_history[-limit:]

    def get_last_event(self) -> Optional[Dict[str, Any]]:
        """Get the most recent event.

        Returns:
            Last event record or None
        """
        return self._last_event

    def clear_hooks(self, event_type: Optional[str] = None) -> int:
        """Clear registered hooks.

        Args:
            event_type: Specific event to clear, or None for all

        Returns:
            Number of hooks cleared
        """
        if event_type is None:
            count = sum(len(hooks) for hooks in self._hooks.values())
            self._hooks.clear()
            return count

        count = len(self._hooks.get(event_type, []))
        self._hooks[event_type] = []
        return count
