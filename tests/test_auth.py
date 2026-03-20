"""Tests for auth module - CredentialStore, AgentRegistry, JWT, and OAuth."""

import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import pytest

from auth import (
    Agent,
    AgentRegistry,
    AgentRegistryError,
    AuthContext,
    Credential,
    CredentialError,
    CredentialStore,
    JWTIssuer,
    JWTKeyError,
    JWTKeyManager,
    JWTValidator,
    OAuthError,
    OAuthHandler,
)


@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def encryption_key():
    return os.urandom(32)


@pytest.fixture
def credential_store(temp_dir, encryption_key):
    db_path = temp_dir / "credentials.db"
    return CredentialStore(str(db_path), encryption_key=encryption_key)


@pytest.fixture
def agent_registry(temp_dir):
    db_path = temp_dir / "agents.db"
    return AgentRegistry(str(db_path))


@pytest.fixture
def jwt_keys_dir(temp_dir):
    return temp_dir / "jwt_keys"


@pytest.fixture
def jwt_key_manager(jwt_keys_dir):
    manager = JWTKeyManager(str(jwt_keys_dir))
    manager.generate_key_pair(force=True)
    return manager


@pytest.fixture
def jwt_issuer(jwt_key_manager):
    return JWTIssuer(jwt_key_manager)


@pytest.fixture
def jwt_validator(jwt_key_manager):
    return JWTValidator(jwt_key_manager)


@pytest.fixture
def oauth_handler(agent_registry, jwt_issuer, jwt_validator):
    return OAuthHandler(agent_registry, jwt_issuer, jwt_validator)


@pytest.fixture
def registered_agent(agent_registry):
    return agent_registry.register(
        agent_id="test-agent-1",
        name="Test Agent",
        allowed_scopes=["github:read", "perplexity:search"],
        namespace="test-ns",
    )


class TestCredentialStoreInit:
    def test_init_with_encryption_key(self, temp_dir, encryption_key):
        db_path = temp_dir / "creds.db"
        store = CredentialStore(str(db_path), encryption_key=encryption_key)
        assert store.db_path == db_path
        assert store.key == encryption_key

    def test_init_with_env_var(self, temp_dir, encryption_key, monkeypatch):
        monkeypatch.setenv("MCPROXY_CREDENTIAL_KEY", encryption_key.hex())
        db_path = temp_dir / "creds.db"
        store = CredentialStore(str(db_path))
        assert store.key == encryption_key

    def test_init_missing_key_raises(self, temp_dir, monkeypatch):
        monkeypatch.delenv("MCPROXY_CREDENTIAL_KEY", raising=False)
        db_path = temp_dir / "creds.db"
        with pytest.raises(CredentialError, match="Encryption key not provided"):
            CredentialStore(str(db_path))

    def test_init_invalid_key_format(self, temp_dir, monkeypatch):
        monkeypatch.setenv("MCPROXY_CREDENTIAL_KEY", "not-hex")
        db_path = temp_dir / "creds.db"
        with pytest.raises(CredentialError, match="Invalid encryption key format"):
            CredentialStore(str(db_path))

    def test_init_wrong_key_length(self, temp_dir):
        db_path = temp_dir / "creds.db"
        with pytest.raises(CredentialError, match="must be 32 bytes"):
            CredentialStore(str(db_path), encryption_key=b"short")

    def test_generate_key(self):
        key = CredentialStore.generate_key()
        assert len(bytes.fromhex(key)) == 32


