"""Authentication and credential management for MCProxy v4.2.

This module provides:
- Encrypted credential storage (credential_store)
- Agent client registry (agent_registry)
- Scope to credential mapping (scope_resolver)

Usage:
    from auth import CredentialStore, AgentRegistry, ScopeResolver

    # Initialize components
    cred_store = CredentialStore("credentials.db", encryption_key)
    agent_registry = AgentRegistry("agents.db")
"""

from auth.credential_store import Credential, CredentialError, CredentialStore
from auth.agent_registry import Agent, AgentRegistry, AgentRegistryError
from auth.scope_resolver import ResolvedCredential, ScopeResolver, ScopeResolverError
from auth.audit_logger import AuditEventType, AuditLogger

__all__ = [
    "CredentialStore",
    "Credential",
    "CredentialError",
    "AgentRegistry",
    "Agent",
    "AgentRegistryError",
    "ScopeResolver",
    "ResolvedCredential",
    "ScopeResolverError",
    "AuditLogger",
    "AuditEventType",
]
