"""Event hook manager for manifest rebuilds."""

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from logging_config import get_logger

from .registry import CapabilityRegistry

logger = get_logger(__name__)


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
