"""Agent registry for MCProxy.

Manages agent client credentials and allowed scopes.
Agents authenticate using OAuth client credentials flow.
"""

import hashlib
import os
import secrets
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from logging_config import get_logger

logger = get_logger(__name__)


class AgentRegistryError(Exception):
    """Error in agent registry operations."""

    pass


@dataclass
class Agent:
    """Registered agent client."""

    agent_id: str
    client_id: str
    client_secret_hash: str
    allowed_scopes: Set[str]
    namespace: str
    tenant_id: Optional[str]
    created_at: datetime
    updated_at: datetime
    enabled: bool = True
    metadata: Optional[Dict[str, Any]] = None
    api_key: Optional[str] = None

    @classmethod
    def generate_api_key(cls) -> str:
        """Generate a random URL-safe API key.

        Returns:
            Random 32-byte URL-safe string
        """
        return secrets.token_urlsafe(32)


class AgentRegistry:
    """Registry for agent clients using SQLite backend."""

    def __init__(self, db_path: str):
        """Initialize agent registry.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agents (
                    agent_id TEXT PRIMARY KEY,
                    client_id TEXT UNIQUE NOT NULL,
                    client_secret_hash TEXT NOT NULL,
                    allowed_scopes TEXT NOT NULL,
                    namespace TEXT NOT NULL,
                    tenant_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    enabled INTEGER DEFAULT 1,
                    metadata TEXT,
                    api_key TEXT UNIQUE
                )
            """)
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_agents_client_id ON agents(client_id)"
            )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_agents_api_key ON agents(api_key)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agents_namespace ON agents(namespace)"
            )
            conn.commit()
        finally:
            conn.close()

    def _hash_secret(self, secret: str) -> str:
        """Hash a client secret using SHA-256.

        Args:
            secret: Plain text secret

        Returns:
            Hex-encoded hash
        """
        return hashlib.sha256(secret.encode()).hexdigest()

    def _generate_client_id(self) -> str:
        """Generate a unique client ID.

        Returns:
            Client ID string
        """
        return f"agent_{secrets.token_hex(8)}"

    def _generate_client_secret(self) -> str:
        """Generate a secure client secret.

        Returns:
            Client secret string
        """
        return secrets.token_urlsafe(32)

    def register(
        self,
        agent_id: Optional[str] = None,
        name: Optional[str] = None,
        allowed_scopes: Optional[List[str]] = None,
        namespace: str = "default",
        tenant_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """Register a new agent client.

        Args:
            agent_id: Optional agent ID. If None, generates UUID.
            name: Optional friendly name for the agent
            allowed_scopes: List of allowed scopes (e.g., ['github:read', 'perplexity:search'])
            namespace: Agent's namespace
            tenant_id: Optional tenant identifier
            metadata: Optional metadata dict

        Returns:
            Dict with agent_id, client_id, client_secret
        """
        if agent_id is None:
            agent_id = str(uuid.uuid4())

        if allowed_scopes is None:
            allowed_scopes = []

        import json

        client_id = self._generate_client_id()
        client_secret = self._generate_client_secret()
        client_secret_hash = self._hash_secret(client_secret)
        api_key = Agent.generate_api_key()

        now = datetime.utcnow().isoformat()

        meta = metadata or {}
        if name:
            meta["name"] = name

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT INTO agents 
                (agent_id, client_id, client_secret_hash, allowed_scopes, namespace, 
                 tenant_id, created_at, updated_at, enabled, metadata, api_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
                (
                    agent_id,
                    client_id,
                    client_secret_hash,
                    json.dumps(sorted(allowed_scopes)),
                    namespace,
                    tenant_id,
                    now,
                    now,
                    json.dumps(meta) if meta else None,
                    api_key,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        logger.info(f"Registered agent {agent_id} with client_id {client_id}")

        return {
            "agent_id": agent_id,
            "client_id": client_id,
            "client_secret": client_secret,
            "api_key": api_key,
        }

    def authenticate(self, client_id: str, client_secret: str) -> Optional[Agent]:
        """Authenticate an agent by client credentials.

        Args:
            client_id: Client ID
            client_secret: Client secret

        Returns:
            Agent if authenticated, None otherwise
        """
        import json

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                SELECT agent_id, client_secret_hash, allowed_scopes, namespace,
                       tenant_id, created_at, updated_at, enabled, metadata, api_key
                FROM agents WHERE client_id = ?
            """,
                (client_id,),
            )
            row = cursor.fetchone()

            if row is None:
                logger.warning(f"Authentication failed: unknown client_id {client_id}")
                return None

            (
                agent_id,
                secret_hash,
                scopes_json,
                namespace,
                tenant_id,
                created_at,
                updated_at,
                enabled,
                meta_json,
                api_key,
            ) = row

            if not enabled:
                logger.warning(f"Authentication failed: agent {agent_id} is disabled")
                return None

            expected_hash = self._hash_secret(client_secret)
            if not secrets.compare_digest(secret_hash, expected_hash):
                logger.warning(f"Authentication failed: invalid secret for {client_id}")
                return None

            return Agent(
                agent_id=agent_id,
                client_id=client_id,
                client_secret_hash=secret_hash,
                allowed_scopes=set(json.loads(scopes_json)),
                namespace=namespace,
                tenant_id=tenant_id,
                created_at=datetime.fromisoformat(created_at),
                updated_at=datetime.fromisoformat(updated_at),
                enabled=bool(enabled),
                metadata=json.loads(meta_json) if meta_json else None,
                api_key=api_key,
            )
        finally:
            conn.close()

    def get_agent(self, agent_id: str) -> Optional[Agent]:
        """Get an agent by ID.

        Args:
            agent_id: Agent ID

        Returns:
            Agent if found, None otherwise
        """
        import json

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                SELECT agent_id, client_id, client_secret_hash, allowed_scopes, namespace,
                       tenant_id, created_at, updated_at, enabled, metadata, api_key
                FROM agents WHERE agent_id = ?
            """,
                (agent_id,),
            )
            row = cursor.fetchone()

            if row is None:
                return None

            (
                agent_id,
                client_id,
                secret_hash,
                scopes_json,
                namespace,
                tenant_id,
                created_at,
                updated_at,
                enabled,
                meta_json,
                api_key,
            ) = row

            return Agent(
                agent_id=agent_id,
                client_id=client_id,
                client_secret_hash=secret_hash,
                allowed_scopes=set(json.loads(scopes_json)),
                namespace=namespace,
                tenant_id=tenant_id,
                created_at=datetime.fromisoformat(created_at),
                updated_at=datetime.fromisoformat(updated_at),
                enabled=bool(enabled),
                metadata=json.loads(meta_json) if meta_json else None,
                api_key=api_key,
            )
        finally:
            conn.close()

    def update_scopes(self, agent_id: str, scopes: List[str]) -> bool:
        """Update an agent's allowed scopes.

        Args:
            agent_id: Agent ID
            scopes: New list of allowed scopes

        Returns:
            True if updated, False if not found
        """
        import json

        conn = sqlite3.connect(self.db_path)
        try:
            now = datetime.utcnow().isoformat()
            cursor = conn.execute(
                """
                UPDATE agents 
                SET allowed_scopes = ?, updated_at = ?
                WHERE agent_id = ?
            """,
                (json.dumps(sorted(scopes)), now, agent_id),
            )
            conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                logger.info(f"Updated scopes for agent {agent_id}")
            return updated
        finally:
            conn.close()

    def rotate_secret(self, agent_id: str) -> Optional[Dict[str, str]]:
        """Rotate an agent's client secret.

        Args:
            agent_id: Agent ID

        Returns:
            Dict with new client_id and client_secret, or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        try:
            new_client_id = self._generate_client_id()
            new_secret = self._generate_client_secret()
            new_hash = self._hash_secret(new_secret)
            now = datetime.utcnow().isoformat()

            cursor = conn.execute(
                """
                UPDATE agents 
                SET client_id = ?, client_secret_hash = ?, updated_at = ?
                WHERE agent_id = ?
            """,
                (new_client_id, new_hash, now, agent_id),
            )
            conn.commit()

            if cursor.rowcount > 0:
                logger.info(f"Rotated secret for agent {agent_id}")
                return {
                    "client_id": new_client_id,
                    "client_secret": new_secret,
                }
            return None
        finally:
            conn.close()

    def disable(self, agent_id: str) -> bool:
        """Disable an agent.

        Args:
            agent_id: Agent ID

        Returns:
            True if disabled, False if not found
        """
        conn = sqlite3.connect(self.db_path)
        try:
            now = datetime.utcnow().isoformat()
            cursor = conn.execute(
                """
                UPDATE agents SET enabled = 0, updated_at = ? WHERE agent_id = ?
            """,
                (now, agent_id),
            )
            conn.commit()
            disabled = cursor.rowcount > 0
            if disabled:
                logger.info(f"Disabled agent {agent_id}")
            return disabled
        finally:
            conn.close()

    def enable(self, agent_id: str) -> bool:
        """Enable a disabled agent.

        Args:
            agent_id: Agent ID

        Returns:
            True if enabled, False if not found
        """
        conn = sqlite3.connect(self.db_path)
        try:
            now = datetime.utcnow().isoformat()
            cursor = conn.execute(
                """
                UPDATE agents SET enabled = 1, updated_at = ? WHERE agent_id = ?
            """,
                (now, agent_id),
            )
            conn.commit()
            enabled = cursor.rowcount > 0
            if enabled:
                logger.info(f"Enabled agent {agent_id}")
            return enabled
        finally:
            conn.close()

    def find_by_api_key(self, api_key: str) -> Optional[Agent]:
        """Find an agent by API key.

        Args:
            api_key: API key to search for

        Returns:
            Agent if found, None otherwise
        """
        import json

        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                SELECT agent_id, client_id, client_secret_hash, allowed_scopes, namespace,
                       tenant_id, created_at, updated_at, enabled, metadata, api_key
                FROM agents WHERE api_key = ?
            """,
                (api_key,),
            )
            row = cursor.fetchone()

            if row is None:
                return None

            (
                agent_id,
                client_id,
                secret_hash,
                scopes_json,
                namespace,
                tenant_id,
                created_at,
                updated_at,
                enabled,
                meta_json,
                api_key,
            ) = row

            return Agent(
                agent_id=agent_id,
                client_id=client_id,
                client_secret_hash=secret_hash,
                allowed_scopes=set(json.loads(scopes_json)),
                namespace=namespace,
                tenant_id=tenant_id,
                created_at=datetime.fromisoformat(created_at),
                updated_at=datetime.fromisoformat(updated_at),
                enabled=bool(enabled),
                metadata=json.loads(meta_json) if meta_json else None,
                api_key=api_key,
            )
        finally:
            conn.close()

    def rotate_api_key(self, agent_id: str) -> Optional[str]:
        """Rotate an agent's API key.

        Args:
            agent_id: Agent ID

        Returns:
            New API key, or None if agent not found
        """
        conn = sqlite3.connect(self.db_path)
        try:
            new_api_key = Agent.generate_api_key()
            now = datetime.utcnow().isoformat()

            cursor = conn.execute(
                """
                UPDATE agents 
                SET api_key = ?, updated_at = ?
                WHERE agent_id = ?
            """,
                (new_api_key, now, agent_id),
            )
            conn.commit()

            if cursor.rowcount > 0:
                logger.info(f"Rotated API key for agent {agent_id}")
                return new_api_key
            return None
        finally:
            conn.close()

    def delete(self, agent_id: str) -> bool:
        """Delete an agent.

        Args:
            agent_id: Agent ID

        Returns:
            True if deleted, False if not found
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("DELETE FROM agents WHERE agent_id = ?", (agent_id,))
            conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted agent {agent_id}")
            return deleted
        finally:
            conn.close()

    def list_agents(
        self,
        namespace: Optional[str] = None,
        enabled_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """List all agents.

        Args:
            namespace: Optional namespace filter
            enabled_only: If True, only return enabled agents

        Returns:
            List of agent info dicts (without secrets)
        """
        import json

        conn = sqlite3.connect(self.db_path)
        try:
            query = """
                SELECT agent_id, client_id, allowed_scopes, namespace,
                       tenant_id, created_at, updated_at, enabled, metadata, api_key
                FROM agents
            """
            params = []
            conditions = []

            if namespace:
                conditions.append("namespace = ?")
                params.append(namespace)
            if enabled_only:
                conditions.append("enabled = 1")

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            cursor = conn.execute(query, params)

            results = []
            for row in cursor.fetchall():
                (
                    agent_id,
                    client_id,
                    scopes_json,
                    namespace,
                    tenant_id,
                    created_at,
                    updated_at,
                    enabled,
                    meta_json,
                    api_key,
                ) = row

                results.append(
                    {
                        "agent_id": agent_id,
                        "client_id": client_id,
                        "allowed_scopes": json.loads(scopes_json),
                        "namespace": namespace,
                        "tenant_id": tenant_id,
                        "created_at": created_at,
                        "updated_at": updated_at,
                        "enabled": bool(enabled),
                        "metadata": json.loads(meta_json) if meta_json else None,
                        "api_key": api_key,
                    }
                )

            return results
        finally:
            conn.close()
