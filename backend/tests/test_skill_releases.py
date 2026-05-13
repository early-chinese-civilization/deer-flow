import uuid
from pathlib import Path

import pytest

from app.gateway.db.models import PendingSkillForkClaim, RuntimeManifest, SkillDefinition, SkillInstall, SkillRelease, SkillVersion
from app.gateway.db.repository import SkillReleaseRepository, SkillRepository


class FakeAsyncSession:
    def __init__(self, skill_version=None, existing_release=None):
        self.added = []
        self.committed = False
        self.executed = []
        self.flushed = False
        self.refreshed = []
        self.skill_version = skill_version
        self.existing_release = existing_release

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        self.flushed = True

    async def refresh(self, value):
        self.refreshed.append(value)

    async def commit(self):
        self.committed = True

    async def execute(self, stmt):
        self.executed.append(stmt)
        if len(self.executed) == 1:
            return FakeScalarResult(self.skill_version)
        return FakeScalarResult(self.existing_release)


class FakeScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeExecuteSession:
    def __init__(self, value):
        self.value = value
        self.executed = []

    async def execute(self, stmt):
        self.executed.append(stmt)
        return FakeScalarResult(self.value)


def test_skill_release_model_declares_release_contract_columns():
    columns = SkillRelease.__table__.columns

    assert SkillRelease.__tablename__ == "skill_releases"
    assert "skill_id" in columns
    assert "version_number" in columns
    assert "skill_name" in columns
    assert "release_version" in columns
    assert "package_version" in columns
    assert "description" in columns
    assert "release_notes" in columns
    assert "status" in columns
    assert "artifact_path" in columns
    assert "publisher_user_id" in columns
    assert "source_skill_id" in columns
    assert "published_skill_id" in columns
    assert "skill_version_id" in columns
    assert "published_at" in columns
    assert "created_at" in columns
    assert "updated_at" in columns
    assert columns["release_version"].unique is True
    assert columns["package_version"].nullable is True


def test_create_skill_release_generates_release_version_and_persists_metadata():
    async def run():
        skill_id = uuid.UUID("11111111-1111-4111-8111-111111111111")
        session = FakeAsyncSession(
            skill_version=SkillVersion(
                id=13,
                skill_id=skill_id,
                skill_definition_id=11,
                version_number=2,
                content_hash="hash",
                file_manifest_hash="manifest",
                artifact_uri="artifacts/skills/13/demo-skill",
            )
        )

        release = await SkillReleaseRepository.create_release(
            session,
            skill_name="demo-skill",
            package_version="v1",
            description="Demo skill",
            release_notes="Initial release",
            artifact_path="public/demo-skill",
            publisher_user_id=7,
            source_skill_id=11,
            published_skill_id=12,
            skill_version_id=13,
            skill_id=skill_id,
            version_number=2,
        )

        assert release in session.added
        assert session.flushed is True
        assert session.committed is True
        assert release.release_version.startswith("rel_")
        assert release.package_version == "v1"
        assert release.release_notes == "Initial release"
        assert release.status == "published"
        assert release.skill_name == "demo-skill"
        assert release.artifact_path == "public/demo-skill"
        assert release.publisher_user_id == 7
        assert release.source_skill_id == 11
        assert release.published_skill_id == 12
        assert release.skill_version_id == 13
        assert release.skill_id == skill_id
        assert release.version_number == 2
        assert release.published_at is not None

    import asyncio

    asyncio.run(run())


def test_create_skill_release_allows_empty_package_version():
    async def run():
        skill_id = uuid.UUID("22222222-2222-4222-8222-222222222222")
        session = FakeAsyncSession(
            skill_version=SkillVersion(
                id=13,
                skill_id=skill_id,
                skill_definition_id=11,
                version_number=1,
                content_hash="hash",
                file_manifest_hash="manifest",
                artifact_uri="artifacts/skills/13/demo-skill",
            )
        )

        release = await SkillReleaseRepository.create_release(
            session,
            skill_name="demo-skill",
            package_version=None,
            description="Demo skill",
            artifact_path="public/demo-skill",
            publisher_user_id=7,
            source_skill_id=11,
            published_skill_id=12,
            skill_version_id=13,
            skill_id=skill_id,
            version_number=1,
            release_version="rel_fixed",
            commit=False,
        )

        assert session.committed is False
        assert release.release_version == "rel_fixed"
        assert release.package_version is None

    import asyncio

    asyncio.run(run())


