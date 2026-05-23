"""Tests for db.models — SQLAlchemy ORM models."""


import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Agent, Credential, Environment, Secret, Session, Vault


class TestAgentModel:
    @pytest.mark.asyncio
    async def test_create_agent(self, session: AsyncSession):
        agent = Agent(
            name="test-agent",
            system_prompt="You are helpful.",
        )
        session.add(agent)
        await session.flush()

        assert agent.id is not None
        assert agent.name == "test-agent"
        assert agent.version == 1
        assert agent.created_at is not None
        assert agent.archived_at is None

    @pytest.mark.asyncio
    async def test_agent_jsonb_defaults(self, session: AsyncSession):
        agent = Agent(name="t")
        session.add(agent)
        await session.flush()

        assert agent.tools == []
        assert agent.mcp_servers == []
        assert agent.metadata_ == {}

    def test_agent_tools_field_is_list(self):
        """Type annotation for tools/mcp_servers should be list, not dict."""
        agent = Agent(name="t", tools=["a"], mcp_servers=["b"])
        assert isinstance(agent.tools, list)
        assert isinstance(agent.mcp_servers, list)

    @pytest.mark.asyncio
    async def test_agent_unique_id(self, session: AsyncSession):
        a1 = Agent(name="a1")
        a2 = Agent(name="a2")
        session.add_all([a1, a2])
        await session.flush()
        assert a1.id != a2.id


class TestEnvironmentModel:
    @pytest.mark.asyncio
    async def test_create_environment(self, session: AsyncSession):
        env = Environment(name="python-dev")
        session.add(env)
        await session.flush()
        assert env.id is not None
        assert env.name == "python-dev"

    @pytest.mark.asyncio
    async def test_environment_name_unique(self, session: AsyncSession):
        """Environment name uniqueness is enforced at route level, not DB level.
        The DB allows duplicate names (for archive-re-add workflow).
        Route-level tests verify the API rejects duplicates."""
        e1 = Environment(name="unique-env")
        e2 = Environment(name="unique-env")
        session.add_all([e1, e2])
        await session.flush()
        assert e1.id != e2.id


class TestSessionModel:
    @pytest.mark.asyncio
    async def test_create_session(self, session: AsyncSession):
        agent = Agent(name="sa")
        session.add(agent)
        await session.flush()

        sess = Session(agent_id=agent.id, title="test session")
        session.add(sess)
        await session.flush()

        assert sess.id is not None
        assert sess.status == "idle"
        assert sess.aegra_thread_id is None

    @pytest.mark.asyncio
    async def test_session_agent_relationship(self, session: AsyncSession):
        agent = Agent(name="rel-agent")
        session.add(agent)
        await session.flush()

        sess = Session(agent_id=agent.id)
        session.add(sess)
        await session.flush()

        await session.refresh(sess, ["agent"])
        assert sess.agent is not None
        assert sess.agent.name == "rel-agent"


class TestVaultModel:
    @pytest.mark.asyncio
    async def test_create_vault(self, session: AsyncSession):
        vault = Vault(display_name="my-vault")
        session.add(vault)
        await session.flush()
        assert vault.id is not None

    @pytest.mark.asyncio
    async def test_vault_cascade_delete(self, session: AsyncSession):
        vault = Vault(display_name="cascade-test")
        session.add(vault)
        await session.flush()

        cred = Credential(
            vault_id=vault.id,
            display_name="c",
            mcp_server_url="http://mcp.example.com",
            auth_type="static_bearer",
            encrypted_token=b"encrypted",
        )
        session.add(cred)
        await session.flush()

        await session.delete(vault)
        await session.flush()

        result = await session.execute(
            select(Credential).where(Credential.vault_id == vault.id)
        )
        assert result.scalar_one_or_none() is None


class TestCredentialModel:
    @pytest.mark.asyncio
    async def test_create_credential(self, session: AsyncSession):
        vault = Vault(display_name="cv")
        session.add(vault)
        await session.flush()

        cred = Credential(
            vault_id=vault.id,
            display_name="test cred",
            mcp_server_url="http://mcp.example.com",
            auth_type="static_bearer",
            encrypted_token=b"\x00\x01\x02",
        )
        session.add(cred)
        await session.flush()
        assert cred.id is not None

    @pytest.mark.asyncio
    async def test_credential_unique_per_vault_url(self, session: AsyncSession):
        """Credential URL uniqueness is enforced at route level, not DB level.
        The DB allows duplicate URLs (for archive-re-add workflow).
        Route-level tests verify the API rejects duplicates."""
        vault = Vault(display_name="uq")
        session.add(vault)
        await session.flush()

        c1 = Credential(
            vault_id=vault.id,
            display_name="c1",
            mcp_server_url="http://same.com",
            auth_type="static_bearer",
            encrypted_token=b"a",
        )
        c2 = Credential(
            vault_id=vault.id,
            display_name="c2",
            mcp_server_url="http://same.com",
            auth_type="static_bearer",
            encrypted_token=b"b",
        )
        session.add_all([c1, c2])
        await session.flush()
        assert c1.id != c2.id


class TestSecretModel:
    @pytest.mark.asyncio
    async def test_create_secret(self, session: AsyncSession):
        secret = Secret(
            name="FIREWORKS_API_KEY",
            encrypted_value=b"\x00\x01",
            scope="global",
        )
        session.add(secret)
        await session.flush()
        assert secret.id is not None

    @pytest.mark.asyncio
    async def test_secret_unique_name_scope(self, session: AsyncSession):
        s1 = Secret(name="KEY", encrypted_value=b"a", scope="global")
        s2 = Secret(name="KEY", encrypted_value=b"b", scope="global")
        session.add_all([s1, s2])
        with pytest.raises(Exception):  # IntegrityError
            await session.flush()

    @pytest.mark.asyncio
    async def test_secret_same_name_different_scope(self, session: AsyncSession):
        s1 = Secret(name="KEY", encrypted_value=b"a", scope="global")
        s2 = Secret(name="KEY", encrypted_value=b"b", scope="agent:abc")
        session.add_all([s1, s2])
        await session.flush()
        assert s1.id != s2.id