class TestCredentialStoreCRUD:
    def test_store_and_retrieve(self, credential_store):
        cred_id = credential_store.store(
            service="github",
            value="ghp_test123",
        )
        assert cred_id is not None

        value = credential_store.get(cred_id)
        assert value == "ghp_test123"

    def test_store_with_all_options(self, credential_store):
        cred_id = credential_store.store(
            service="perplexity",
            value="pplx_test456",
            credential_id="custom-id-123",
            permission="write",
            metadata={"owner": "test-user"},
            expires_at=datetime.utcnow() + timedelta(days=30),
        )
        assert cred_id == "custom-id-123"

        value = credential_store.get(cred_id)
        assert value == "pplx_test456"

    def test_get_nonexistent_returns_none(self, credential_store):
        value = credential_store.get("nonexistent-id")
        assert value is None

    def test_get_expired_returns_none(self, credential_store):
        cred_id = credential_store.store(
            service="temp",
            value="temp_value",
            expires_at=datetime.utcnow() - timedelta(hours=1),
        )
        value = credential_store.get(cred_id)
        assert value is None

    def test_delete_existing(self, credential_store):
        cred_id = credential_store.store(service="test", value="value")
        deleted = credential_store.delete(cred_id)
        assert deleted is True
        assert credential_store.get(cred_id) is None

    def test_delete_nonexistent(self, credential_store):
        deleted = credential_store.delete("nonexistent")
        assert deleted is False


class TestCredentialStoreEncryption:
    def test_encrypt_decrypt_roundtrip(self, credential_store):
        plaintext = "super_secret_api_key_123"
        cred_id = credential_store.store(service="test", value=plaintext)
        decrypted = credential_store.get(cred_id)
        assert decrypted == plaintext

    def test_different_iv_each_time(self, credential_store):
        import sqlite3

        cred_id1 = credential_store.store(service="s1", value="value1")
        cred_id2 = credential_store.store(service="s2", value="value1")

        conn = sqlite3.connect(credential_store.db_path)
        try:
            cursor = conn.execute(
                "SELECT iv FROM credentials WHERE id = ?", (cred_id1,)
            )
            iv1 = cursor.fetchone()[0]
            cursor = conn.execute(
                "SELECT iv FROM credentials WHERE id = ?", (cred_id2,)
            )
            iv2 = cursor.fetchone()[0]
            assert iv1 != iv2
        finally:
            conn.close()

    def test_decrypt_with_wrong_key_fails(self, temp_dir, credential_store):
        cred_id = credential_store.store(service="test", value="secret")

        wrong_key = os.urandom(32)
        wrong_store = CredentialStore(
            str(temp_dir / "creds.db"), encryption_key=wrong_key
        )
        with pytest.raises(CredentialError, match="Decryption failed"):
            wrong_store.get(cred_id)


class TestCredentialStoreResolve:
    def test_resolve_with_permission(self, credential_store):
        credential_store.store(
            service="github", value="default_key", permission="default"
        )
        credential_store.store(service="github", value="write_key", permission="write")

        value = credential_store.resolve("github", "write")
        assert value == "write_key"

    def test_resolve_fallback_to_default(self, credential_store):
        credential_store.store(
            service="github", value="default_key", permission="default"
        )

        value = credential_store.resolve("github", "admin")
        assert value == "default_key"

    def test_resolve_without_permission(self, credential_store):
        credential_store.store(service="perplexity", value="key123")

        value = credential_store.resolve("perplexity")
        assert value == "key123"

    def test_resolve_nonexistent_returns_none(self, credential_store):
        value = credential_store.resolve("nonexistent", "read")
        assert value is None


class TestCredentialStoreList:
    def test_list_all_credentials(self, credential_store):
        credential_store.store(service="github", value="key1")
        credential_store.store(service="perplexity", value="key2")
        credential_store.store(service="openai", value="key3")

        creds = credential_store.list_credentials()
        assert len(creds) == 3
        services = [c["service"] for c in creds]
        assert "github" in services
        assert "perplexity" in services
        assert "openai" in services

    def test_list_filter_by_service(self, credential_store):
        credential_store.store(service="github", value="key1", permission="read")
        credential_store.store(service="github", value="key2", permission="write")
        credential_store.store(service="perplexity", value="key3")

        creds = credential_store.list_credentials(service="github")
        assert len(creds) == 2
        assert all(c["service"] == "github" for c in creds)

    def test_list_excludes_values(self, credential_store):
        credential_store.store(service="secret", value="super_secret_value")
        creds = credential_store.list_credentials()
        assert "value" not in creds[0]
        assert "encrypted_value" not in creds[0]


