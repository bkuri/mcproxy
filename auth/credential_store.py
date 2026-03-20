"""Encrypted credential storage for MCProxy.

Implements AES-256-GCM encryption for API keys and secrets.
Credentials are stored in SQLite database with automatic IV generation.
"""

import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from logging_config import get_logger

logger = get_logger(__name__)


class CredentialError(Exception):
    """Error in credential operations."""

    pass


@dataclass
class Credential:
    """Stored credential with metadata."""

    id: str
    service: str
    permission: Optional[str]
    encrypted_value: bytes
    iv: bytes
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None


class CredentialStore:
    """Encrypted credential storage using SQLite + AES-256-GCM."""

    def __init__(self, db_path: str, encryption_key: Optional[bytes] = None):
        """Initialize credential store.

        Args:
            db_path: Path to SQLite database file
            encryption_key: 32-byte encryption key. If None, reads from MCPROXY_CREDENTIAL_KEY env var.

        Raises:
            CredentialError: If encryption key is not provided or invalid
        """
        self.db_path = Path(db_path)

        if encryption_key is None:
            key_hex = os.environ.get("MCPROXY_CREDENTIAL_KEY")
            if not key_hex:
                raise CredentialError(
                    "Encryption key not provided. Set MCPROXY_CREDENTIAL_KEY env var "
                    "or pass encryption_key parameter."
                )
            try:
                encryption_key = bytes.fromhex(key_hex)
            except ValueError as e:
                raise CredentialError(f"Invalid encryption key format: {e}")

        if len(encryption_key) != 32:
            raise CredentialError(
                f"Encryption key must be 32 bytes, got {len(encryption_key)}"
            )

        self.key = encryption_key
        self.aesgcm = AESGCM(self.key)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS credentials (
                    id TEXT PRIMARY KEY,
                    service TEXT NOT NULL,
                    permission TEXT,
                    encrypted_value BLOB NOT NULL,
                    iv BLOB NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    expires_at TEXT
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_credentials_service ON credentials(service)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_credentials_service_permission ON credentials(service, permission)"
            )
            conn.commit()
        finally:
            conn.close()

    def _encrypt(self, plaintext: str) -> tuple[bytes, bytes]:
        """Encrypt plaintext using AES-256-GCM.

        Args:
            plaintext: String to encrypt

        Returns:
            Tuple of (ciphertext, iv)
        """
        iv = os.urandom(12)
        ciphertext = self.aesgcm.encrypt(iv, plaintext.encode("utf-8"), None)
        return ciphertext, iv

    def _decrypt(self, ciphertext: bytes, iv: bytes) -> str:
        """Decrypt ciphertext using AES-256-GCM.

        Args:
            ciphertext: Encrypted data
            iv: Initialization vector

        Returns:
            Decrypted string

        Raises:
            CredentialError: If decryption fails
        """
        try:
            plaintext = self.aesgcm.decrypt(iv, ciphertext, None)
            return plaintext.decode("utf-8")
        except Exception as e:
            raise CredentialError(f"Decryption failed: {e}")

    def store(
        self,
        service: str,
        value: str,
        credential_id: Optional[str] = None,
        permission: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        expires_at: Optional[datetime] = None,
    ) -> str:
        """Store a credential.

        Args:
            service: Service name (e.g., 'github', 'perplexity')
            value: The secret value to store
            credential_id: Optional ID. If None, generates UUID.
            permission: Optional permission level (e.g., 'read', 'write')
            metadata: Optional metadata dict
            expires_at: Optional expiration datetime

        Returns:
            Credential ID
        """
        if credential_id is None:
            credential_id = str(uuid.uuid4())

        encrypted_value, iv = self._encrypt(value)
        now = datetime.utcnow().isoformat()
        expires_str = expires_at.isoformat() if expires_at else None

        import json

        metadata_json = json.dumps(metadata or {})

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO credentials 
                (id, service, permission, encrypted_value, iv, metadata, created_at, updated_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    credential_id,
                    service,
                    permission,
                    encrypted_value,
                    iv,
                    metadata_json,
                    now,
                    now,
                    expires_str,
                ),
            )
            conn.commit()
        finally:
            conn.close()

        logger.info(f"Stored credential {credential_id} for service {service}")
        return credential_id

    def get(self, credential_id: str) -> Optional[str]:
        """Retrieve a credential value by ID.

        Args:
            credential_id: Credential ID

        Returns:
            Decrypted credential value, or None if not found/expired
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                """
                SELECT encrypted_value, iv, expires_at 
                FROM credentials WHERE id = ?
            """,
                (credential_id,),
            )
            row = cursor.fetchone()

            if row is None:
                return None

            encrypted_value, iv, expires_str = row

            if expires_str:
                expires_at = datetime.fromisoformat(expires_str)
                if datetime.utcnow() > expires_at:
                    logger.warning(f"Credential {credential_id} has expired")
                    return None

            return self._decrypt(encrypted_value, iv)
        finally:
            conn.close()

    def get_by_service(
        self, service: str, permission: Optional[str] = None
    ) -> Optional[str]:
        """Retrieve credential by service name and optional permission.

        Args:
            service: Service name
            permission: Optional permission level

        Returns:
            Decrypted credential value, or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        try:
            if permission:
                cursor = conn.execute(
                    """
                    SELECT id, encrypted_value, iv, expires_at 
                    FROM credentials 
                    WHERE service = ? AND permission = ?
                """,
                    (service, permission),
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT id, encrypted_value, iv, expires_at 
                    FROM credentials 
                    WHERE service = ? AND (permission IS NULL OR permission = 'default')
                """,
                    (service,),
                )

            row = cursor.fetchone()

            if row is None:
                return None

            cred_id, encrypted_value, iv, expires_str = row

            if expires_str:
                expires_at = datetime.fromisoformat(expires_str)
                if datetime.utcnow() > expires_at:
                    logger.warning(f"Credential {cred_id} has expired")
                    return None

            return self._decrypt(encrypted_value, iv)
        finally:
            conn.close()

    def resolve(self, service: str, permission: Optional[str] = None) -> Optional[str]:
        """Resolve credential with fallback chain.

        Tries: service:permission -> service:default -> None

        Args:
            service: Service name
            permission: Permission level (e.g., 'write')

        Returns:
            Decrypted credential value
        """
        if permission and permission != "default":
            value = self.get_by_service(service, permission)
            if value is not None:
                return value

        return self.get_by_service(service, "default")

    def delete(self, credential_id: str) -> bool:
        """Delete a credential.

        Args:
            credential_id: Credential ID

        Returns:
            True if deleted, False if not found
        """
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute(
                "DELETE FROM credentials WHERE id = ?", (credential_id,)
            )
            conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted credential {credential_id}")
            return deleted
        finally:
            conn.close()

    def list_credentials(self, service: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all credentials (without values).

        Args:
            service: Optional service filter

        Returns:
            List of credential metadata dicts
        """
        import json

        conn = sqlite3.connect(self.db_path)
        try:
            if service:
                cursor = conn.execute(
                    """
                    SELECT id, service, permission, metadata, created_at, updated_at, expires_at
                    FROM credentials WHERE service = ?
                """,
                    (service,),
                )
            else:
                cursor = conn.execute("""
                    SELECT id, service, permission, metadata, created_at, updated_at, expires_at
                    FROM credentials
                """)

            results = []
            for row in cursor.fetchall():
                cred_id, svc, perm, meta_json, created, updated, expires = row
                results.append(
                    {
                        "id": cred_id,
                        "service": svc,
                        "permission": perm,
                        "metadata": json.loads(meta_json) if meta_json else {},
                        "created_at": created,
                        "updated_at": updated,
                        "expires_at": expires,
                    }
                )
            return results
        finally:
            conn.close()

    @staticmethod
    def generate_key() -> str:
        """Generate a new encryption key.

        Returns:
            Hex-encoded 32-byte key
        """
        return os.urandom(32).hex()
