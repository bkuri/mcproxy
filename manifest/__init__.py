"""Manifest system v2.0 for MCProxy.

Provides capability registry, manifest queries, event hooks, and namespace inheritance.
"""

from .errors import ManifestError, NamespaceInheritanceError, validate_group
from .hooks import EventHookManager
from .query import ManifestQuery
from .registry import CACHE_DIR, CACHE_FILE, CACHE_TTL_SECONDS, CapabilityRegistry

__all__ = [
    "CapabilityRegistry",
    "ManifestQuery",
    "EventHookManager",
    "ManifestError",
    "NamespaceInheritanceError",
    "validate_group",
    "CACHE_DIR",
    "CACHE_FILE",
    "CACHE_TTL_SECONDS",
]
