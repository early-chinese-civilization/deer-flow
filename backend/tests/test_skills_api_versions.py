import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid5

import pytest
from fastapi import HTTPException

from app.gateway.db.models import LegacySkill as Skill
from app.gateway.db.models import SkillDefinition, SkillInstall, SkillRelease, SkillVersion, User
from app.gateway.db.repository import SkillRepository
from app.gateway.routers import skills as skills_router

_TEST_SKILL_NAMESPACE = UUID("1cfd0d33-84d8-5e43-9b53-b22f9a21b423")


class FakeDb:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self.flushed = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def flush(self):
        self.flushed += 1


def _user() -> User:
    return User(id=7, external_auth_id="sub", username="alice", display_name="Alice")


def _definition(
    *,
    definition_id: int = 100,
    owner_user_id: int | None = 7,
    source_type: str = "user",
    source_identifier: str = "7",
    owner_user: User | None = None,
) -> SkillDefinition:
    return SkillDefinition(
        id=definition_id,
        name="demo-skill",
        display_name="demo-skill",
        description="Demo skill",
        owner_user_id=owner_user_id,
        source_type=source_type,
        source_identifier=source_identifier,
        owner_user=owner_user,
    )


def _version(version_number: int, *, definition: SkillDefinition | None = None) -> SkillVersion:
    definition = definition or _definition()
    skill_id = uuid5(_TEST_SKILL_NAMESPACE, f"skill-definition:{definition.id}")
    return SkillVersion(
        id=200 + version_number,
        skill_id=skill_id,
        skill_definition_id=definition.id,
        version_number=version_number,
        source_package_version="pkg-ignored",
        description="Demo skill",
        content_hash=f"hash-{version_number}",
        file_manifest_hash=f"manifest-{version_number}",
        artifact_uri=f"artifacts/skills/{definition.id}/v{version_number}/demo-skill",
        definition=definition,
    )


def _install(version: SkillVersion) -> SkillInstall:
    return SkillInstall(
        id=300,
        user_id=7,
        skill_id=version.skill_id,
        version_number=version.version_number,
        status="active",
        skill_definition_id=version.skill_definition_id,
        installed_version_id=version.id,
        current_version_id=version.id,
        definition=version.definition,
        current_version=version,
    )


def _public_skill(skill_id: int, name: str = "demo-skill") -> Skill:
    return Skill(id=skill_id, user_id=None, owner_user_id=7, name=name, display_name=name, description="Public skill", file_path=f"public/{name}")


def _custom_skill(skill_id: int, name: str = "demo-skill") -> Skill:
    return Skill(id=skill_id, user_id=7, owner_user_id=None, name=name, display_name=name, description="Custom skill", file_path=f"7/{name}")


def _release(published_skill_id: int, version: SkillVersion | None = None) -> SkillRelease:
    version = version or _version(1)
    release = SkillRelease(
        id=30,
        skill_name="demo-skill",
        release_version="rel_fixed",
        package_version=version.source_package_version,
        description="Public skill",
        release_notes="Initial release",
        status="published",
        artifact_path=version.artifact_uri,
        publisher_user_id=7,
        source_skill_id=11,
        published_skill_id=published_skill_id,
        skill_version_id=version.id,
        skill_id=version.skill_id,
        version_number=version.version_number,
        created_at=datetime(2026, 4, 28, 8, 0, tzinfo=UTC),
    )
    release.skill_version = version
    release.publisher_user = User(id=7, external_auth_id="sub", username="alice", display_name="Alice")
    return release


def test_visible_skills_hide_stale_user_rows_for_public_system_definition():
    definition = _definition(definition_id=7, owner_user_id=None, source_type="legacy", source_identifier="legacy")
    public = _public_skill(24, "chart-visualization")
    public.owner_user_id = None
    public.skill_definition_id = definition.id
    public.definition = definition
    stale_user_row = _custom_skill(28, "chart-visualization")
    stale_user_row.skill_definition_id = definition.id
    stale_user_row.definition = definition

    result = SkillRepository._dedupe_visible_skills([stale_user_row, public])

    assert result == [public]


def test_visible_skills_preserve_community_and_personal_rows_for_same_definition():
    owner = User(id=8, external_auth_id="sub-8", username="bob", display_name="Bob")
    definition = _definition(definition_id=102, owner_user_id=8, source_type="user", source_identifier="8", owner_user=owner)
    community = _public_skill(102, "community-skill")
    community.owner_user_id = owner.id
    community.owner_user = owner
    community.skill_definition_id = definition.id
    community.definition = definition
    personal = _custom_skill(104, "community-skill")
    personal.skill_definition_id = definition.id
    personal.definition = definition

    result = SkillRepository._dedupe_visible_skills([community, personal])

    assert result == [community, personal]