class TestAgentRegistryInit:
    def test_init_creates_database(self, temp_dir):
        db_path = temp_dir / "agents.db"
        AgentRegistry(str(db_path))
        assert db_path.exists()

    def test_init_creates_tables(self, agent_registry):
        import sqlite3

        conn = sqlite3.connect(agent_registry.db_path)
        try:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='agents'"
            )
            assert cursor.fetchone() is not None
        finally:
            conn.close()


class TestAgentRegistryRegister:
    def test_register_returns_credentials(self, agent_registry):
        result = agent_registry.register(
            agent_id="agent-1", name="Test Agent", allowed_scopes=["read", "write"]
        )

        assert "agent_id" in result
        assert "client_id" in result
        assert "client_secret" in result
        assert result["agent_id"] == "agent-1"
        assert result["client_id"].startswith("agent_")

    def test_register_generates_uuid_if_not_provided(self, agent_registry):
        result = agent_registry.register(name="Auto ID Agent")
        assert len(result["agent_id"]) == 36

    def test_register_with_namespace_and_tenant(self, agent_registry):
        result = agent_registry.register(
            agent_id="tenant-agent",
            namespace="tenant-ns",
            tenant_id="tenant-123",
        )
        agent = agent_registry.get_agent("tenant-agent")
        assert agent.namespace == "tenant-ns"
        assert agent.tenant_id == "tenant-123"

    def test_register_with_metadata(self, agent_registry):
        result = agent_registry.register(
            agent_id="meta-agent",
            metadata={"env": "prod", "owner": "team-a"},
        )
        agent = agent_registry.get_agent("meta-agent")
        assert agent.metadata["env"] == "prod"
        assert agent.metadata["owner"] == "team-a"


class TestAgentRegistryAuthenticate:
    def test_authenticate_valid_credentials(self, agent_registry):
        reg_result = agent_registry.register(
            agent_id="auth-test",
            allowed_scopes=["scope1", "scope2"],
            namespace="test-ns",
        )

        agent = agent_registry.authenticate(
            reg_result["client_id"], reg_result["client_secret"]
        )

        assert agent is not None
        assert agent.agent_id == "auth-test"
        assert agent.namespace == "test-ns"
        assert "scope1" in agent.allowed_scopes
        assert "scope2" in agent.allowed_scopes
        assert agent.enabled is True

    def test_authenticate_invalid_client_id(self, agent_registry):
        agent = agent_registry.authenticate("nonexistent_client", "any_secret")
        assert agent is None

    def test_authenticate_invalid_secret(self, agent_registry):
        reg_result = agent_registry.register(agent_id="wrong-secret-test")
        agent = agent_registry.authenticate(reg_result["client_id"], "wrong_secret")
        assert agent is None

    def test_authenticate_disabled_agent(self, agent_registry):
        reg_result = agent_registry.register(agent_id="disabled-test")
        agent_registry.disable("disabled-test")

        agent = agent_registry.authenticate(
            reg_result["client_id"], reg_result["client_secret"]
        )
        assert agent is None


class TestAgentRegistryUpdateScopes:
    def test_update_scopes(self, agent_registry):
        agent_registry.register(agent_id="scope-test", allowed_scopes=["read"])
        updated = agent_registry.update_scopes("scope-test", ["read", "write", "admin"])
        assert updated is True

        agent = agent_registry.get_agent("scope-test")
        assert agent.allowed_scopes == {"read", "write", "admin"}

    def test_update_scopes_nonexistent(self, agent_registry):
        updated = agent_registry.update_scopes("nonexistent", ["read"])
        assert updated is False


