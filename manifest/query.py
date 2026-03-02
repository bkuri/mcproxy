"""Query interface for manifest data."""

from typing import Any, Dict, Optional

from utils.fuzzy_match import fuzzy_score

from .registry import CapabilityRegistry


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

        show_all = max_depth >= 1 and (not query_lower or len(query_lower) <= 1)

        for server_name in servers:
            if show_all:
                server_match_score = 1.0
            else:
                server_match_score = fuzzy_score(
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
                        cat_score = fuzzy_score(
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

                        name_score = fuzzy_score(
                            query_lower, tool_name.lower(), min_similarity
                        )
                        desc_score = fuzzy_score(
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