def test_skill_response_relation_matrix():
    current_user = _user()
    other_user = User(id=8, external_auth_id="sub-8", username="bob", display_name="Bob")
    official_definition = _definition(definition_id=101, owner_user_id=None, source_type="legacy", source_identifier="legacy")
    official_public = _public_skill(101, "official-skill")
    official_public.owner_user_id = None
    official_public.definition = official_definition

    official_response = skills_router._skill_to_response(official_public, skill_version=_version(1, definition=official_definition), current_user_id=current_user.id)
    assert official_response.space == "system"
    assert official_response.source_kind == "official"
    assert official_response.viewer_relation == "system_available"
    assert official_response.owner_display_name == "official"
    assert official_response.skill_install_id is None

    legacy_official_install = _install(_version(1, definition=official_definition))
    legacy_official_response = skills_router._skill_to_response(official_public, skill_version=_version(1, definition=official_definition), skill_install=legacy_official_install, current_user_id=current_user.id)
    assert legacy_official_response.space == "system"
    assert legacy_official_response.skill_install_id is None
    assert legacy_official_response.current_platform_version is None

    community_definition = _definition(definition_id=102, owner_user_id=8, source_type="user", source_identifier="8", owner_user=other_user)
    community_public = _public_skill(102, "community-skill")
    community_public.owner_user_id = 8
    community_public.owner_user = other_user
    community_response = skills_router._skill_to_response(community_public, skill_version=_version(1, definition=community_definition), current_user_id=current_user.id)
    assert community_response.space == "community"
    assert community_response.source_kind == "community"
    assert community_response.viewer_relation == "community_available"
    assert community_response.owner_display_name == "Bob"

    missing_owner_public = _public_skill(108, "missing-owner-community-skill")
    missing_owner_public.owner_user_id = None
    missing_owner_response = skills_router._skill_to_response(
        missing_owner_public,
        skill_version=_version(1, definition=community_definition),
        current_user_id=current_user.id,
    )
    assert missing_owner_response.source_kind == "community"
    assert missing_owner_response.viewer_relation == "community_available"
    assert missing_owner_response.owner_display_name == "Bob"

    self_public = _public_skill(103, "self-skill")
    self_public.owner_user = current_user
    self_response = skills_router._skill_to_response(self_public, release=_release(103), skill_version=_version(1), current_user_id=current_user.id)
    assert self_response.space == "community"
    assert self_response.source_kind == "community"
    assert self_response.viewer_relation == "authored_published"

    self_legacy_response = skills_router._skill_to_response(self_public, current_user_id=current_user.id)
    assert self_legacy_response.source_kind == "community"
    assert self_legacy_response.viewer_relation == "authored_published"

    downloaded_version = _version(1, definition=community_definition)
    downloaded = _custom_skill(104, "community-skill")
    downloaded.definition = community_definition
    downloaded_install = _install(downloaded_version)
    downloaded_install.skill_definition_id = community_definition.id
    downloaded_install.definition = community_definition
    downloaded_response = skills_router._skill_to_response(downloaded, skill_version=downloaded_version, skill_install=downloaded_install, current_user_id=current_user.id)
    assert downloaded_response.space == "personal"
    assert downloaded_response.source_kind == "community"
    assert downloaded_response.viewer_relation == "downloaded"

    authored = _custom_skill(105, "authored-skill")
    authored.definition = _definition()
    authored_response = skills_router._skill_to_response(authored, skill_version=_version(1), skill_install=_install(_version(1)), current_user_id=current_user.id)
    assert authored_response.space == "personal"
    assert authored_response.source_kind == "personal"
    assert authored_response.viewer_relation == "authored"

    published_response = skills_router._skill_to_response(
        authored,
        release=_release(105, _version(1)),
        skill_version=_version(1),
        skill_install=_install(_version(1)),
        latest_skill_version=_version(1),
        current_user_id=current_user.id,
    )
    assert published_response.viewer_relation == "authored_published"

    v1 = _version(1)
    v2 = _version(2, definition=v1.definition)
    unpublished_install = _install(v2)
    unpublished_response = skills_router._skill_to_response(
        authored,
        release=_release(105, v1),
        skill_version=v2,
        skill_install=unpublished_install,
        latest_skill_version=v1,
        current_user_id=current_user.id,
    )
    assert unpublished_response.viewer_relation == "authored_unpublished_changes"
    assert unpublished_response.update_available is None

    fork_definition = _definition(definition_id=106, owner_user_id=7, source_type="fork", source_identifier="source:102")
    forked = _custom_skill(106, "forked-skill")
    forked.definition = fork_definition
    forked_response = skills_router._skill_to_response(forked, skill_version=_version(1, definition=fork_definition), current_user_id=current_user.id)
    assert forked_response.source_kind == "fork"
    assert forked_response.viewer_relation == "forked"

    latest_version = _version(2, definition=community_definition)
    downloaded_install.current_version = downloaded_version
    downloaded_install.current_version_id = downloaded_version.id
    update_response = skills_router._skill_to_response(
        downloaded,
        skill_version=downloaded_version,
        skill_install=downloaded_install,
        latest_skill_version=latest_version,
        current_user_id=current_user.id,
    )
    assert update_response.viewer_relation == "update_available"
    assert update_response.current_platform_version == 1
    assert update_response.latest_platform_version == 2


