"""Scope to credential mapping for MCProxy.

Maps JWT scopes to actual credentials with fallback chain support.
Configuration-driven mapping with service-level and permission-level keys.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from auth.credential_store import CredentialStore
from logging_config import get_logger

logger = get_logger(__name__)


class ScopeResolverError(Exception):
    """Error in scope resolution."""

    pass


@dataclass
class ResolvedCredential:
    """Resolved credential with injection config."""

    value: str
    inject_as: str
    inject_type: str  # 'env' or 'header'
    service: str
    permission: Optional[str] = None


class ScopeResolver:
    """Resolves JWT scopes to actual credentials."""

    def __init__(
        self,
        credential_store: CredentialStore,
        scope_mappings: Dict[str, Any],
        tool_scopes: Dict[str, str],
    ):
        """Initialize scope resolver.

        Args:
            credential_store: CredentialStore instance
            scope_mappings: Config dict mapping scopes to credentials
            tool_scopes: Config dict mapping tool names to required scopes
        """
        self.credential_store = credential_store
        self.scope_mappings = scope_mappings
        self.tool_scopes = tool_scopes

    def resolve_scope(self, scope: str) -> Optional[ResolvedCredential]:
        """Resolve a scope to a credential.

        Implements fallback chain:
        1. Check explicit scope mapping
        2. Parse service:permission from scope
        3. Try service:permission in credential store
        4. Fall back to service:default

        Args:
            scope: Scope string (e.g., 'github:write')

        Returns:
            ResolvedCredential or None if not found
        """
        mapping = self.scope_mappings.get("scopes", {}).get(scope)

        if mapping:
            return self._resolve_from_mapping(scope, mapping)

        parts = scope.split(":", 1)
        if len(parts) != 2:
            logger.warning(f"Invalid scope format: {scope}")
            return None

        service, permission = parts

        credentials_config = self.scope_mappings.get("credentials", {})
        service_config = credentials_config.get(service, {})
        keys_config = service_config.get("keys", {})

        inject_config = keys_config.get(permission) or keys_config.get("default")

        if not inject_config:
            logger.debug(f"No credential mapping for scope {scope}")
            return None

        if isinstance(inject_config, str):
            credential_id = inject_config
            inject_as = self._default_inject_as(service)
            inject_type = "env"
        else:
            credential_id = inject_config.get("credential_id")
            inject_as = inject_config.get("inject_as", self._default_inject_as(service))
            inject_type = inject_config.get("inject_type", "env")

        if not credential_id:
            logger.warning(f"No credential_id in mapping for scope {scope}")
            return None

        value = self.credential_store.resolve(service, permission)
        if value is None:
            logger.warning(
                f"Credential not found for service {service}, permission {permission}"
            )
            return None

        return ResolvedCredential(
            value=value,
            inject_as=inject_as,
            inject_type=inject_type,
            service=service,
            permission=permission,
        )

    def _resolve_from_mapping(
        self, scope: str, mapping: Any
    ) -> Optional[ResolvedCredential]:
        """Resolve credential from explicit mapping config.

        Args:
            scope: Scope string
            mapping: Mapping config (string or dict)

        Returns:
            ResolvedCredential or None
        """
        if isinstance(mapping, str):
            credential_ref = mapping
            inject_as = None
            inject_type = "env"
        else:
            credential_ref = mapping.get("credential")
            inject_as = mapping.get("inject_as")
            inject_type = mapping.get("inject_type", "env")

        if ":" in credential_ref:
            service, permission = credential_ref.split(":", 1)
        else:
            service = credential_ref
            permission = None

        value = self.credential_store.resolve(service, permission)
        if value is None:
            return None

        if not inject_as:
            inject_as = self._default_inject_as(service)

        return ResolvedCredential(
            value=value,
            inject_as=inject_as,
            inject_type=inject_type,
            service=service,
            permission=permission,
        )

    def _default_inject_as(self, service: str) -> str:
        """Get default injection name for a service.

        Args:
            service: Service name

        Returns:
            Default environment variable name
        """
        service_upper = service.upper().replace("-", "_")
        return f"{service_upper}_API_KEY"

    def get_tool_scope(self, tool_name: str) -> Optional[str]:
        """Get the required scope for a tool.

        Args:
            tool_name: Tool name

        Returns:
            Required scope or None
        """
        return self.tool_scopes.get(tool_name)

    def check_scope_permission(
        self, granted_scopes: List[str], required_scope: str
    ) -> bool:
        """Check if granted scopes include the required scope.

        Args:
            granted_scopes: List of scopes from JWT
            required_scope: Required scope for operation

        Returns:
            True if permission is granted
        """
        if required_scope in granted_scopes:
            return True

        parts = required_scope.split(":", 1)
        if len(parts) == 2:
            service, _ = parts
            wildcard_scope = f"{service}:*"
            if wildcard_scope in granted_scopes:
                return True

        return False

    def resolve_for_tool(
        self, tool_name: str, granted_scopes: List[str]
    ) -> Optional[ResolvedCredential]:
        """Resolve credential for a tool call.

        Args:
            tool_name: Tool name
            granted_scopes: Scopes from JWT

        Returns:
            ResolvedCredential or None

        Raises:
            ScopeResolverError: If scope not granted
        """
        required_scope = self.get_tool_scope(tool_name)
        if not required_scope:
            return None

        if not self.check_scope_permission(granted_scopes, required_scope):
            raise ScopeResolverError(
                f"Agent lacks required scope '{required_scope}' for tool '{tool_name}'"
            )

        return self.resolve_scope(required_scope)