class TestAgentRegistryRotateSecret:
    def test_rotate_secret(self, agent_registry):
        reg_result = agent_registry.register(agent_id="rotate-test")

        new_creds = agent_registry.rotate_secret("rotate-test")
        assert new_creds is not None
        assert "client_id" in new_creds
        assert "client_secret" in new_creds
        assert new_creds["client_id"] != reg_result["client_id"]

        agent = agent_registry.authenticate(
            new_creds["client_id"], new_creds["client_secret"]
        )
        assert agent is not None
        assert agent.agent_id == "rotate-test"

    def test_rotate_secret_invalidates_old(self, agent_registry):
        reg_result = agent_registry.register(agent_id="rotate-invalidate-test")
        agent_registry.rotate_secret("rotate-invalidate-test")

        agent = agent_registry.authenticate(
            reg_result["client_id"], reg_result["client_secret"]
        )
        assert agent is None

    def test_rotate_secret_nonexistent(self, agent_registry):
        result = agent_registry.rotate_secret("nonexistent")
        assert result is None


class TestAgentRegistryDisableEnable:
    def test_disable_agent(self, agent_registry):
        agent_registry.register(agent_id="disable-test")
        disabled = agent_registry.disable("disable-test")
        assert disabled is True

        agent = agent_registry.get_agent("disable-test")
        assert agent.enabled is False

    def test_enable_agent(self, agent_registry):
        agent_registry.register(agent_id="enable-test")
        agent_registry.disable("enable-test")
        enabled = agent_registry.enable("enable-test")
        assert enabled is True

        agent = agent_registry.get_agent("enable-test")
        assert agent.enabled is True

    def test_disable_nonexistent(self, agent_registry):
        disabled = agent_registry.disable("nonexistent")
        assert disabled is False

    def test_enable_nonexistent(self, agent_registry):
        enabled = agent_registry.enable("nonexistent")
        assert enabled is False


class TestAgentRegistryDelete:
    def test_delete_agent(self, agent_registry):
        agent_registry.register(agent_id="delete-test")
        deleted = agent_registry.delete("delete-test")
        assert deleted is True
        assert agent_registry.get_agent("delete-test") is None

    def test_delete_nonexistent(self, agent_registry):
        deleted = agent_registry.delete("nonexistent")
        assert deleted is False


class TestAgentRegistryList:
    def test_list_all_agents(self, agent_registry):
        agent_registry.register(agent_id="list-1", namespace="ns1")
        agent_registry.register(agent_id="list-2", namespace="ns2")
        agent_registry.register(agent_id="list-3", namespace="ns1")

        agents = agent_registry.list_agents(enabled_only=False)
        assert len(agents) >= 3

    def test_list_filter_by_namespace(self, agent_registry):
        agent_registry.register(agent_id="ns-test-1", namespace="namespace-a")
        agent_registry.register(agent_id="ns-test-2", namespace="namespace-b")
        agent_registry.register(agent_id="ns-test-3", namespace="namespace-a")

        agents = agent_registry.list_agents(namespace="namespace-a", enabled_only=False)
        assert all(a["namespace"] == "namespace-a" for a in agents)

    def test_list_enabled_only(self, agent_registry):
        agent_registry.register(agent_id="enabled-only-1")
        agent_registry.register(agent_id="enabled-only-2")
        agent_registry.register(agent_id="enabled-only-3")
        agent_registry.disable("enabled-only-3")

        agents = agent_registry.list_agents(enabled_only=True)
        assert all(a["enabled"] is True for a in agents)


