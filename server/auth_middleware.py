"""Static API key authentication middleware for MCProxy v4.2.

This module provides simple API key-based authentication as a replacement for JWT.
API keys are stored in the agent registry and validated against incoming requests.
"""

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from auth import AgentRegistry
from logging_config import get_logger

logger = get_logger(__name__)

_agent_registry: Optional[AgentRegistry] = None
_auth_config: Optional[dict] = None
_router = APIRouter(tags=["auth"])


def configure_static_key_auth(agent_registry: AgentRegistry, auth_config: dict) -> None:
    """Configure static key authentication.

    Args:
        agent_registry: Agent registry for API key lookup
        auth_config: Auth configuration dict
    """
    global _agent_registry, _auth_config
    _agent_registry = agent_registry
    _auth_config = auth_config


def get_agent_registry(request: Request) -> AgentRegistry:
    """Get agent registry from app state."""
    if _agent_registry is not None:
        return _agent_registry
    registry = getattr(request.app.state, "agent_registry", None)
    if not registry:
        raise HTTPException(status_code=500, detail="Agent registry not configured")
    return registry


def static_key_auth(request: Request) -> dict:
    """Validate static API key from Authorization header.

    Expected header: Authorization: Bearer <api_key>

    Returns:
        Dict with agent info (agent_id, namespace, scopes)

    Raises:
        HTTPException: If API key is invalid or agent is disabled
    """
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
        if _auth_config and _auth_config.get("enabled"):
            raise HTTPException(
                status_code=401,
                detail="Missing or invalid Authorization header. Use 'Authorization: Bearer <api_key>'",
            )
        return {"agent_id": None, "namespace": None, "scopes": []}

    api_key = auth_header[7:]  # Strip "Bearer "

    if not api_key:
        raise HTTPException(status_code=401, detail="Empty API key")

    registry = get_agent_registry(request)
    agent = registry.find_by_api_key(api_key)

    if not agent:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not agent.enabled:
        raise HTTPException(status_code=403, detail="API key disabled")

    return {
        "agent_id": agent.agent_id,
        "namespace": agent.namespace,
        "scopes": list(agent.allowed_scopes),
    }


def optional_static_key_auth(request: Request) -> dict:
    """Optional static key auth - returns empty auth if no header."""
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
        return {"agent_id": None, "namespace": None, "scopes": []}

    return static_key_auth(request)


def create_auth_dependency():
    """Create auth dependency for FastAPI routes."""
    return static_key_auth


def create_optional_auth_dependency():
    """Create optional auth dependency for FastAPI routes."""
    return optional_static_key_auth


def get_current_agent(auth: dict = Depends(static_key_auth)) -> str:
    """Get current agent ID from auth context."""
    return auth.get("agent_id")


def get_current_namespace(auth: dict = Depends(static_key_auth)) -> str:
    """Get current namespace from auth context."""
    return auth.get("namespace")


def get_current_scopes(auth: dict = Depends(static_key_auth)) -> list:
    """Get current scopes from auth context."""
    return auth.get("scopes", [])


__all__ = [
    "configure_static_key_auth",
    "static_key_auth",
    "optional_static_key_auth",
    "create_auth_dependency",
    "create_optional_auth_dependency",
    "get_current_agent",
    "get_current_namespace",
    "get_current_scopes",
]