def test_skill_response_legacy_public_fallback_is_official():
    legacy_public = _public_skill(107, "legacy-skill")
    legacy_public.owner_user_id = None
    response = skills_router._skill_to_response(legacy_public, current_user_id=_user().id)

    assert response.space == "system"
    assert response.source_kind == "official"
    assert response.viewer_relation == "system_available"
    assert response.owner_display_name == "official"


def test_skill_response_preserves_same_name_different_source_identity():
    bob = User(id=8, external_auth_id="sub-8", username="bob", display_name="Bob")
    carol = User(id=9, external_auth_id="sub-9", username="carol", display_name="Carol")
    bob_definition = _definition(definition_id=201, owner_user_id=8, source_type="user", source_identifier="8", owner_user=bob)
    carol_definition = _definition(definition_id=202, owner_user_id=9, source_type="user", source_identifier="9", owner_user=carol)
    bob_public = _public_skill(201, "same-skill")
    bob_public.owner_user_id = 8
    bob_public.owner_user = bob
    carol_public = _public_skill(202, "same-skill")
    carol_public.owner_user_id = 9
    carol_public.owner_user = carol

    bob_response = skills_router._skill_to_response(bob_public, skill_version=_version(1, definition=bob_definition), current_user_id=7)
    carol_response = skills_router._skill_to_response(carol_public, skill_version=_version(1, definition=carol_definition), current_user_id=7)

    assert bob_response.name == carol_response.name
    assert bob_response.skill_definition_id == 201
    assert carol_response.skill_definition_id == 202
    assert bob_response.owner_display_name == "Bob"
    assert carol_response.owner_display_name == "Carol"


def test_list_skills_uses_platform_version_for_public_and_install_rows(monkeypatch):
    db = FakeDb()
    current_user = _user()
    definition = _definition()
    public_version = _version(2, definition=definition)
    install_version = _version(1, definition=definition)
    public = _public_skill(12, "demo-skill")
    custom = _custom_skill(21, "demo-skill")

    async def list_visible_skills(db_arg, *, user_id):
        return [public, custom]

    async def list_published_releases(db_arg):
        return [_release(public.id, public_version)]

    async def get_latest_release_for_public_skill(db_arg, *, published_skill_id):
        return _release(published_skill_id, public_version)

    async def get_version_by_id(db_arg, *, skill_version_id):
        assert skill_version_id == public_version.id
        return public_version

    async def get_install_by_user_and_name(db_arg, *, user_id, name):
        return _install(install_version)

    async def get_install_by_user_and_definition(db_arg, *, user_id, skill_definition_id):
        return _install(install_version)

    async def get_install_by_user_and_skill_id(db_arg, *, user_id, skill_id):
        return _install(install_version)

    async def get_latest_published_release_for_definition(db_arg, *, skill_definition_id):
        assert skill_definition_id == definition.id
        return _release(public.id, public_version)

    monkeypatch.setattr(skills_router.SkillRepository, "list_visible_skills", list_visible_skills)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "list_published_releases", list_published_releases)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_latest_release_for_public_skill", get_latest_release_for_public_skill)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_latest_published_release_for_definition", get_latest_published_release_for_definition)
    monkeypatch.setattr(skills_router.SkillVersionRepository, "get_by_id", get_version_by_id)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_user_and_name", get_install_by_user_and_name)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_user_and_definition", get_install_by_user_and_definition)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_user_and_skill_id", get_install_by_user_and_skill_id)

    async def run():
        return await skills_router.list_skills(current_user=current_user, db=db)

    response = asyncio.run(run())
    by_category = {skill.category: skill for skill in response.skills}

    assert by_category["public"].platform_version == 2
    assert by_category["public"].version == "2"
    assert by_category["public"].source_package_version == "pkg-ignored"
    assert by_category["public"].release_version == "rel_fixed"
    assert by_category["custom"].platform_version == 1
    assert by_category["custom"].skill_install_id == 300
    assert by_category["custom"].version == "1"