class TestJWTKeyManagerGenerate:
    def test_generate_key_pair(self, jwt_keys_dir):
        manager = JWTKeyManager(str(jwt_keys_dir))
        manager.generate_key_pair()

        private_path = jwt_keys_dir / "jwt_private.pem"
        public_path = jwt_keys_dir / "jwt_public.pem"

        assert private_path.exists()
        assert public_path.exists()

    def test_generate_key_pair_force_overwrites(self, jwt_key_manager, jwt_keys_dir):
        original_private = (jwt_keys_dir / "jwt_private.pem").read_bytes()

        jwt_key_manager.generate_key_pair(force=True)

        new_private = (jwt_keys_dir / "jwt_private.pem").read_bytes()
        assert new_private != original_private

    def test_generate_key_pair_no_force_raises(self, jwt_key_manager):
        with pytest.raises(JWTKeyError, match="Keys already exist"):
            jwt_key_manager.generate_key_pair(force=False)

    def test_private_key_permissions(self, jwt_keys_dir):
        manager = JWTKeyManager(str(jwt_keys_dir))
        manager.generate_key_pair()

        private_path = jwt_keys_dir / "jwt_private.pem"
        mode = private_path.stat().st_mode & 0o777
        assert mode == 0o600


class TestJWTKeyManagerLoad:
    def test_load_private_key(self, jwt_key_manager):
        key = jwt_key_manager.load_private_key()
        assert key is not None

    def test_load_public_key(self, jwt_key_manager):
        key = jwt_key_manager.load_public_key()
        assert key is not None

    def test_load_private_key_caches(self, jwt_key_manager):
        key1 = jwt_key_manager.load_private_key()
        key2 = jwt_key_manager.load_private_key()
        assert key1 is key2

    def test_load_missing_private_key_raises(self, jwt_keys_dir):
        manager = JWTKeyManager(str(jwt_keys_dir))
        with pytest.raises(JWTKeyError, match="Private key not found"):
            manager.load_private_key()

    def test_load_missing_public_key_raises(self, jwt_keys_dir):
        manager = JWTKeyManager(str(jwt_keys_dir))
        with pytest.raises(JWTKeyError, match="Public key not found"):
            manager.load_public_key()

    def test_get_public_key_pem(self, jwt_key_manager):
        pem = jwt_key_manager.get_public_key_pem()
        assert "-----BEGIN PUBLIC KEY-----" in pem
        assert "-----END PUBLIC KEY-----" in pem

    def test_ensure_keys_generates_if_missing(self, jwt_keys_dir):
        manager = JWTKeyManager(str(jwt_keys_dir))
        manager.ensure_keys()
        assert (jwt_keys_dir / "jwt_private.pem").exists()
        assert (jwt_keys_dir / "jwt_public.pem").exists()


class TestJWTIssuer:
    def test_issue_token(self, jwt_issuer):
        result = jwt_issuer.issue_token(
            agent_id="test-agent",
            scopes="read write",
            namespace="test-ns",
        )

        assert "access_token" in result
        assert "token_type" in result
        assert "expires_in" in result
        assert result["token_type"] == "Bearer"
        assert result["expires_in"] == 3600

    def test_issue_token_with_ttl(self, jwt_issuer):
        result = jwt_issuer.issue_token(
            agent_id="test-agent",
            scopes="read",
            namespace="test-ns",
            ttl_hours=4,
        )
        assert result["expires_in"] == 4 * 3600

    def test_issue_token_with_tenant(self, jwt_issuer):
        result = jwt_issuer.issue_token(
            agent_id="tenant-agent",
            scopes="read",
            namespace="tenant-ns",
            tenant_id="tenant-123",
        )
        assert "access_token" in result

    def test_issue_token_clamps_ttl(self, jwt_issuer):
        result = jwt_issuer.issue_token(
            agent_id="clamp-test",
            scopes="read",
            namespace="test-ns",
            ttl_hours=100,
        )
        assert result["expires_in"] == 24 * 3600

    def test_issue_token_clamps_min_ttl(self, jwt_key_manager):
        issuer = JWTIssuer(jwt_key_manager, min_ttl_minutes=30)
        result = issuer.issue_token(
            agent_id="min-ttl-test",
            scopes="read",
            namespace="test-ns",
            ttl_hours=0,
        )
        assert result["expires_in"] == 30 * 60


