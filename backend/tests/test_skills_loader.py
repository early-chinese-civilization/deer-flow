"""Tests for recursive skills loading."""

from pathlib import Path

from deerflow.config.paths import get_paths
from deerflow.skills.loader import get_skills_root_path, load_skills


def _write_skill(skill_dir: Path, name: str, description: str, extra_frontmatter: str = "") -> None:
    """Write a minimal SKILL.md for tests."""
    skill_dir.mkdir(parents=True, exist_ok=True)
    content = f"---\nname: {name}\ndescription: {description}\n{extra_frontmatter}---\n\n# {name}\n"
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


def test_get_skills_root_path_points_to_shared_fs_skills():
    """get_skills_root_path() should point to the shared `.deer-flow/skills` root."""
    path = get_skills_root_path()
    assert path == get_paths().shared_fs_root / "skills"


def test_load_skills_discovers_public_and_user_scoped_skills_with_virtual_paths(tmp_path: Path):
    """Nested public and per-user skills should be discovered with unified virtual paths."""
    skills_root = tmp_path / "skills"

    _write_skill(skills_root / "public" / "root-skill", "root-skill", "Root skill")
    _write_skill(skills_root / "public" / "parent" / "child-skill", "child-skill", "Child skill")
    _write_skill(skills_root / "7" / "team-helper", "team-helper", "Team helper")

    skills = load_skills(skills_path=skills_root, use_config=False, enabled_only=False)
    by_name = {skill.name: skill for skill in skills}

    assert {"root-skill", "child-skill", "team-helper"} <= set(by_name)

    root_skill = by_name["root-skill"]
    child_skill = by_name["child-skill"]
    team_skill = by_name["team-helper"]

    assert root_skill.skill_path == "public/root-skill"
    assert root_skill.get_container_file_path() == "/mnt/skills/root-skill/SKILL.md"

    assert child_skill.skill_path == "public/parent/child-skill"
    assert child_skill.get_container_file_path() == "/mnt/skills/child-skill/SKILL.md"

    assert team_skill.skill_path == "7/team-helper"
    assert team_skill.get_container_file_path() == "/mnt/skills/team-helper/SKILL.md"


def test_load_skills_parses_optional_package_metadata(tmp_path: Path):
    """Optional SKILL.md metadata should be available to API/release callers without reparsing."""
    skills_root = tmp_path / "skills"
    _write_skill(
        skills_root / "public" / "versioned-skill",
        "versioned-skill",
        "Versioned skill",
        extra_frontmatter="version: v1.2.3\nauthor: Test Author\ncompatibility: DeerFlow >= 0.1\n",
    )

    skills = load_skills(skills_path=skills_root, use_config=False, enabled_only=False)

    assert len(skills) == 1
    assert skills[0].package_version == "v1.2.3"
    assert skills[0].author == "Test Author"
    assert skills[0].compatibility == "DeerFlow >= 0.1"


def test_load_skills_skips_hidden_directories(tmp_path: Path):
    """Hidden directories should be excluded from recursive discovery."""
    skills_root = tmp_path / "skills"

    _write_skill(skills_root / "public" / "visible" / "ok-skill", "ok-skill", "Visible skill")
    _write_skill(
        skills_root / "public" / "visible" / ".hidden" / "secret-skill",
        "secret-skill",
        "Hidden skill",
    )

    skills = load_skills(skills_path=skills_root, use_config=False, enabled_only=False)
    names = {skill.name for skill in skills}

    assert "ok-skill" in names
    assert "secret-skill" not in names


def test_load_skills_keeps_legacy_custom_directory_compatibility_with_warning(tmp_path: Path, caplog):
    """Legacy `custom/` skills should load only as explicit compatibility."""
    skills_root = tmp_path / "skills"
    _write_skill(skills_root / "custom" / "legacy-tool", "legacy-tool", "Legacy custom skill")

    with caplog.at_level("WARNING", logger="deerflow.skills.loader"):
        skills = load_skills(skills_path=skills_root, use_config=False, enabled_only=False)

    assert [skill.name for skill in skills] == ["legacy-tool"]
    assert skills[0].category == "custom"
    assert skills[0].skill_path == "custom/legacy-tool"
    assert "legacy custom/" in caplog.text
    assert "compatibility only" in caplog.text
