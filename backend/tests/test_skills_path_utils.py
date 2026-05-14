from uuid import UUID

import pytest

from deerflow.skills.path_utils import build_terminal_skill_version_relative_path, build_terminal_skill_virtual_path, is_terminal_skill_version_relative_path, normalize_skill_file_path


def test_build_terminal_skill_version_relative_path_normalizes_uuid_and_version():
    relative_path = build_terminal_skill_version_relative_path(
        UUID("12345678-1234-5678-1234-567812345678"),
        "2",
    )

    assert relative_path == "12345678-1234-5678-1234-567812345678/2"


def test_build_terminal_skill_virtual_path_uses_canonical_mount_path():
    virtual_path = build_terminal_skill_virtual_path(
        UUID("12345678-1234-5678-1234-567812345678"),
        "2",
        container_base_path="/mnt/skills/",
    )

    assert virtual_path == "/mnt/skills/12345678-1234-5678-1234-567812345678/2/SKILL.md"


@pytest.mark.parametrize(
    ("skill_id", "version_number"),
    [
        ("not-a-uuid", 1),
        ("12345678-1234-5678-1234-567812345678", 0),
        ("12345678-1234-5678-1234-567812345678", -1),
        ("12345678-1234-5678-1234-567812345678", True),
    ],
)
def test_build_terminal_skill_version_relative_path_rejects_invalid_identity(skill_id, version_number):
    with pytest.raises(ValueError):
        build_terminal_skill_version_relative_path(skill_id, version_number)


@pytest.mark.parametrize(
    ("file_path", "expected"),
    [
        ("12345678-1234-5678-1234-567812345678/2", True),
        ("12345678-1234-5678-1234-567812345678/02", False),
        ("12345678-1234-5678-1234-567812345678/2/SKILL.md", False),
        ("public/demo-skill", False),
    ],
)
def test_is_terminal_skill_version_relative_path_requires_exact_terminal_shape(file_path, expected):
    assert is_terminal_skill_version_relative_path(file_path) is expected


def test_normalize_skill_file_path_rewrites_legacy_custom_to_user_private_path():
    normalized = normalize_skill_file_path(
        "custom/demo-skill",
        user_id=7,
        skill_name="demo-skill",
    )

    assert normalized == "7/demo-skill"


def test_normalize_skill_file_path_rewrites_nested_legacy_custom_to_user_private_path():
    normalized = normalize_skill_file_path(
        "custom/demo-skill/SKILL.md",
        user_id=7,
        skill_name="demo-skill",
    )

    assert normalized == "7/demo-skill"