def test_create_skill_release_rejects_mismatched_legacy_version_identity():
    async def run():
        session = FakeAsyncSession(
            skill_version=SkillVersion(
                id=13,
                skill_id=uuid.UUID("33333333-3333-4333-8333-333333333333"),
                skill_definition_id=11,
                version_number=2,
                content_hash="hash",
                file_manifest_hash="manifest",
                artifact_uri="artifacts/skills/13/demo-skill",
            )
        )

        with pytest.raises(ValueError, match="skill_id"):
            await SkillReleaseRepository.create_release(
                session,
                skill_name="demo-skill",
                package_version=None,
                description="Demo skill",
                artifact_path="public/demo-skill",
                publisher_user_id=7,
                source_skill_id=11,
                published_skill_id=12,
                skill_version_id=13,
                skill_id=uuid.UUID("44444444-4444-4444-8444-444444444444"),
                version_number=2,
                commit=False,
            )

    import asyncio

    asyncio.run(run())


def test_get_latest_release_for_public_skill_returns_release():
    async def run():
        release = SkillRelease(
            skill_name="demo-skill",
            release_version="rel_fixed",
            package_version="v1",
            description="Demo skill",
            status="published",
            artifact_path="public/demo-skill",
            publisher_user_id=7,
            source_skill_id=11,
            published_skill_id=12,
        )
        session = FakeExecuteSession(release)

        result = await SkillReleaseRepository.get_latest_release_for_public_skill(session, published_skill_id=12)

        assert result is release
        assert len(session.executed) == 1

    import asyncio

    asyncio.run(run())


def test_get_latest_release_for_public_skill_returns_none_for_legacy_public_skill():
    async def run():
        session = FakeExecuteSession(None)

        result = await SkillReleaseRepository.get_latest_release_for_public_skill(session, published_skill_id=99)

        assert result is None
        assert len(session.executed) == 1

    import asyncio

    asyncio.run(run())


def test_latest_published_release_by_name_uses_terminal_release_identity():
    async def run():
        release = SkillRelease(
            skill_id=uuid.UUID("55555555-5555-4555-8555-555555555555"),
            version_number=2,
            skill_name="demo-skill",
            release_version="rel_fixed",
            package_version="v1",
            description="Demo skill",
            status="published",
            artifact_path=".deer-flow/skills/55555555-5555-4555-8555-555555555555/2",
            publisher_user_id=7,
            skill_version_id=None,
        )
        session = FakeExecuteSession(release)

        result = await SkillReleaseRepository.get_latest_published_release_by_name(session, skill_name="demo-skill")

        sql = str(session.executed[0].compile(compile_kwargs={"literal_binds": True}))
        assert result is release
        assert "skill_releases.skill_id = skill_versions.skill_id" in sql
        assert "skill_releases.version_number = skill_versions.version_number" in sql
        assert "skill_releases.skill_version_id IS NOT NULL" not in sql

    import asyncio

    asyncio.run(run())


def test_latest_published_release_for_definition_uses_terminal_release_identity():
    async def run():
        session = FakeExecuteSession(None)

        await SkillReleaseRepository.get_latest_published_release_for_definition(session, skill_definition_id=11)

        sql = str(session.executed[0].compile(compile_kwargs={"literal_binds": True}))
        assert "skill_releases.skill_id = skill_versions.skill_id" in sql
        assert "skill_releases.version_number = skill_versions.version_number" in sql
        assert "skill_releases.skill_version_id IS NOT NULL" not in sql

    import asyncio

    asyncio.run(run())


def test_skill_release_migration_creates_release_table():
    migration_path = Path("alembic/versions/e2a7c9d4f601_add_skill_releases.py")

    assert migration_path.exists()
    migration = migration_path.read_text(encoding="utf-8")
    assert "skill_releases" in migration
    assert "release_version" in migration
    assert "package_version" in migration
    assert "published_skill_id" in migration


def test_skill_release_notes_migration_adds_release_notes_column():
    migration_path = Path("alembic/versions/f4b8c3d2a901_add_release_notes_to_skill_releases.py")

    assert migration_path.exists()
    migration = migration_path.read_text(encoding="utf-8")
    assert "skill_releases" in migration
    assert "release_notes" in migration


