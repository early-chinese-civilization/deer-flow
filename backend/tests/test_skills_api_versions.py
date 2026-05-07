import asyncio
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from app.gateway.db.models import Skill, SkillDefinition, SkillInstall, SkillRelease, SkillVersion, User
from app.gateway.routers import skills as skills_router


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
    return SkillVersion(
        id=200 + version_number,
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
        created_at=datetime(2026, 4, 28, 8, 0, tzinfo=UTC),
    )
    release.skill_version = version
    release.publisher_user = User(id=7, external_auth_id="sub", username="alice", display_name="Alice")
    return release


def test_skill_response_relation_matrix():
    current_user = _user()
    other_user = User(id=8, external_auth_id="sub-8", username="bob", display_name="Bob")
    official_definition = _definition(definition_id=101, owner_user_id=None, source_type="legacy", source_identifier="legacy")
    official_public = _public_skill(101, "official-skill")
    official_public.owner_user_id = None
    official_public.definition = official_definition

    official_response = skills_router._skill_to_response(official_public, skill_version=_version(1, definition=official_definition), current_user_id=current_user.id)
    assert official_response.space == "community"
    assert official_response.source_kind == "official"
    assert official_response.viewer_relation == "official_available"
    assert official_response.owner_display_name == "official"

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

    assert response.space == "community"
    assert response.source_kind == "official"
    assert response.viewer_relation == "official_available"
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

    async def get_latest_release_for_public_skill(db_arg, *, published_skill_id):
        return _release(published_skill_id, public_version)

    async def get_version_by_id(db_arg, *, skill_version_id):
        assert skill_version_id == public_version.id
        return public_version

    async def get_install_by_user_and_name(db_arg, *, user_id, name):
        return _install(install_version)

    async def get_install_by_user_and_definition(db_arg, *, user_id, skill_definition_id):
        return _install(install_version)

    async def get_latest_published_release_for_definition(db_arg, *, skill_definition_id):
        assert skill_definition_id == definition.id
        return _release(public.id, public_version)

    monkeypatch.setattr(skills_router.SkillRepository, "list_visible_skills", list_visible_skills)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_latest_release_for_public_skill", get_latest_release_for_public_skill)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_latest_published_release_for_definition", get_latest_published_release_for_definition)
    monkeypatch.setattr(skills_router.SkillVersionRepository, "get_by_id", get_version_by_id)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_user_and_name", get_install_by_user_and_name)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_user_and_definition", get_install_by_user_and_definition)

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

    async def get_visible_skill_by_name(db_arg, *, user_id, name):
        return public

    async def get_latest_release_for_public_skill(db_arg, *, published_skill_id):
        return release

    async def get_version_by_id(db_arg, *, skill_version_id):
        return version

    async def get_install_by_user_and_definition(db_arg, *, user_id, skill_definition_id):
        return None

    monkeypatch.setattr(skills_router.SkillRepository, "get_visible_skill_by_name", get_visible_skill_by_name)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_latest_release_for_public_skill", get_latest_release_for_public_skill)
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


