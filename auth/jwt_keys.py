"""JWT signing key management for MCProxy.

Implements RSA key pair generation and management for MCProxy
acting as a JWT issuer for agent authentication.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jose import JWTError, jwt

from logging_config import get_logger

logger = get_logger(__name__)


class JWTKeyError(Exception):
    """Error in JWT key operations."""

    pass


class JWTKeyManager:
    """Manages RSA key pairs for JWT signing and verification."""

    def __init__(self, keys_dir: str):
        """Initialize JWT key manager.

        Args:
            keys_dir: Directory to store key files
        """
        self.keys_dir = Path(keys_dir)
        self.keys_dir.mkdir(parents=True, exist_ok=True)
        self.private_key_path = self.keys_dir / "jwt_private.pem"
        self.public_key_path = self.keys_dir / "jwt_public.pem"
        self._private_key: Optional[Any] = None
        self._public_key: Optional[Any] = None

    def generate_key_pair(self, force: bool = False) -> None:
        """Generate a new RSA key pair.

        Args:
            force: If True, overwrite existing keys

        Raises:
            JWTKeyError: If keys exist and force is False
        """
        if self.private_key_path.exists() and not force:
            raise JWTKeyError(
                f"Keys already exist at {self.private_key_path}. "
                "Use force=True to overwrite."
            )

        logger.info("Generating new RSA key pair for JWT signing...")

        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend(),
        )

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )

        self.private_key_path.write_bytes(private_pem)
        self.public_key_path.write_bytes(public_pem)

        self.private_key_path.chmod(0o600)

        self._private_key = private_key
        self._public_key = public_key

        logger.info(
            f"Generated key pair: {self.private_key_path}, {self.public_key_path}"
        )

    def load_private_key(self) -> Any:
        """Load the private key for signing tokens.

        Returns:
            RSA private key object

        Raises:
            JWTKeyError: If key cannot be loaded
        """
        if self._private_key is not None:
            return self._private_key

        if not self.private_key_path.exists():
            raise JWTKeyError(
                f"Private key not found at {self.private_key_path}. "
                "Run generate_key_pair() first."
            )

        try:
            private_pem = self.private_key_path.read_bytes()
            self._private_key = serialization.load_pem_private_key(
                private_pem,
                password=None,
                backend=default_backend(),
            )
            return self._private_key
        except Exception as e:
            raise JWTKeyError(f"Failed to load private key: {e}")

    def load_public_key(self) -> Any:
        """Load the public key for verification.

        Returns:
            RSA public key object

        Raises:
            JWTKeyError: If key cannot be loaded
        """
        if self._public_key is not None:
            return self._public_key

        if not self.public_key_path.exists():
            raise JWTKeyError(
                f"Public key not found at {self.public_key_path}. "
                "Run generate_key_pair() first."
            )

        try:
            public_pem = self.public_key_path.read_bytes()
            self._public_key = serialization.load_pem_public_key(
                public_pem,
                backend=default_backend(),
            )
            return self._public_key
        except Exception as e:
            raise JWTKeyError(f"Failed to load public key: {e}")

    def get_public_key_pem(self) -> str:
        """Get the public key in PEM format.

        Returns:
            PEM-encoded public key string
        """
        public_key = self.load_public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return public_pem.decode("utf-8")

    def ensure_keys(self) -> None:
        """Ensure keys exist, generating if necessary."""
        if not self.private_key_path.exists():
            self.generate_key_pair(force=True)


class JWTIssuer:
    """JWT token issuer for agent authentication."""

    def __init__(
        self,
        key_manager: JWTKeyManager,
        issuer: str = "mcproxy",
        audience: str = "mcproxy",
        default_ttl_hours: int = 1,
        min_ttl_minutes: int = 5,
        max_ttl_hours: int = 24,
    ):
        """Initialize JWT issuer.

        Args:
            key_manager: JWTKeyManager instance
            issuer: Token issuer identifier
            audience: Token audience
            default_ttl_hours: Default token lifetime in hours
            min_ttl_minutes: Minimum allowed TTL in minutes
            max_ttl_hours: Maximum allowed TTL in hours
        """
        self.key_manager = key_manager
        self.issuer = issuer
        self.audience = audience
        self.default_ttl_hours = default_ttl_hours
        self.min_ttl_minutes = min_ttl_minutes
        self.max_ttl_hours = max_ttl_hours

    def issue_token(
        self,
        agent_id: str,
        scopes: str,
        namespace: str,
        ttl_hours: Optional[int] = None,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Issue a JWT for an agent.

        Args:
            agent_id: Agent identifier
            scopes: Space-separated list of scopes
            namespace: Agent's namespace
            ttl_hours: Token lifetime in hours (uses default if None)
            tenant_id: Optional tenant identifier

        Returns:
            Dict with access_token, expires_in, token_type
        """
        if ttl_hours is None:
            ttl_hours = self.default_ttl_hours

        ttl_hours_float: float = max(
            self.min_ttl_minutes / 60, min(ttl_hours, self.max_ttl_hours)
        )

        now = datetime.utcnow()
        exp = now + timedelta(hours=ttl_hours_float)

        claims = {
            "sub": f"agent:{agent_id}",
            "iss": self.issuer,
            "aud": self.audience,
            "exp": exp,
            "iat": now,
            "scope": scopes,
            "agent_id": agent_id,
            "namespace": namespace,
        }

        if tenant_id:
            claims["tenant_id"] = tenant_id

        private_key = self.key_manager.load_private_key()
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

        token = jwt.encode(claims, private_pem.decode("utf-8"), algorithm="RS256")

        return {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": int(ttl_hours_float * 3600),
        }


class JWTValidator:
    """JWT token validator."""

    def __init__(self, key_manager: JWTKeyManager, issuer: str = "mcproxy"):
        """Initialize JWT validator.

        Args:
            key_manager: JWTKeyManager instance
            issuer: Expected token issuer
        """
        self.key_manager = key_manager
        self.issuer = issuer
        self._public_key_pem: Optional[str] = None

    def validate(self, token: str) -> Dict[str, Any]:
        """Validate a JWT and return claims.

        Args:
            token: JWT token string

        Returns:
            Claims dict

        Raises:
            JWTKeyError: If token is invalid
        """
        if self._public_key_pem is None:
            self._public_key_pem = self.key_manager.get_public_key_pem()

        try:
            claims = jwt.decode(
                token,
                self._public_key_pem,
                algorithms=["RS256"],
                issuer=self.issuer,
                audience="mcproxy",
            )
            return claims
        except JWTError as e:
            error_msg = str(e).lower()
            if "expired" in error_msg:
                raise JWTKeyError("Token has expired")
            elif "issuer" in error_msg:
                raise JWTKeyError("Invalid token issuer")
            elif "audience" in error_msg:
                raise JWTKeyError("Invalid token audience")
            elif "signature" in error_msg:
                raise JWTKeyError("Invalid token signature")
            else:
                raise JWTKeyError(f"Token validation failed: {e}")
        except Exception as e:
            raise JWTKeyError(f"Token validation failed: {e}")

    def extract_claims(self, token: str) -> Optional[Dict[str, Any]]:
        """Extract claims from token without full validation.

        Args:
            token: JWT token string

        Returns:
            Claims dict or None if invalid
        """
        try:
            return jwt.get_unverified_claims(token)
        except Exception:
            return None
