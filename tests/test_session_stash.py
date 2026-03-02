"""Tests for session_stash.py - Session-scoped key-value store."""

import asyncio
import time

import pytest

from session_stash import (
    SessionStash,
    SessionManager,
    StashEntry,
    DEFAULT_SESSION_TTL_SECONDS,
    DEFAULT_KEY_TTL_SECONDS,
    CLEANUP_INTERVAL_SECONDS,
    get_session_manager,
    init_session_manager,
    shutdown_session_manager,
)


class TestStashEntry:
    """Tests for StashEntry dataclass."""

    def test_entry_without_ttl(self):
        entry = StashEntry(value="test")
        assert entry.value == "test"
        assert entry.expires_at is None
        assert entry.is_expired() is False

    def test_entry_with_future_ttl(self):
        entry = StashEntry(value="test", expires_at=time.monotonic() + 100)
        assert entry.is_expired() is False

    def test_entry_with_past_ttl(self):
        entry = StashEntry(value="test", expires_at=time.monotonic() - 1)
        assert entry.is_expired() is True


class TestSessionStash:
    """Tests for SessionStash class."""

    @pytest.mark.asyncio
    async def test_put_and_get(self):
        stash = SessionStash("test-session")
        await stash.put("key1", "value1")
        result = await stash.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_get_nonexistent_key(self):
        stash = SessionStash("test-session")
        result = await stash.get("missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_has_key(self):
        stash = SessionStash("test-session")
        await stash.put("key1", "value1")
        assert await stash.has("key1") is True
        assert await stash.has("missing") is False

    @pytest.mark.asyncio
    async def test_delete(self):
        stash = SessionStash("test-session")
        await stash.put("key1", "value1")
        deleted = await stash.delete("key1")
        assert deleted is True
        assert await stash.has("key1") is False

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self):
        stash = SessionStash("test-session")
        deleted = await stash.delete("missing")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_clear(self):
        stash = SessionStash("test-session")
        await stash.put("key1", "value1")
        await stash.put("key2", "value2")
        await stash.clear()
        assert await stash.has("key1") is False
        assert await stash.has("key2") is False

    @pytest.mark.asyncio
    async def test_keys(self):
        stash = SessionStash("test-session")
        await stash.put("key1", "value1")
        await stash.put("key2", "value2")
        keys = await stash.keys()
        assert set(keys) == {"key1", "key2"}

    @pytest.mark.asyncio
    async def test_keys_empty(self):
        stash = SessionStash("test-session")
        keys = await stash.keys()
        assert keys == []

    @pytest.mark.asyncio
    async def test_put_with_ttl(self):
        stash = SessionStash("test-session")
        await stash.put("key1", "value1", ttl_seconds=1)
        assert await stash.has("key1") is True
        await asyncio.sleep(1.1)
        result = await stash.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_put_with_zero_ttl(self):
        stash = SessionStash("test-session")
        await stash.put("key1", "value1", ttl_seconds=0)
        await asyncio.sleep(0.1)
        assert await stash.has("key1") is True

    @pytest.mark.asyncio
    async def test_put_overwrites(self):
        stash = SessionStash("test-session")
        await stash.put("key1", "value1")
        await stash.put("key1", "value2")
        result = await stash.get("key1")
        assert result == "value2"

    @pytest.mark.asyncio
    async def test_complex_value(self):
        stash = SessionStash("test-session")
        complex_value = {
            "list": [1, 2, 3],
            "nested": {"a": "b"},
            "number": 42,
        }
        await stash.put("complex", complex_value)
        result = await stash.get("complex")
        assert result == complex_value

    @pytest.mark.asyncio
    async def test_session_expiry(self):
        stash = SessionStash("test-session", ttl_seconds=1)
        assert stash.is_expired is False
        await asyncio.sleep(1.1)
        assert stash.is_expired is True

    @pytest.mark.asyncio
    async def test_expired_key_removed_on_get(self):
        stash = SessionStash("test-session")
        await stash.put("key1", "value1", ttl_seconds=0.5)
        await asyncio.sleep(0.6)
        result = await stash.get("key1")
        assert result is None
        assert "key1" not in stash._data

    @pytest.mark.asyncio
    async def test_expired_key_removed_on_has(self):
        stash = SessionStash("test-session")
        await stash.put("key1", "value1", ttl_seconds=0.5)
        await asyncio.sleep(0.6)
        exists = await stash.has("key1")
        assert exists is False
        assert "key1" not in stash._data

    @pytest.mark.asyncio
    async def test_expired_key_removed_on_keys(self):
        stash = SessionStash("test-session")
        await stash.put("key1", "value1", ttl_seconds=0.5)
        await stash.put("key2", "value2")
        await asyncio.sleep(0.6)
        keys = await stash.keys()
        assert "key1" not in keys
        assert "key2" in keys