def test_install_public_skill_records_install_without_copying_public_latest(monkeypatch):
    db = FakeDb()
    public = _public_skill(12, "demo-skill")
    version = _version(1)
    created = _custom_skill(21, "demo-skill")
    created.file_path = version.artifact_uri
    install = _install(version)

    async def get_download_source_skill(db_arg, *, skill_name, owner_user_id):
        return public

    async def get_latest_published_version_by_name(db_arg, *, skill_name):
        return version

    async def get_latest_release_for_public_skill(db_arg, *, published_skill_id):
        return _release(published_skill_id, version)

    async def get_user_skill_by_name(db_arg, *, user_id, name):
        return None

    async def get_user_skill_by_definition(db_arg, *, user_id, skill_definition_id):
        assert skill_definition_id == version.skill_definition_id
        return None

    async def get_install_by_user_and_name(db_arg, *, user_id, name):
        return None

    async def upsert_install(db_arg, *, user_id, definition, version):
        return install

    async def create_skill(db_arg, **kwargs):
        assert kwargs["file_path"] == version.artifact_uri
        assert kwargs["commit"] is False
        return created

    async def get_skill_by_id(db_arg, skill_id):
        return created

    install_lookup_count = 0

    async def get_install_by_user_and_definition(db_arg, *, user_id, skill_definition_id):
        nonlocal install_lookup_count
        assert skill_definition_id == version.skill_definition_id
        install_lookup_count += 1
        return None if install_lookup_count == 1 else install

    monkeypatch.setattr(skills_router, "_get_download_source_skill", get_download_source_skill)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_latest_published_version_by_name", get_latest_published_version_by_name)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_latest_release_for_public_skill", get_latest_release_for_public_skill)
    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_name", get_user_skill_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_definition", get_user_skill_by_definition)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_user_and_name", get_install_by_user_and_name)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "upsert_install", upsert_install)
    monkeypatch.setattr(skills_router.SkillRepository, "create_skill", create_skill)
    monkeypatch.setattr(skills_router.SkillRepository, "get_skill_by_id", get_skill_by_id)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_user_and_definition", get_install_by_user_and_definition)

    async def run():
        return await skills_router.download_skill(
            "demo-skill",
            skills_router.SkillDownloadRequest(overwrite=False),
            current_user=_user(),
            db=db,
        )

    response = asyncio.run(run())

    assert db.commits == 1
    assert response.category == "custom"
    assert response.platform_version == 1
    assert response.skill_install_id == 300
    assert response.version == "1"


def test_install_public_skill_existing_install_without_overwrite_returns_409(monkeypatch):
    db = FakeDb()
    public = _public_skill(12, "demo-skill")
    version = _version(1)

    async def get_download_source_skill(db_arg, *, skill_name, owner_user_id):
        return public

    async def get_latest_published_version_by_name(db_arg, *, skill_name):
        return version

    async def get_latest_release_for_public_skill(db_arg, *, published_skill_id):
        return _release(published_skill_id, version)

    async def get_install_by_user_and_name(db_arg, *, user_id, name):
        return _install(version)

    async def get_install_by_user_and_definition(db_arg, *, user_id, skill_definition_id):
        return _install(version)

    async def get_user_skill_by_name(db_arg, *, user_id, name):
        return None

    async def get_user_skill_by_definition(db_arg, *, user_id, skill_definition_id):
        return None

    monkeypatch.setattr(skills_router, "_get_download_source_skill", get_download_source_skill)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_latest_published_version_by_name", get_latest_published_version_by_name)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_latest_release_for_public_skill", get_latest_release_for_public_skill)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_user_and_name", get_install_by_user_and_name)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "get_by_user_and_definition", get_install_by_user_and_definition)
    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_name", get_user_skill_by_name)
    monkeypatch.setattr(skills_router.SkillRepository, "get_user_skill_by_definition", get_user_skill_by_definition)

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await skills_router.download_skill(
                "demo-skill",
                skills_router.SkillDownloadRequest(overwrite=False),
                current_user=_user(),
                db=db,
            )
        return exc_info.value

    exc = asyncio.run(run())

    assert exc.status_code == 409
    assert db.rollbacks == 1


