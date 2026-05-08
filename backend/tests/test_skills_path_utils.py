from deerflow.skills.path_utils import normalize_skill_file_path


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