def test_get_skill_includes_public_platform_version_and_publish_metadata(monkeypatch):
    db = FakeDb()
    public = _public_skill(12, "demo-skill")
    public.owner_user = User(id=7, external_auth_id="sub", username="alice", display_name="Alice")
    version = _version(2)
    release = _release(12, version)

    async def list_user_skills_by_name(db_arg, *, user_id, name):
        return []

    async def get_latest_published_release_by_name(db_arg, *, skill_name):
        return release

    async def get_install_by_user_and_skill_id(db_arg, *, user_id, skill_id):
        return None

    async def get_version_by_id(db_arg, *, skill_version_id):
        return version

    async def get_install_by_user_and_definition(db_arg, *, user_id, skill_definition_id):
        return None

    monkeypatch.setattr(skills_router.SkillRepository, "list_user_skills_by_name", list_user_skills_by_name)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_latest_published_release_by_name", get_latest_published_release_by_name)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_user_and_skill_id", get_install_by_user_and_skill_id)
    monkeypatch.setattr(skills_router.SkillVersionRepository, "get_by_id", get_version_by_id)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_user_and_definition", get_install_by_user_and_definition)

    async def run():
        return await skills_router.get_skill("demo-skill", current_user=_user(), db=db)

    response = asyncio.run(run())

    assert response.owner_display_name == "Alice"
    assert response.platform_version == 2
    assert response.version == "2"
    assert response.release_version == "rel_fixed"
    assert response.published_at == "2026-04-28T08:00:00+00:00"


def test_get_skill_resolves_terminal_release_without_legacy_version_id(monkeypatch):
    db = FakeDb()
    version = _version(2)
    release = _release(None, version)
    release.skill_version_id = None
    release.skill_version = None

    async def list_user_skills_by_name(db_arg, *, user_id, name):
        return []

    async def get_latest_published_release_by_name(db_arg, *, skill_name):
        assert skill_name == "demo-skill"
        return release

    async def get_by_skill_version(db_arg, *, skill_id, version_number):
        assert skill_id == version.skill_id
        assert version_number == version.version_number
        return version

    async def get_install_by_user_and_skill_id(db_arg, *, user_id, skill_id):
        return None

    monkeypatch.setattr(skills_router.SkillRepository, "list_user_skills_by_name", list_user_skills_by_name)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_latest_published_release_by_name", get_latest_published_release_by_name)
    monkeypatch.setattr(skills_router.SkillVersionRepository, "get_by_skill_version", get_by_skill_version)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_user_and_skill_id", get_install_by_user_and_skill_id)

    async def run():
        return await skills_router.get_skill("demo-skill", current_user=_user(), db=db)

    response = asyncio.run(run())

    assert response.skill_id == str(version.skill_id)
    assert response.version_number == 2
    assert response.platform_version == 2


def test_install_public_skill_records_install_without_copying_public_latest(monkeypatch):
    db = FakeDb()
    version = _version(1)
    release = _release(None, version)
    install = _install(version)

    async def get_published_release_by_skill_version(db_arg, *, skill_id, version_number):
        assert skill_id == version.skill_id
        assert version_number == version.version_number
        return release

    async def upsert_install(db_arg, *, user_id, definition, version):
        assert user_id == _user().id
        assert definition.id == version.skill_definition_id
        return install

    async def create_skill(db_arg, **kwargs):
        raise AssertionError("terminal install must not create legacy personal Skill rows")

    async def get_by_user_and_skill_id(db_arg, *, user_id, skill_id):
        assert skill_id == version.skill_id
        return install

    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_published_release_by_skill_version", get_published_release_by_skill_version)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "upsert_install", upsert_install)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_user_and_skill_id", get_by_user_and_skill_id)
    monkeypatch.setattr(skills_router.SkillRepository, "create_skill", create_skill)

    async def run():
        return await skills_router.install_skill(
            skills_router.SkillInstallRequest(skill_id=str(version.skill_id), version_number=version.version_number),
            current_user=_user(),
            db=db,
        )

    response = asyncio.run(run())

    assert db.commits == 1
    assert response.category == "public"
    assert response.platform_version == 1
    assert response.skill_install_id == 300
    assert response.version == "1"


def test_terminal_install_rejects_unpublished_release(monkeypatch):
    db = FakeDb()
    version = _version(1)

    async def get_published_release_by_skill_version(db_arg, *, skill_id, version_number):
        assert skill_id == version.skill_id
        assert version_number == version.version_number
        return None

    async def upsert_install(*args, **kwargs):
        raise AssertionError("unpublished releases must not create or update installs")

    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_published_release_by_skill_version", get_published_release_by_skill_version)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "upsert_install", upsert_install)

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await skills_router.install_skill(
                skills_router.SkillInstallRequest(skill_id=str(version.skill_id), version_number=version.version_number),
                current_user=_user(),
                db=db,
            )
        return exc_info.value

    exc = asyncio.run(run())

    assert exc.status_code == 404
    assert db.commits == 0
    assert db.rollbacks == 1


def test_archive_install_route_is_removed():
    db = FakeDb()

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await skills_router.install_skill(
                skills_router.SkillInstallRequest(thread_id="thread-1", path="mnt/user-data/outputs/demo.skill"),
                current_user=_user(),
                db=db,
            )
        return exc_info.value

    exc = asyncio.run(run())

    assert exc.status_code == 410
    assert exc.detail["code"] == "archive_install_removed"
    assert db.commits == 0
    assert db.rollbacks == 1


