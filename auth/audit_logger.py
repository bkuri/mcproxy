"""Audit logging for credential access in MCProxy.

Provides structured JSON logging for authentication and credential access events.
"""

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from logging_config import get_logger

logger = get_logger(__name__)


class AuditEventType(str, Enum):
    CREDENTIAL_ACCESS = "credential_access"
    TOKEN_ISSUED = "token_issued"
    AUTH_FAILURE = "auth_failure"
    SCOPE_DENIED = "scope_denied"


class AuditLogger:
    """Structured audit logger for credential and authentication events."""

    def __init__(
        self,
        log_file: Optional[str] = None,
        use_system_logger: bool = True,
    ):
        """Initialize audit logger.

        Args:
            log_file: Optional path to JSON log file
            use_system_logger: If True, also log via logging_config
        """
        self.log_file = Path(log_file) if log_file else None
        self.use_system_logger = use_system_logger
        self._file_logger: Optional[logging.Logger] = None

        if self.log_file:
            self._setup_file_logger()

    def _setup_file_logger(self) -> None:
        """Set up dedicated file logger for audit events."""
        if not self.log_file:
            return

        self._file_logger = logging.getLogger(f"{__name__}.file")
        self._file_logger.setLevel(logging.INFO)
        self._file_logger.handlers.clear()

        handler = logging.FileHandler(self.log_file)
        handler.setFormatter(logging.Formatter("%(message)s"))
        self._file_logger.addHandler(handler)
        self._file_logger.propagate = False

    def _create_event(
        self,
        event_type: AuditEventType,
        agent_id: Optional[str] = None,
        scope: Optional[str] = None,
        credential_id: Optional[str] = None,
        tool_name: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create structured audit event.

        Args:
            event_type: Type of audit event
            agent_id: Agent identifier
            scope: Scope being accessed
            credential_id: Credential identifier
            tool_name: Tool that triggered access
            success: Whether operation succeeded
            error_message: Error message if failed
            extra: Additional fields

        Returns:
            Structured event dictionary
        """
        event: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type.value,
            "agent_id": agent_id,
            "scope": scope,
            "credential_id": credential_id,
            "tool_name": tool_name,
            "success": success,
            "error_message": error_message,
        }

        if extra:
            event.update(extra)

        event = {k: v for k, v in event.items() if v is not None}

        return event

    def _log_event(self, event: Dict[str, Any]) -> None:
        """Log event to configured outputs.

        Args:
            event: Structured event dictionary
        """
        event_json = json.dumps(event)

        if self._file_logger:
            self._file_logger.info(event_json)

        if self.use_system_logger:
            logger.info(f"AUDIT: {event_json}")

    def log_credential_access(
        self,
        agent_id: str,
        scope: str,
        credential_id: str,
        tool_name: str,
        success: bool,
    ) -> None:
        """Log a credential access event.

        Args:
            agent_id: Agent accessing the credential
            scope: Scope of the credential
            credential_id: ID of credential accessed
            tool_name: Tool that triggered the access
            success: Whether access was successful
        """
        event = self._create_event(
            event_type=AuditEventType.CREDENTIAL_ACCESS,
            agent_id=agent_id,
            scope=scope,
            credential_id=credential_id,
            tool_name=tool_name,
            success=success,
        )
        self._log_event(event)

    def log_token_issued(
        self,
        agent_id: str,
        scopes: List[str],
        client_id: str,
    ) -> None:
        """Log a token issuance event.

        Args:
            agent_id: Agent receiving the token
            scopes: Scopes granted in the token
            client_id: Client ID that authenticated
        """
        event = self._create_event(
            event_type=AuditEventType.TOKEN_ISSUED,
            agent_id=agent_id,
            extra={
                "scopes": scopes,
                "client_id": client_id,
            },
        )
        self._log_event(event)

    def log_auth_failure(
        self,
        client_id: str,
        error: str,
    ) -> None:
        """Log an authentication failure event.

        Args:
            client_id: Client ID that failed authentication
            error: Error message describing the failure
        """
        event = self._create_event(
            event_type=AuditEventType.AUTH_FAILURE,
            success=False,
            error_message=error,
            extra={
                "client_id": client_id,
            },
        )
        self._log_event(event)

    def log_scope_denied(
        self,
        agent_id: str,
        required_scope: str,
        granted_scopes: List[str],
    ) -> None:
        """Log a scope denial event.

        Args:
            agent_id: Agent that was denied scope access
            required_scope: Scope that was required but not granted
            granted_scopes: Scopes that were actually granted
        """
        event = self._create_event(
            event_type=AuditEventType.SCOPE_DENIED,
            agent_id=agent_id,
            success=False,
            extra={
                "required_scope": required_scope,
                "granted_scopes": granted_scopes,
            },
        )
        self._log_event(event)
