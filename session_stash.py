"""Session-scoped key-value store for MCProxy.

Provides per-session storage with TTL support for caching data across
multiple execute() calls within the same session.
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from logging_config import get_logger

logger = get_logger(__name__)

DEFAULT_SESSION_TTL_SECONDS = 3600
DEFAULT_KEY_TTL_SECONDS = 3600
CLEANUP_INTERVAL_SECONDS = 60


@dataclass
class StashEntry:
    value: Any
    expires_at: Optional[float] = None

    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return time.monotonic() > self.expires_at


class SessionStash:
    def __init__(self, session_id: str, ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS):
        self._session_id = session_id
        self._data: Dict[str, StashEntry] = {}
        self._lock = asyncio.Lock()
        self._created_at = time.monotonic()
        self._expires_at = time.monotonic() + ttl_seconds

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def is_expired(self) -> bool:
        return time.monotonic() > self._expires_at

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            if entry.is_expired():
                del self._data[key]
                logger.debug(
                    f"[STASH] Key '{key}' expired in session {self._session_id}"
                )
                return None
            return entry.value

    async def put(
        self, key: str, value: Any, ttl_seconds: Optional[int] = None
    ) -> None:
        if ttl_seconds is None:
            ttl_seconds = DEFAULT_KEY_TTL_SECONDS

        expires_at = time.monotonic() + ttl_seconds if ttl_seconds > 0 else None

        async with self._lock:
            self._data[key] = StashEntry(value=value, expires_at=expires_at)
            logger.debug(
                f"[STASH] Stored key '{key}' in session {self._session_id} "
                f"(ttl={ttl_seconds}s)"
            )

    async def has(self, key: str) -> bool:
        async with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return False
            if entry.is_expired():
                del self._data[key]
                return False
            return True

    async def delete(self, key: str) -> bool:
        async with self._lock:
            if key in self._data:
                del self._data[key]
                return True
            return False

    async def clear(self) -> None:
        async with self._lock:
            self._data.clear()
            logger.debug(f"[STASH] Cleared session {self._session_id}")

    async def keys(self) -> list[str]:
        async with self._lock:
            valid_keys = []
            expired_keys = []
            for key, entry in self._data.items():
                if entry.is_expired():
                    expired_keys.append(key)
                else:
                    valid_keys.append(key)
            for key in expired_keys:
                del self._data[key]
            return valid_keys

    def _cleanup_expired_sync(self) -> int:
        expired_keys = [k for k, v in self._data.items() if v.is_expired()]
        for key in expired_keys:
            del self._data[key]
        return len(expired_keys)


class SessionManager:
    def __init__(
        self,
        session_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
        cleanup_interval_seconds: int = CLEANUP_INTERVAL_SECONDS,
    ):
        self._sessions: Dict[str, SessionStash] = {}
        self._lock = asyncio.Lock()
        self._session_ttl = session_ttl_seconds
        self._cleanup_interval = cleanup_interval_seconds
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("[SESSION_MANAGER] Started")

    async def stop(self) -> None:
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
        async with self._lock:
            self._sessions.clear()
        logger.info("[SESSION_MANAGER] Stopped")

    async def get_or_create(self, session_id: Optional[str] = None) -> SessionStash:
        if session_id is None:
            session_id = self._generate_session_id()

        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None or session.is_expired:
                session = SessionStash(session_id, ttl_seconds=self._session_ttl)
                self._sessions[session_id] = session
                logger.debug(f"[SESSION_MANAGER] Created new session {session_id}")
            return session

    async def get(self, session_id: str) -> Optional[SessionStash]:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if session.is_expired:
                del self._sessions[session_id]
                return None
            return session

    async def delete(self, session_id: str) -> bool:
        async with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                logger.debug(f"[SESSION_MANAGER] Deleted session {session_id}")
                return True
            return False

    async def clear_all(self) -> None:
        async with self._lock:
            self._sessions.clear()
            logger.info("[SESSION_MANAGER] Cleared all sessions")

    async def get_active_count(self) -> int:
        async with self._lock:
            valid_count = 0
            expired_ids = []
            for sid, session in self._sessions.items():
                if session.is_expired:
                    expired_ids.append(sid)
                else:
                    valid_count += 1
            for sid in expired_ids:
                del self._sessions[sid]
            return valid_count

    def _generate_session_id(self) -> str:
        return f"sess_{uuid.uuid4().hex[:16]}"

    async def _cleanup_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[SESSION_MANAGER] Cleanup error: {e}")

    async def _cleanup_expired(self) -> None:
        async with self._lock:
            expired_ids = [
                sid for sid, session in self._sessions.items() if session.is_expired
            ]
            for sid in expired_ids:
                del self._sessions[sid]
            if expired_ids:
                logger.debug(
                    f"[SESSION_MANAGER] Cleaned up {len(expired_ids)} expired sessions"
                )


session_manager: Optional[SessionManager] = None


def get_session_manager() -> SessionManager:
    global session_manager
    if session_manager is None:
        session_manager = SessionManager()
    return session_manager


async def init_session_manager(
    session_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
    cleanup_interval_seconds: int = CLEANUP_INTERVAL_SECONDS,
) -> SessionManager:
    global session_manager
    session_manager = SessionManager(
        session_ttl_seconds=session_ttl_seconds,
        cleanup_interval_seconds=cleanup_interval_seconds,
    )
    await session_manager.start()
    return session_manager


async def shutdown_session_manager() -> None:
    global session_manager
    if session_manager is not None:
        await session_manager.stop()
        session_manager = None