class TestSessionManager:
    """Tests for SessionManager class."""

    @pytest.mark.asyncio
    async def test_get_or_create_new(self):
        manager = SessionManager()
        session = await manager.get_or_create()
        assert session is not None
        assert session.session_id.startswith("sess_")

    @pytest.mark.asyncio
    async def test_get_or_create_with_id(self):
        manager = SessionManager()
        session = await manager.get_or_create("custom-id")
        assert session.session_id == "custom-id"

    @pytest.mark.asyncio
    async def test_get_or_create_returns_same(self):
        manager = SessionManager()
        session1 = await manager.get_or_create("same-id")
        session2 = await manager.get_or_create("same-id")
        assert session1 is session2

    @pytest.mark.asyncio
    async def test_get_existing(self):
        manager = SessionManager()
        await manager.get_or_create("existing-id")
        session = await manager.get("existing-id")
        assert session is not None
        assert session.session_id == "existing-id"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self):
        manager = SessionManager()
        session = await manager.get("nonexistent-id")
        assert session is None

    @pytest.mark.asyncio
    async def test_delete(self):
        manager = SessionManager()
        await manager.get_or_create("to-delete")
        deleted = await manager.delete("to-delete")
        assert deleted is True
        session = await manager.get("to-delete")
        assert session is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self):
        manager = SessionManager()
        deleted = await manager.delete("nonexistent")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_clear_all(self):
        manager = SessionManager()
        await manager.get_or_create("session1")
        await manager.get_or_create("session2")
        await manager.clear_all()
        assert await manager.get("session1") is None
        assert await manager.get("session2") is None

    @pytest.mark.asyncio
    async def test_get_active_count(self):
        manager = SessionManager()
        await manager.get_or_create("session1")
        await manager.get_or_create("session2")
        count = await manager.get_active_count()
        assert count == 2

    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        manager = SessionManager()
        await manager.start()
        assert manager._running is True
        assert manager._cleanup_task is not None
        await manager.stop()
        assert manager._running is False
        assert manager._cleanup_task is None

    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions(self):
        manager = SessionManager(session_ttl_seconds=1)
        await manager.start()

        session = await manager.get_or_create("expiring")
        await session.put("key", "value")

        await asyncio.sleep(1.5)

        result = await manager.get("expiring")
        assert result is None

        await manager.stop()

    @pytest.mark.asyncio
    async def test_generate_session_id(self):
        manager = SessionManager()
        id1 = manager._generate_session_id()
        id2 = manager._generate_session_id()
        assert id1 != id2
        assert id1.startswith("sess_")
        assert len(id1) == 21


class TestSessionIsolation:
    """Tests for session isolation between sessions."""

    @pytest.mark.asyncio
    async def test_different_sessions_isolated(self):
        manager = SessionManager()
        session1 = await manager.get_or_create("session1")
        session2 = await manager.get_or_create("session2")

        await session1.put("key", "value1")
        await session2.put("key", "value2")

        assert await session1.get("key") == "value1"
        assert await session2.get("key") == "value2"

    @pytest.mark.asyncio
    async def test_clear_isolated(self):
        manager = SessionManager()
        session1 = await manager.get_or_create("session1")
        session2 = await manager.get_or_create("session2")

        await session1.put("key1", "value1")
        await session2.put("key2", "value2")

        await session1.clear()

        assert await session1.has("key1") is False
        assert await session2.has("key2") is True

    @pytest.mark.asyncio
    async def test_delete_session_isolated(self):
        manager = SessionManager()
        session1 = await manager.get_or_create("session1")
        session2 = await manager.get_or_create("session2")

        await session1.put("key", "value")
        await manager.delete("session1")

        session1_new = await manager.get_or_create("session1")
        assert await session1_new.get("key") is None
        assert await session2.get("key") is None


class TestGlobalFunctions:
    """Tests for global session manager functions."""

    @pytest.mark.asyncio
    async def test_get_session_manager_singleton(self):
        import session_stash

        session_stash.session_manager = None

        manager1 = get_session_manager()
        manager2 = get_session_manager()
        assert manager1 is manager2

        session_stash.session_manager = None

    @pytest.mark.asyncio
    async def test_init_and_shutdown(self):
        import session_stash

        session_stash.session_manager = None

        manager = await init_session_manager()
        assert manager is not None
        assert manager._running is True

        await shutdown_session_manager()
        assert session_stash.session_manager is None


class TestConcurrency:
    """Tests for concurrent access to session stash."""

    @pytest.mark.asyncio
    async def test_concurrent_puts(self):
        stash = SessionStash("test-session")

        async def put_value(i):
            await stash.put(f"key{i}", f"value{i}")

        await asyncio.gather(*[put_value(i) for i in range(100)])

        keys = await stash.keys()
        assert len(keys) == 100

    @pytest.mark.asyncio
    async def test_concurrent_gets(self):
        stash = SessionStash("test-session")
        await stash.put("key", "value")

        async def get_value():
            return await stash.get("key")

        results = await asyncio.gather(*[get_value() for _ in range(100)])
        assert all(r == "value" for r in results)

    @pytest.mark.asyncio
    async def test_concurrent_put_and_get(self):
        stash = SessionStash("test-session")

        async def putter():
            for i in range(10):
                await stash.put("key", i)

        async def getter():
            for _ in range(10):
                await stash.get("key")

        await asyncio.gather(putter(), getter())
