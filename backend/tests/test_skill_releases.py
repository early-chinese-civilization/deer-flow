from pathlib import Path

from app.gateway.db.models import RuntimeManifest, SkillDefinition, SkillInstall, SkillRelease, SkillVersion
from app.gateway.db.repository import SkillReleaseRepository


class FakeAsyncSession:
    def __init__(self):
        self.added = []
        self.committed = False
        self.flushed = False
        self.refreshed = []

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        self.flushed = True

    async def refresh(self, value):
        self.refreshed.append(value)

    async def commit(self):
        self.committed = True


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
    assert "created_at" in columns
    assert columns["release_version"].unique is True
    assert columns["package_version"].nullable is True


def test_create_skill_release_generates_release_version_and_persists_metadata():
    async def run():
        session = FakeAsyncSession()

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

    import asyncio

    asyncio.run(run())


def test_create_skill_release_allows_empty_package_version():
    async def run():
        session = FakeAsyncSession()

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
            release_version="rel_fixed",
            commit=False,
        )

        assert session.committed is False
        assert release.release_version == "rel_fixed"
        assert release.package_version is None

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
    assert "owner_user_id" in definition_columns

    assert SkillVersion.__tablename__ == "skill_versions"
    assert "skill_definition_id" in version_columns
    assert "version_number" in version_columns
    assert "source_package_version" in version_columns
    assert "content_hash" in version_columns
    assert "file_manifest_hash" in version_columns
    assert "artifact_uri" in version_columns

    assert SkillInstall.__tablename__ == "skill_installs"
    assert "user_id" in install_columns
    assert "skill_definition_id" in install_columns
    assert "installed_version_id" in install_columns
    assert "current_version_id" in install_columns

    assert RuntimeManifest.__tablename__ == "runtime_manifests"
    assert "manifest_json" in manifest_columns
    assert "manifest_hash" in manifest_columns


def test_skill_versions_installs_manifest_migration_exists():
    migration_path = Path("alembic/versions/a7c9e2d5f604_add_skill_versions_installs_runtime_manifest.py")

    assert migration_path.exists()
    migration = migration_path.read_text(encoding="utf-8")
    assert "skill_definitions" in migration
    assert "skill_versions" in migration
    assert "skill_installs" in migration
    assert "skill_version_id" in migration
    assert "runtime_manifests" in migration


def test_runtime_manifest_hash_migration_exists():
    migration_path = Path("alembic/versions/c1d2e3f4a5b6_add_runtime_manifest_hash.py")

    assert migration_path.exists()
    migration = migration_path.read_text(encoding="utf-8")
    assert "runtime_manifests" in migration
    assert "manifest_hash" in migration