def test_list_skills_hides_public_rows_without_published_release(monkeypatch):
    db = FakeDb()
    public = _public_skill(12, "demo-skill")

    async def list_visible_skills(db_arg, *, user_id):
        return [public]

    async def list_published_releases(db_arg):
        return []

    monkeypatch.setattr(skills_router.SkillRepository, "list_visible_skills", list_visible_skills)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "list_published_releases", list_published_releases)

    async def run():
        return await skills_router.list_skills(current_user=_user(), db=db)

    response = asyncio.run(run())

    assert response.skills == []


def test_download_and_check_download_routes_are_removed():
    db = FakeDb()

    async def run_check():
        with pytest.raises(HTTPException) as exc_info:
            await skills_router.check_skill_download(
                "demo-skill",
                skills_router.SkillDownloadCheckRequest(skill_definition_id=100),
                current_user=_user(),
                db=db,
            )
        return exc_info.value

    async def run_install():
        with pytest.raises(HTTPException) as exc_info:
            await skills_router.download_skill(
                "demo-skill",
                skills_router.SkillDownloadRequest(skill_definition_id=100),
                current_user=_user(),
                db=db,
            )
        return exc_info.value

    check_exc = asyncio.run(run_check())
    install_exc = asyncio.run(run_install())

    assert check_exc.status_code == 410
    assert check_exc.detail["code"] == "skill_download_removed"
    assert install_exc.status_code == 410
    assert install_exc.detail["code"] == "skill_download_removed"
    assert db.commits == 0
    assert db.rollbacks == 0


def test_fork_package_route_is_removed_before_claim_creation(monkeypatch):
    db = FakeDb()

    async def create_claim(*args, **kwargs):
        raise AssertionError("removed fork route must not create pending fork claims")

    monkeypatch.setattr(skills_router.PendingSkillForkClaimRepository, "create_claim", create_claim)

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await skills_router.download_skill_fork_package(
                "demo-skill",
                skills_router.SkillForkPackageRequest(skill_definition_id=100),
                current_user=_user(),
                db=db,
            )
        return exc_info.value

    exc = asyncio.run(run())

    assert exc.status_code == 410
    assert exc.detail["code"] == "skill_fork_removed"
    assert db.commits == 0
    assert db.rollbacks == 0


def test_manual_update_install_switches_current_platform_version(monkeypatch):
    db = FakeDb()
    v1 = _version(1)
    v2 = _version(2, definition=v1.definition)
    install = _install(v1)
    touched_user_skill = False
    touched_agent_bindings = False

    async def get_published_release_by_skill_version(db_arg, *, skill_id, version_number):
        assert skill_id == v2.skill_id
        assert version_number == v2.version_number
        release = _release(None, v2)
        release.skill_version_id = None
        release.skill_version = None
        return release

    async def get_by_skill_version(db_arg, *, skill_id, version_number):
        assert skill_id == v2.skill_id
        assert version_number == v2.version_number
        return v2

    async def update_current_version(db_arg, *, install, version):
        install.current_version = version
        install.current_version_id = version.id
        install.version_number = version.version_number
        return install

    async def get_by_id_for_user(db_arg, *, user_id, skill_install_id):
        assert skill_install_id == install.id
        return install

    async def list_bound_agents_for_install(db_arg, *, user_id, skill_install_id):
        return []

    async def create_skill(*args, **kwargs):
        nonlocal touched_user_skill
        touched_user_skill = True
        raise AssertionError("update confirmation must not rewrite skill rows")

    async def rebind_agent_skills(*args, **kwargs):
        nonlocal touched_agent_bindings
        touched_agent_bindings = True
        raise AssertionError("update confirmation must not mutate AgentSkill rows")

    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_published_release_by_skill_version", get_published_release_by_skill_version)
    monkeypatch.setattr(skills_router.SkillVersionRepository, "get_by_skill_version", get_by_skill_version)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "update_current_version", update_current_version)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_id_for_user", get_by_id_for_user)
    monkeypatch.setattr(skills_router.SkillRepository, "list_bound_agents_for_install", list_bound_agents_for_install)
    monkeypatch.setattr(skills_router.SkillRepository, "create_skill", create_skill)
    monkeypatch.setattr(skills_router.SkillRepository, "rebind_agent_skills", rebind_agent_skills)
    monkeypatch.setattr(skills_router, "_is_skill_version_artifact_available", lambda version: True)

    async def run():
        return await skills_router.update_skill_install(
            "demo-skill",
            skills_router.SkillInstallUpdateRequest(skill_install_id=install.id, skill_id=str(v2.skill_id), version_number=v2.version_number),
            current_user=_user(),
            db=db,
        )

    response = asyncio.run(run())

    assert db.commits == 1
    assert install.current_version_id == v2.id
    assert install.version_number == 2
    assert response.skill_id == str(v2.skill_id)
    assert response.version_number == v2.version_number
    assert response.current_platform_version == 2
    assert response.target_platform_version == 2
    assert not hasattr(response, "target_skill_version_id")
    assert response.update_available is False
    assert touched_user_skill is False
    assert touched_agent_bindings is False


