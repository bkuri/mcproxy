"""OAuth token endpoint and JWT validation for MCProxy.

Implements client credentials flow for agent authentication.
"""

import json
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from auth.agent_registry import AgentRegistry, AgentRegistryError
from auth.jwt_keys import JWTIssuer, JWTKeyError, JWTValidator
from logging_config import get_logger

logger = get_logger(__name__)

security = HTTPBearer(auto_error=False)


class OAuthError(Exception):
    """OAuth protocol error."""

    def __init__(self, error: str, description: str):
        self.error = error
        self.description = description
        super().__init__(f"{error}: {description}")


class AuthContext:
    """Authentication context for a request."""

    def __init__(
        self,
        agent_id: str,
        scopes: List[str],
        namespace: str,
        tenant_id: Optional[str] = None,
    ):
        self.agent_id = agent_id
        self.scopes = scopes
        self.namespace = namespace
        self.tenant_id = tenant_id


class OAuthHandler:
    """Handles OAuth token endpoint operations."""

    def __init__(
        self,
        agent_registry: AgentRegistry,
        jwt_issuer: JWTIssuer,
        jwt_validator: JWTValidator,
    ):
        """Initialize OAuth handler.

        Args:
            agent_registry: AgentRegistry instance
            jwt_issuer: JWTIssuer instance
            jwt_validator: JWTValidator instance
        """
        self.agent_registry = agent_registry
        self.jwt_issuer = jwt_issuer
        self.jwt_validator = jwt_validator

    async def handle_token_request(
        self,
        grant_type: str,
        client_id: str,
        client_secret: str,
        scope: Optional[str] = None,
        ttl_hours: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Handle OAuth token request (client credentials flow).

        Args:
            grant_type: Must be 'client_credentials'
            client_id: Agent's client ID
            client_secret: Agent's client secret
            scope: Optional space-separated list of scopes
            ttl_hours: Optional token TTL override

        Returns:
            Token response dict

        Raises:
            OAuthError: If request is invalid
        """
        if grant_type != "client_credentials":
            raise OAuthError(
                "unsupported_grant_type",
                "Only client_credentials grant type is supported",
            )

        try:
            agent = self.agent_registry.authenticate(client_id, client_secret)
        except AgentRegistryError as e:
            raise OAuthError("invalid_client", str(e))

        if not agent:
            raise OAuthError("invalid_client", "Agent not found")

        if not agent.enabled:
            raise OAuthError("invalid_client", "Agent is disabled")

        allowed_scopes: List[str] = list(agent.allowed_scopes)

        requested_scopes = scope.split() if scope else []

        granted_scopes = []
        for req_scope in requested_scopes:
            if req_scope in allowed_scopes:
                granted_scopes.append(req_scope)
            else:
                parts = req_scope.split(":", 1)
                if len(parts) == 2:
                    service, _ = parts
                    wildcard = f"{service}:*"
                    if wildcard in allowed_scopes:
                        granted_scopes.append(req_scope)

        if requested_scopes and not granted_scopes:
            raise OAuthError(
                "invalid_scope",
                f"None of the requested scopes are allowed",
            )

        scope_str = (
            " ".join(granted_scopes) if granted_scopes else " ".join(allowed_scopes)
        )

        token_response = self.jwt_issuer.issue_token(
            agent_id=agent.agent_id,
            scopes=scope_str,
            namespace=agent.namespace,
            ttl_hours=ttl_hours,
            tenant_id=agent.tenant_id,
        )

        logger.info(f"Issued token for agent {agent.agent_id} with scopes: {scope_str}")

        return token_response

    def validate_token(self, token: str) -> AuthContext:
        """Validate a JWT token and return auth context.

        Args:
            token: JWT token string

        Returns:
            AuthContext with agent info

        Raises:
            HTTPException: If token is invalid
        """
        try:
            claims = self.jwt_validator.validate(token)
        except JWTKeyError as e:
            raise HTTPException(
                status_code=401,
                detail=str(e),
                headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            )

        agent_id: str = claims.get("agent_id") or ""
        scope_str: str = claims.get("scope", "")
        namespace: str = claims.get("namespace", "default")
        tenant_id: Optional[str] = claims.get("tenant_id")

        scopes: List[str] = scope_str.split() if scope_str else []

        return AuthContext(
            agent_id=agent_id,
            scopes=scopes,
            namespace=namespace,
            tenant_id=tenant_id,
        )


def create_auth_dependency(oauth_handler: OAuthHandler):
    """Create a FastAPI dependency for authentication.

    Args:
        oauth_handler: OAuthHandler instance

    Returns:
        Dependency function
    """

    async def get_auth_context(
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    ) -> Optional[AuthContext]:
        """Get authentication context from request.

        Args:
            request: FastAPI request
            credentials: Bearer token credentials

        Returns:
            AuthContext or None if auth is disabled
        """
        auth_config = getattr(request.app.state, "auth_config", None)

        if not auth_config or not auth_config.get("enabled", False):
            return None

        if credentials is None:
            raise HTTPException(
                status_code=401,
                detail="Missing authorization header",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return oauth_handler.validate_token(credentials.credentials)

    return get_auth_context


def create_optional_auth_dependency(oauth_handler: OAuthHandler):
    """Create an optional FastAPI dependency for authentication.

    Unlike the required dependency, this returns None instead of raising
    if no token is provided.

    Args:
        oauth_handler: OAuthHandler instance

    Returns:
        Dependency function
    """

    async def get_optional_auth_context(
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    ) -> Optional[AuthContext]:
        """Get optional authentication context from request.

        Args:
            request: FastAPI request
            credentials: Bearer token credentials

        Returns:
            AuthContext or None
        """
        auth_config = getattr(request.app.state, "auth_config", None)

        if not auth_config or not auth_config.get("enabled", False):
            return None

        if credentials is None:
            return None

        try:
            return oauth_handler.validate_token(credentials.credentials)
        except HTTPException:
            return None

    return get_optional_auth_context
