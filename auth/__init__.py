"""Authentication and credential management for MCProxy v4.1.

This module provides:
- Encrypted credential storage (credential_store)
- JWT key management and token issuance (jwt_keys)
- Agent client registry (agent_registry)
- Scope to credential mapping (scope_resolver)
- OAuth token endpoint and validation (oauth)

Usage:
    from auth import CredentialStore, AgentRegistry, JWTIssuer, JWTValidator

    # Initialize components
    cred_store = CredentialStore("credentials.db", encryption_key)
    agent_registry = AgentRegistry("agents.db")
    key_manager = JWTKeyManager("/path/to/keys")
    jwt_issuer = JWTIssuer(key_manager)
    jwt_validator = JWTValidator(key_manager)
"""

from auth.credential_store import Credential, CredentialError, CredentialStore
from auth.jwt_keys import JWTIssuer, JWTKeyError, JWTKeyManager, JWTValidator
from auth.agent_registry import Agent, AgentRegistry, AgentRegistryError
from auth.scope_resolver import ResolvedCredential, ScopeResolver, ScopeResolverError
from auth.oauth import (
    AuthContext,
    OAuthError,
    OAuthHandler,
    create_auth_dependency,
    create_optional_auth_dependency,
)
from auth.audit_logger import AuditEventType, AuditLogger

__all__ = [
    "CredentialStore",
    "Credential",
    "CredentialError",
    "JWTKeyManager",
    "JWTIssuer",
    "JWTValidator",
    "JWTKeyError",
    "AgentRegistry",
    "Agent",
    "AgentRegistryError",
    "ScopeResolver",
    "ResolvedCredential",
    "ScopeResolverError",
    "OAuthHandler",
    "OAuthError",
    "AuthContext",
    "create_auth_dependency",
    "create_optional_auth_dependency",
    "AuditLogger",
    "AuditEventType",
]