def test_update_install_rejects_legacy_skill_version_id(monkeypatch):
    db = FakeDb()
    v1 = _version(1)
    install = _install(v1)

    async def get_by_id_for_user(*args, **kwargs):
        raise AssertionError("legacy numeric update must be rejected before install lookup")

    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_id_for_user", get_by_id_for_user)

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await skills_router.update_skill_install(
                "demo-skill",
                skills_router.SkillInstallUpdateRequest(skill_install_id=install.id, skill_id=str(v1.skill_id), version_number=v1.version_number, skill_version_id=v1.id),
                current_user=_user(),
                db=db,
            )
        return exc_info.value

    exc = asyncio.run(run())

    assert exc.status_code == 400
    assert exc.detail["code"] == "terminal_identity_required"
    assert db.rollbacks == 1


def test_update_preview_uses_selected_install_id_for_same_name_collision(monkeypatch):
    db = FakeDb()
    v1 = _version(1)
    install = _install(v1)

    async def get_by_id_for_user(db_arg, *, user_id, skill_install_id):
        assert skill_install_id == install.id
        return install

    async def list_installs_by_user_and_name(*args, **kwargs):
        raise AssertionError("install-id preview must not use ambiguous name lookup")

    async def get_latest_published_release_for_definition(db_arg, *, skill_definition_id):
        return _release(12, v1)

    async def list_bound_agents_for_install(db_arg, *, user_id, skill_install_id):
        return []

    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_id_for_user", get_by_id_for_user)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "list_by_user_and_name", list_installs_by_user_and_name)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_latest_published_release_for_definition", get_latest_published_release_for_definition)
    monkeypatch.setattr(skills_router.SkillRepository, "list_bound_agents_for_install", list_bound_agents_for_install)
    monkeypatch.setattr(skills_router, "_is_skill_version_artifact_available", lambda version: True)

    async def run():
        return await skills_router.preview_skill_install_update(
            "demo-skill",
            skill_install_id=install.id,
            current_user=_user(),
            db=db,
        )

    response = asyncio.run(run())

    assert response.skill_install_id == install.id
    assert response.status == "up_to_date"


@pytest.mark.parametrize(
    "artifact_uri",
    [
        "artifacts/skills/100/v1/demo-skill",
        "12345678-1234-5678-1234-567812345678/1",
    ],
)
def test_delete_installed_skill_row_does_not_delete_immutable_artifact(tmp_path, monkeypatch, artifact_uri):
    db = FakeDb()
    artifact_dir = tmp_path / artifact_uri
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "SKILL.md").write_text("artifact", encoding="utf-8")
    user_skill = _custom_skill(104, "demo-skill")
    user_skill.skill_definition_id = 100
    user_skill.file_path = artifact_uri
    deleted = {"called": False}

    async def list_user_skills_by_name(db_arg, *, user_id, name):
        return [user_skill]

    async def list_bound_agent_names_for_skill(db_arg, *, user_id, skill_id):
        return []

    async def get_by_user_and_definition(db_arg, *, user_id, skill_definition_id):
        return None

    async def soft_delete_skill(db_arg, *, skill, commit=True):
        deleted["called"] = True
        assert skill is user_skill
        if commit:
            await db_arg.commit()

    monkeypatch.setattr(skills_router, "_get_skills_root_dir", lambda: tmp_path)
    monkeypatch.setattr(skills_router.SkillRepository, "list_user_skills_by_name", list_user_skills_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "list_bound_agent_names_for_skill", list_bound_agent_names_for_skill)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_user_and_definition", get_by_user_and_definition)
    monkeypatch.setattr(skills_router.SkillRepository, "soft_delete_skill", soft_delete_skill)

    async def run():
        await skills_router.delete_skill("demo-skill", current_user=_user(), db=db)

    asyncio.run(run())

    assert deleted["called"] is True
    assert artifact_dir.exists()


def test_name_only_public_lookup_rejects_same_name_ambiguity(monkeypatch):
    first = _public_skill(101, "demo-skill")
    first.skill_definition_id = 201
    second = _public_skill(102, "demo-skill")
    second.skill_definition_id = 202

    async def list_public_skills_by_name(db_arg, *, name):
        return [first, second]

    monkeypatch.setattr(skills_router.SkillRepository, "list_public_skills_by_name", list_public_skills_by_name)

    async def run():
        return await skills_router._get_download_source_skill(
            FakeDb(),
            skill_name="demo-skill",
            owner_user_id=None,
            skill_definition_id=None,
        )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(run())

    assert exc.value.status_code == 400
    assert "ambiguous" in exc.value.detail