class TestJWTValidator:
    def test_validate_valid_token(self, jwt_issuer, jwt_validator):
        token_response = jwt_issuer.issue_token(
            agent_id="validate-test",
            scopes="read write",
            namespace="validate-ns",
        )

        claims = jwt_validator.validate(token_response["access_token"])

        assert claims["agent_id"] == "validate-test"
        assert claims["namespace"] == "validate-ns"
        assert "read" in claims["scope"]

    def test_validate_expired_token(self, jwt_key_manager):
        issuer = JWTIssuer(jwt_key_manager)
        validator = JWTValidator(jwt_key_manager)

        with patch("auth.jwt_keys.datetime") as mock_dt:
            mock_dt.utcnow.return_value = datetime.utcnow() - timedelta(hours=2)
            token_response = issuer.issue_token(
                agent_id="expired-test",
                scopes="read",
                namespace="test-ns",
                ttl_hours=1,
            )

        with pytest.raises(JWTKeyError, match="expired"):
            validator.validate(token_response["access_token"])

    def test_validate_invalid_signature(self, jwt_validator, temp_dir):
        other_keys_dir = temp_dir / "other_keys"
        other_manager = JWTKeyManager(str(other_keys_dir))
        other_manager.generate_key_pair(force=True)
        other_issuer = JWTIssuer(other_manager)

        token_response = other_issuer.issue_token(
            agent_id="wrong-sig",
            scopes="read",
            namespace="test-ns",
        )

        with pytest.raises(JWTKeyError, match="signature"):
            jwt_validator.validate(token_response["access_token"])

    def test_validate_wrong_issuer(self, jwt_key_manager):
        issuer = JWTIssuer(jwt_key_manager, issuer="wrong-issuer")
        validator = JWTValidator(jwt_key_manager, issuer="mcproxy")

        token_response = issuer.issue_token(
            agent_id="wrong-issuer-test",
            scopes="read",
            namespace="test-ns",
        )

        with pytest.raises(JWTKeyError, match="issuer"):
            validator.validate(token_response["access_token"])

    def test_extract_claims_without_validation(self, jwt_issuer, jwt_validator):
        token_response = jwt_issuer.issue_token(
            agent_id="extract-test",
            scopes="read",
            namespace="test-ns",
        )

        claims = jwt_validator.extract_claims(token_response["access_token"])
        assert claims is not None
        assert claims["agent_id"] == "extract-test"

    def test_extract_claims_invalid_token(self, jwt_validator):
        claims = jwt_validator.extract_claims("not.a.valid.token")
        assert claims is None


class TestOAuthHandlerTokenRequest:
    @pytest.mark.asyncio
    async def test_successful_token_request(self, oauth_handler, registered_agent):
        response = await oauth_handler.handle_token_request(
            grant_type="client_credentials",
            client_id=registered_agent["client_id"],
            client_secret=registered_agent["client_secret"],
        )

        assert "access_token" in response
        assert response["token_type"] == "Bearer"
        assert "expires_in" in response

    @pytest.mark.asyncio
    async def test_invalid_grant_type(self, oauth_handler, registered_agent):
        with pytest.raises(OAuthError, match="unsupported_grant_type"):
            await oauth_handler.handle_token_request(
                grant_type="password",
                client_id=registered_agent["client_id"],
                client_secret=registered_agent["client_secret"],
            )

    @pytest.mark.asyncio
    async def test_invalid_client_credentials(self, oauth_handler):
        with pytest.raises(OAuthError, match="invalid_client"):
            await oauth_handler.handle_token_request(
                grant_type="client_credentials",
                client_id="invalid_client",
                client_secret="invalid_secret",
            )

    @pytest.mark.asyncio
    async def test_disabled_agent_rejected(self, oauth_handler, agent_registry):
        reg = agent_registry.register(agent_id="disabled-oauth-test")
        agent_registry.disable("disabled-oauth-test")

        with pytest.raises(OAuthError, match="invalid_client"):
            await oauth_handler.handle_token_request(
                grant_type="client_credentials",
                client_id=reg["client_id"],
                client_secret=reg["client_secret"],
            )