def test_platform_skill_version_install_models_declares_manifest_foundation_columns():
    definition_columns = SkillDefinition.__table__.columns
    version_columns = SkillVersion.__table__.columns
    install_columns = SkillInstall.__table__.columns
    manifest_columns = RuntimeManifest.__table__.columns

    assert SkillDefinition.__tablename__ == "skill_definitions"
    assert "name" in definition_columns
    assert "source_type" in definition_columns
    assert "source_identifier" in definition_columns
    assert "owner_user_id" in definition_columns

    assert SkillVersion.__tablename__ == "skill_versions"
    assert "skill_id" in version_columns
    assert "skill_definition_id" in version_columns
    assert "version_number" in version_columns
    assert "source_package_version" in version_columns
    assert "content_hash" in version_columns
    assert "file_manifest_hash" in version_columns
    assert "artifact_uri" in version_columns

    assert SkillInstall.__tablename__ == "skill_installations"
    assert "user_id" in install_columns
    assert "skill_id" in install_columns
    assert "version_number" in install_columns
    assert "status" in install_columns
    assert "skill_definition_id" in install_columns
    assert "installed_version_id" in install_columns
    assert "current_version_id" in install_columns

    assert RuntimeManifest.__tablename__ == "runtime_manifests"
    assert "manifest_json" in manifest_columns
    assert "manifest_hash" in manifest_columns


def test_pending_skill_fork_claim_model_declares_claim_columns():
    claim_columns = PendingSkillForkClaim.__table__.columns

    assert PendingSkillForkClaim.__tablename__ == "pending_skill_fork_claims"
    assert "user_id" in claim_columns
    assert "source_skill_definition_id" in claim_columns
    assert "source_skill_version_id" in claim_columns
    assert "claim_token_hash" in claim_columns
    assert "status" in claim_columns
    assert "source_snapshot" in claim_columns
    assert "expires_at" in claim_columns
    assert "claimed_at" in claim_columns


def test_skill_versions_installs_manifest_migration_exists():
    migration_path = Path("alembic/versions/a7c9e2d5f604_add_skill_versions_installs_runtime_manifest.py")

    assert migration_path.exists()
    migration = migration_path.read_text(encoding="utf-8")
    assert "skill_definitions" in migration
    assert "skill_versions" in migration
    assert "skill_installs" in migration
    assert "skill_version_id" in migration
    assert "runtime_manifests" in migration
    assert "legacy-skill-" in migration
    assert "UPDATE agents_skills" in migration
    assert "skill_install_id = si.id" in migration


def test_runtime_manifest_hash_migration_exists():
    migration_path = Path("alembic/versions/c1d2e3f4a5b6_add_runtime_manifest_hash.py")

    assert migration_path.exists()
    migration = migration_path.read_text(encoding="utf-8")
    assert "runtime_manifests" in migration
    assert "manifest_hash" in migration


def test_skill_definition_namespace_migration_exists():
    migration_path = Path("alembic/versions/9f4d2c7b1a63_namespace_skill_definitions.py")

    assert migration_path.exists()
    migration = migration_path.read_text(encoding="utf-8")
    assert "source_type" in migration
    assert "source_identifier" in migration
    assert "uq_skill_definitions_source_name_active" in migration
    assert "skill_definition_id" in migration
    assert "INSERT INTO skill_definitions" in migration
    assert "COALESCE(s.owner_user_id, s.user_id)" in migration
    assert "UPDATE skill_versions AS sv" in migration
    assert "UPDATE agents_skills AS ask" in migration
    assert "OR ask.skill_install_id <> resolved.skill_install_id" in migration


def test_install_bound_agent_lookup_includes_disabled_active_bindings():
    class FakeScalars:
        def all(self):
            return []

    class FakeResult:
        def scalars(self):
            return FakeScalars()

    class CaptureSession:
        def __init__(self):
            self.statement = None

        async def execute(self, stmt):
            self.statement = stmt
            return FakeResult()

    async def run():
        session = CaptureSession()
        await SkillRepository.list_bound_agents_for_install(
            session,
            user_id=7,
            skill_install_id=20,
        )
        return str(session.statement.compile(compile_kwargs={"literal_binds": True}))

    import asyncio

    sql = asyncio.run(run())
    assert "agents_skills.skill_install_id = 20" in sql
    assert "agents_skills.enabled" not in sql


def test_pending_skill_fork_claims_migration_exists():
    migration_path = Path("alembic/versions/2b7c6d8e9f10_add_pending_skill_fork_claims.py")

    assert migration_path.exists()
    migration = migration_path.read_text(encoding="utf-8")
    assert "pending_skill_fork_claims" in migration
    assert "claim_token_hash" in migration
    assert "source_skill_version_id" in migration