def test_fork_claim_lookup_only_accepts_pending_status():
    captured = {}

    class Result:
        def scalar_one_or_none(self):
            return None

    class Db:
        async def execute(self, stmt):
            captured["sql"] = str(stmt.compile(compile_kwargs={"literal_binds": True}))
            return Result()

    async def run():
        return await skills_router.PendingSkillForkClaimRepository.get_valid_claim(
            Db(),
            claim_id=10,
            user_id=7,
            claim_token="token",
            now=datetime(2026, 5, 8, 0, 0, tzinfo=UTC),
        )

    assert asyncio.run(run()) is None
    assert "pending_skill_fork_claims.status = 'pending'" in captured["sql"]
    assert "pending_skill_fork_claims.status IN" not in captured["sql"]


def test_update_preview_is_read_only_and_lists_affected_agents(monkeypatch):
    db = FakeDb()
    v1 = _version(1)
    v2 = _version(2, definition=v1.definition)
    install = _install(v1)
    affected_agent = type("AgentRow", (), {"id": 55, "name": "demo-agent"})()

    async def list_installs_by_user_and_name(db_arg, *, user_id, name):
        return [install]

    async def get_latest_published_release_for_definition(db_arg, *, skill_definition_id):
        assert skill_definition_id == install.skill_definition_id
        return _release(12, v2)

    async def list_bound_agents_for_install(db_arg, *, user_id, skill_install_id):
        assert skill_install_id == install.id
        return [affected_agent]

    monkeypatch.setattr(skills_router.SkillInstallRepository, "list_by_user_and_name", list_installs_by_user_and_name)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_latest_published_release_for_definition", get_latest_published_release_for_definition)
    monkeypatch.setattr(skills_router.SkillRepository, "list_bound_agents_for_install", list_bound_agents_for_install)
    monkeypatch.setattr(skills_router, "_is_skill_version_artifact_available", lambda version: True)

    async def run():
        return await skills_router.preview_skill_install_update(
            "demo-skill",
            current_user=_user(),
            db=db,
        )

    response = asyncio.run(run())

    assert db.commits == 0
    assert install.current_version_id == v1.id
    assert response.status == "available"
    assert response.skill_id == str(v2.skill_id)
    assert response.version_number == v2.version_number
    assert response.current_platform_version == 1
    assert response.target_platform_version == 2
    assert response.release_notes == "Initial release"
    assert response.published_at == "2026-04-28T08:00:00+00:00"
    assert response.publisher == "Alice"
    assert [agent.name for agent in response.affected_agents] == ["demo-agent"]


def test_update_preview_rejects_ambiguous_same_name_installs(monkeypatch):
    db = FakeDb()
    v1 = _version(1)
    install_a = _install(v1)
    install_b = _install(v1)
    install_b.id = 301
    install_b.skill_definition_id = 999

    async def list_installs_by_user_and_name(db_arg, *, user_id, name):
        return [install_a, install_b]

    monkeypatch.setattr(skills_router.SkillInstallRepository, "list_by_user_and_name", list_installs_by_user_and_name)

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await skills_router.preview_skill_install_update(
                "demo-skill",
                current_user=_user(),
                db=db,
            )
        return exc_info.value

    exc = asyncio.run(run())

    assert exc.status_code == 400
    assert "ambiguous" in exc.detail


def test_update_confirm_rejects_missing_artifact_without_fallback(monkeypatch):
    db = FakeDb()
    v1 = _version(1)
    v2 = _version(2, definition=v1.definition)
    install = _install(v1)
    update_called = False

    async def get_by_id_for_user(db_arg, *, user_id, skill_install_id):
        assert skill_install_id == install.id
        return install

    async def get_published_release_by_skill_version(db_arg, *, skill_id, version_number):
        assert skill_id == v2.skill_id
        assert version_number == v2.version_number
        return _release(12, v2)

    async def list_bound_agents_for_install(db_arg, *, user_id, skill_install_id):
        return []

    async def update_current_version(db_arg, *, install, version):
        nonlocal update_called
        update_called = True

    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_id_for_user", get_by_id_for_user)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_published_release_by_skill_version", get_published_release_by_skill_version)
    monkeypatch.setattr(skills_router.SkillRepository, "list_bound_agents_for_install", list_bound_agents_for_install)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "update_current_version", update_current_version)
    monkeypatch.setattr(skills_router, "_is_skill_version_artifact_available", lambda version: False)

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await skills_router.update_skill_install(
                "demo-skill",
                skills_router.SkillInstallUpdateRequest(skill_install_id=install.id, skill_id=str(v2.skill_id), version_number=v2.version_number),
                current_user=_user(),
                db=db,
            )
        return exc_info.value

    exc = asyncio.run(run())

    assert exc.status_code == 409
    assert "unavailable" in exc.detail
    assert install.current_version_id == v1.id
    assert update_called is False
    assert db.commits == 0
    assert db.rollbacks == 1