class TestOAuthHandlerScopeFiltering:
    @pytest.mark.asyncio
    async def test_scope_filtering_grants_allowed(self, oauth_handler, agent_registry):
        reg = agent_registry.register(
            agent_id="scope-filter-test",
            allowed_scopes=["github:read", "perplexity:search"],
        )

        response = await oauth_handler.handle_token_request(
            grant_type="client_credentials",
            client_id=reg["client_id"],
            client_secret=reg["client_secret"],
            scope="github:read perplexity:search",
        )

        assert "access_token" in response

    @pytest.mark.asyncio
    async def test_scope_filtering_rejects_unallowed(
        self, oauth_handler, agent_registry
    ):
        reg = agent_registry.register(
            agent_id="scope-reject-test",
            allowed_scopes=["github:read"],
        )

        with pytest.raises(OAuthError, match="invalid_scope"):
            await oauth_handler.handle_token_request(
                grant_type="client_credentials",
                client_id=reg["client_id"],
                client_secret=reg["client_secret"],
                scope="admin:full",
            )

    @pytest.mark.asyncio
    async def test_scope_filtering_wildcard(self, oauth_handler, agent_registry):
        reg = agent_registry.register(
            agent_id="wildcard-test",
            allowed_scopes=["github:*"],
        )

        response = await oauth_handler.handle_token_request(
            grant_type="client_credentials",
            client_id=reg["client_id"],
            client_secret=reg["client_secret"],
            scope="github:read github:write",
        )

        assert "access_token" in response

    @pytest.mark.asyncio
    async def test_scope_filtering_no_requested_uses_all(
        self, oauth_handler, agent_registry
    ):
        reg = agent_registry.register(
            agent_id="no-scope-request-test",
            allowed_scopes=["github:read", "perplexity:search"],
        )

        response = await oauth_handler.handle_token_request(
            grant_type="client_credentials",
            client_id=reg["client_id"],
            client_secret=reg["client_secret"],
        )

        assert "access_token" in response


class TestOAuthHandlerValidateToken:
    def test_validate_token(self, oauth_handler, jwt_issuer):
        token_response = jwt_issuer.issue_token(
            agent_id="validate-ctx-test",
            scopes="read write",
            namespace="ctx-ns",
            tenant_id="tenant-456",
        )

        ctx = oauth_handler.validate_token(token_response["access_token"])

        assert isinstance(ctx, AuthContext)
        assert ctx.agent_id == "validate-ctx-test"
        assert ctx.namespace == "ctx-ns"
        assert ctx.tenant_id == "tenant-456"
        assert "read" in ctx.scopes
        assert "write" in ctx.scopes

    def test_validate_token_invalid_raises_401(self, oauth_handler):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            oauth_handler.validate_token("invalid.token.here")

        assert exc_info.value.status_code == 401


class TestAuthContext:
    def test_auth_context_creation(self):
        ctx = AuthContext(
            agent_id="agent-123",
            scopes=["read", "write"],
            namespace="test-ns",
            tenant_id="tenant-456",
        )

        assert ctx.agent_id == "agent-123"
        assert ctx.scopes == ["read", "write"]
        assert ctx.namespace == "test-ns"
        assert ctx.tenant_id == "tenant-456"

    def test_auth_context_without_tenant(self):
        ctx = AuthContext(
            agent_id="agent-789",
            scopes=["read"],
            namespace="default",
        )

        assert ctx.tenant_id is None


class TestAgentDataclass:
    def test_agent_creation(self):
        agent = Agent(
            agent_id="test-id",
            client_id="agent_abc123",
            client_secret_hash="hashed_secret",
            allowed_scopes={"read", "write"},
            namespace="test-ns",
            tenant_id=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            enabled=True,
            metadata={"key": "value"},
        )

        assert agent.agent_id == "test-id"
        assert agent.enabled is True
        assert "read" in agent.allowed_scopes