def test_manual_update_install_switches_current_platform_version(monkeypatch):
    db = FakeDb()
    v1 = _version(1)
    v2 = _version(2, definition=v1.definition)
    install = _install(v1)
    touched_user_skill = False
    touched_agent_bindings = False

    async def list_installs_by_user_and_name(db_arg, *, user_id, name):
        return [install]

    async def get_published_release_by_version_id(db_arg, *, skill_version_id):
        assert skill_version_id == v2.id
        return _release(12, v2)

    async def update_current_version(db_arg, *, install, version):
        install.current_version = version
        install.current_version_id = version.id
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

    monkeypatch.setattr(skills_router.SkillInstallRepository, "list_by_user_and_name", list_installs_by_user_and_name)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_published_release_by_version_id", get_published_release_by_version_id)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "update_current_version", update_current_version)
    monkeypatch.setattr(skills_router.SkillRepository, "list_bound_agents_for_install", list_bound_agents_for_install)
    monkeypatch.setattr(skills_router.SkillRepository, "create_skill", create_skill)
    monkeypatch.setattr(skills_router.SkillRepository, "rebind_agent_skills", rebind_agent_skills)
    monkeypatch.setattr(skills_router, "_is_skill_version_artifact_available", lambda version: True)

    async def run():
        return await skills_router.update_skill_install(
            "demo-skill",
            skills_router.SkillInstallUpdateRequest(skill_version_id=v2.id),
            current_user=_user(),
            db=db,
        )

    response = asyncio.run(run())

    assert db.commits == 1
    assert install.current_version_id == v2.id
    assert response.current_platform_version == 1
    assert response.target_platform_version == 2
    assert response.update_available is True
    assert touched_user_skill is False
    assert touched_agent_bindings is False


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

    async def list_installs_by_user_and_name(db_arg, *, user_id, name):
        return [install]

    async def get_latest_published_release_for_definition(db_arg, *, skill_definition_id):
        assert skill_definition_id == install.skill_definition_id
        return _release(12, v2)

    async def list_bound_agents_for_install(db_arg, *, user_id, skill_install_id):
        return []

    async def update_current_version(db_arg, *, install, version):
        nonlocal update_called
        update_called = True

    monkeypatch.setattr(skills_router.SkillInstallRepository, "list_by_user_and_name", list_installs_by_user_and_name)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_latest_published_release_for_definition", get_latest_published_release_for_definition)
    monkeypatch.setattr(skills_router.SkillRepository, "list_bound_agents_for_install", list_bound_agents_for_install)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "update_current_version", update_current_version)
    monkeypatch.setattr(skills_router, "_is_skill_version_artifact_available", lambda version: False)

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await skills_router.update_skill_install(
                "demo-skill",
                None,
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

    async def list_installs_by_user_and_name(db_arg, *, user_id, name):
        return [install]

    async def get_latest_published_release_for_definition(db_arg, *, skill_definition_id):
        return _release(12, v2)

    async def list_bound_agents_for_install(db_arg, *, user_id, skill_install_id):
        return []

    async def update_current_version(db_arg, *, install, version):
        nonlocal update_called
        update_called = True

    monkeypatch.setattr(skills_router.SkillInstallRepository, "list_by_user_and_name", list_installs_by_user_and_name)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_latest_published_release_for_definition", get_latest_published_release_for_definition)
    monkeypatch.setattr(skills_router.SkillRepository, "list_bound_agents_for_install", list_bound_agents_for_install)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "update_current_version", update_current_version)
    monkeypatch.setattr(skills_router, "_is_skill_version_artifact_available", lambda version: version.id == v2.id)

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await skills_router.update_skill_install(
                "demo-skill",
                None,
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

    async def list_installs_by_user_and_name(db_arg, *, user_id, name):
        return [install]

    async def get_published_release_by_version_id(db_arg, *, skill_version_id):
        assert skill_version_id == other_version.id
        return _release(12, other_version)

    async def update_current_version(db_arg, *, install, version):
        nonlocal update_called
        update_called = True

    monkeypatch.setattr(skills_router.SkillInstallRepository, "list_by_user_and_name", list_installs_by_user_and_name)
    monkeypatch.setattr(skills_router.SkillReleaseRepository, "get_published_release_by_version_id", get_published_release_by_version_id)
    monkeypatch.setattr(skills_router.SkillInstallRepository, "update_current_version", update_current_version)

    async def run():
        with pytest.raises(HTTPException) as exc_info:
            await skills_router.update_skill_install(
                "demo-skill",
                skills_router.SkillInstallUpdateRequest(skill_version_id=other_version.id),
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