def test_update_confirm_rejects_missing_current_artifact_without_fallback(monkeypatch):
    db = FakeDb()
    v1 = _version(1)
    v2 = _version(2, definition=v1.definition)
    install = _install(v1)
    update_called = False

    async def get_by_id_for_user(db_arg, *, user_id, skill_install_id):
        assert skill_install_id == install.id
        return install

    async def get_published_release_by_skill_version(db_arg, *, skill_id, version_number):
        assert skill_id == v2.skill_id
        assert version_number == v2.version_number
        return _release(12, v2)

    async def list_bound_agents_for_install(db_arg, *, user_id, skill_install_id):
        return []

    async def update_current_version(db_arg, *, install, version):
        nonlocal update_called
        update_called = True

    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_id_for_user", get_by_id_for_user)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_published_release_by_skill_version", get_published_release_by_skill_version)
    monkeypatch.setattr(skills_router.SkillRepository, "list_bound_agents_for_install", list_bound_agents_for_install)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "update_current_version", update_current_version)
    monkeypatch.setattr(skills_router, "_is_skill_version_artifact_available", lambda version: version.id == v2.id)

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await skills_router.update_skill_install(
                "demo-skill",
                skills_router.SkillInstallUpdateRequest(skill_install_id=install.id, skill_id=str(v2.skill_id), version_number=v2.version_number),
                current_user=_user(),
                db=db,
            )
        return exc_info.value

    exc = asyncio.run(run())

    assert exc.status_code == 409
    assert "Current installed version 1 is unavailable" in exc.detail
    assert install.current_version_id == v1.id
    assert update_called is False
    assert db.commits == 0
    assert db.rollbacks == 1


def test_update_confirm_rejects_selected_version_from_other_definition(monkeypatch):
    db = FakeDb()
    v1 = _version(1)
    other_definition = SkillDefinition(id=999, name="other-skill", display_name="other-skill", description="Other")
    other_version = _version(2, definition=other_definition)
    install = _install(v1)
    update_called = False

    async def get_by_id_for_user(db_arg, *, user_id, skill_install_id):
        assert skill_install_id == install.id
        return install

    async def get_published_release_by_skill_version(*args, **kwargs):
        raise AssertionError("wrong-skill update must be rejected before release lookup")

    async def update_current_version(db_arg, *, install, version):
        nonlocal update_called
        update_called = True

    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_id_for_user", get_by_id_for_user)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_published_release_by_skill_version", get_published_release_by_skill_version)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "update_current_version", update_current_version)

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await skills_router.update_skill_install(
                "demo-skill",
                skills_router.SkillInstallUpdateRequest(skill_install_id=install.id, skill_id=str(other_version.skill_id), version_number=other_version.version_number),
                current_user=_user(),
                db=db,
            )
        return exc_info.value

    exc = asyncio.run(run())

    assert exc.status_code == 404
    assert install.current_version_id == v1.id
    assert update_called is False
    assert db.commits == 0
    assert db.rollbacks == 1


def test_delete_skill_blocks_install_backed_agent_binding(monkeypatch):
    db = FakeDb()
    user_skill = _custom_skill(21, "demo-skill")
    v1 = _version(1)
    user_skill.skill_definition_id = v1.skill_definition_id
    install = _install(v1)
    deleted_directory = False

    async def get_user_skill_by_name(db_arg, *, user_id, name):
        return user_skill

    async def list_user_skills_by_name(db_arg, *, user_id, name):
        return [user_skill]

    async def list_bound_agent_names_for_skill(db_arg, *, user_id, skill_id):
        return []

    async def get_by_user_and_definition(db_arg, *, user_id, skill_definition_id):
        return install

    async def list_bound_agents_for_install(db_arg, *, user_id, skill_install_id):
        assert skill_install_id == install.id
        return [type("AgentRow", (), {"name": "bound-agent"})()]

    async def soft_delete_skill(*args, **kwargs):
        raise AssertionError("bound install-backed skill must not be deleted")

    def delete_skill_directory(*args, **kwargs):
        nonlocal deleted_directory
        deleted_directory = True

    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_name", get_user_skill_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "list_user_skills_by_name", list_user_skills_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "list_bound_agent_names_for_skill", list_bound_agent_names_for_skill)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_user_and_definition", get_by_user_and_definition)
    monkeypatch.setattr(skills_router.SkillRepository, "list_bound_agents_for_install", list_bound_agents_for_install)
    monkeypatch.setattr(skills_router.SkillRepository, "soft_delete_skill", soft_delete_skill)
    monkeypatch.setattr(skills_router, "_delete_skill_directory", delete_skill_directory)

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await skills_router.delete_skill(
                "demo-skill",
                current_user=_user(),
                db=db,
            )
        return exc_info.value

    exc = asyncio.run(run())

    assert exc.status_code == 409
    assert "bound-agent" in exc.detail
    assert deleted_directory is False
