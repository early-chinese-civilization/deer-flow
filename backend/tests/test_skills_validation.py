"""Tests for skill frontmatter validation.

Consolidates all _validate_skill_frontmatter tests (previously split across
test_skills_router.py and this module) into a single dedicated module.
"""

from pathlib import Path

from app.gateway.routers.skills import ALLOWED_SKILL_FRONTMATTER_KEYS, _validate_skill_directory
from deerflow.skills.validation import ALLOWED_FRONTMATTER_PROPERTIES, _validate_skill_frontmatter


def _write_skill(tmp_path: Path, content: str) -> Path:
    """Write a SKILL.md file and return its parent directory."""
    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text(content, encoding="utf-8")
    return tmp_path


class TestValidateSkillFrontmatter:
    def test_valid_minimal_skill(self, tmp_path):
        skill_dir = _write_skill(
            tmp_path,
            "---\nname: my-skill\ndescription: A valid skill\n---\n\nBody\n",
        )
        valid, msg, name = _validate_skill_frontmatter(skill_dir)
        assert valid is True
        assert msg == "Skill is valid!"
        assert name == "my-skill"

    def test_valid_with_all_allowed_fields(self, tmp_path):
        skill_dir = _write_skill(
            tmp_path,
            "---\nname: my-skill\ndescription: A skill\nlicense: MIT\nversion: '1.0'\nauthor: test\n---\n\nBody\n",
        )
        valid, msg, name = _validate_skill_frontmatter(skill_dir)
        assert valid is True
        assert msg == "Skill is valid!"
        assert name == "my-skill"

    def test_gateway_accepts_standard_optional_metadata_fields(self, tmp_path):
        skill_dir = _write_skill(
            tmp_path,
            "---\nname: my-skill\ndescription: A skill\nversion: '1.0'\nauthor: test author\ncompatibility: DeerFlow >= 0.1\n---\n\nBody\n",
        )

        name, description = _validate_skill_directory(skill_dir)

        assert name == "my-skill"
        assert description == "A skill"

    def test_gateway_allowed_keys_match_harness_metadata_keys(self):
        assert {"version", "author", "compatibility"}.issubset(ALLOWED_SKILL_FRONTMATTER_KEYS)
        assert ALLOWED_FRONTMATTER_PROPERTIES == ALLOWED_SKILL_FRONTMATTER_KEYS

    def test_rejects_non_string_version_in_harness_and_gateway(self, tmp_path):
        skill_dir = _write_skill(
            tmp_path,
            "---\nname: my-skill\ndescription: A skill\nversion: 1.0\n---\n\nBody\n",
        )

        valid, msg, name = _validate_skill_frontmatter(skill_dir)
        assert valid is False
        assert "Version must be a string" in msg
        assert name is None

        try:
            _validate_skill_directory(skill_dir)
        except ValueError as exc:
            assert "Version must be a string" in str(exc)
        else:
            raise AssertionError("Gateway validation accepted a non-string version")

    def test_missing_skill_md(self, tmp_path):
        valid, msg, name = _validate_skill_frontmatter(tmp_path)
        assert valid is False
        assert "not found" in msg
        assert name is None

    def test_no_frontmatter(self, tmp_path):
        skill_dir = _write_skill(tmp_path, "# Just markdown\n\nNo front matter.\n")
        valid, msg, _ = _validate_skill_frontmatter(skill_dir)
        assert valid is False
        assert "frontmatter" in msg.lower()

    def test_invalid_yaml(self, tmp_path):
        skill_dir = _write_skill(tmp_path, "---\n[invalid yaml: {{\n---\n\nBody\n")
        valid, msg, _ = _validate_skill_frontmatter(skill_dir)
        assert valid is False
        assert "YAML" in msg

    def test_missing_name(self, tmp_path):
        skill_dir = _write_skill(
            tmp_path,
            "---\ndescription: A skill without a name\n---\n\nBody\n",
        )
        valid, msg, _ = _validate_skill_frontmatter(skill_dir)
        assert valid is False
        assert "name" in msg.lower()

    def test_missing_description(self, tmp_path):
        skill_dir = _write_skill(
            tmp_path,
            "---\nname: my-skill\n---\n\nBody\n",
        )
        valid, msg, _ = _validate_skill_frontmatter(skill_dir)
        assert valid is False
        assert "description" in msg.lower()

    def test_unexpected_keys_rejected(self, tmp_path):
        skill_dir = _write_skill(
            tmp_path,
            "---\nname: my-skill\ndescription: test\ncustom-field: bad\n---\n\nBody\n",
        )
        valid, msg, _ = _validate_skill_frontmatter(skill_dir)
        assert valid is False
        assert "custom-field" in msg

    def test_name_must_be_hyphen_case(self, tmp_path):
        skill_dir = _write_skill(
            tmp_path,
            "---\nname: MySkill\ndescription: test\n---\n\nBody\n",
        )
        valid, msg, _ = _validate_skill_frontmatter(skill_dir)
        assert valid is False
        assert "hyphen-case" in msg

    def test_name_no_leading_hyphen(self, tmp_path):
        skill_dir = _write_skill(
            tmp_path,
            "---\nname: -my-skill\ndescription: test\n---\n\nBody\n",
        )
        valid, msg, _ = _validate_skill_frontmatter(skill_dir)
        assert valid is False
        assert "hyphen" in msg

    def test_name_no_trailing_hyphen(self, tmp_path):
        skill_dir = _write_skill(
            tmp_path,
            "---\nname: my-skill-\ndescription: test\n---\n\nBody\n",
        )
        valid, msg, _ = _validate_skill_frontmatter(skill_dir)
        assert valid is False
        assert "hyphen" in msg

    def test_name_no_consecutive_hyphens(self, tmp_path):
        skill_dir = _write_skill(
            tmp_path,
            "---\nname: my--skill\ndescription: test\n---\n\nBody\n",
        )
        valid, msg, _ = _validate_skill_frontmatter(skill_dir)
        assert valid is False
        assert "hyphen" in msg

    def test_name_too_long(self, tmp_path):
        long_name = "a" * 65
        skill_dir = _write_skill(
            tmp_path,
            f"---\nname: {long_name}\ndescription: test\n---\n\nBody\n",
        )
        valid, msg, _ = _validate_skill_frontmatter(skill_dir)
        assert valid is False
        assert "too long" in msg.lower()

    def test_description_no_angle_brackets(self, tmp_path):
        skill_dir = _write_skill(
            tmp_path,
            "---\nname: my-skill\ndescription: Has <html> tags\n---\n\nBody\n",
        )
        valid, msg, _ = _validate_skill_frontmatter(skill_dir)
        assert valid is False
        assert "angle brackets" in msg.lower()

    def test_description_too_long(self, tmp_path):
        long_desc = "a" * 1025
        skill_dir = _write_skill(
            tmp_path,
            f"---\nname: my-skill\ndescription: {long_desc}\n---\n\nBody\n",
        )
        valid, msg, _ = _validate_skill_frontmatter(skill_dir)
        assert valid is False
        assert "too long" in msg.lower()

    def test_empty_name_rejected(self, tmp_path):
        skill_dir = _write_skill(
            tmp_path,
            "---\nname: ''\ndescription: test\n---\n\nBody\n",
        )
        valid, msg, _ = _validate_skill_frontmatter(skill_dir)
        assert valid is False
        assert "empty" in msg.lower()

    def test_allowed_properties_constant(self):
        assert "name" in ALLOWED_FRONTMATTER_PROPERTIES
        assert "description" in ALLOWED_FRONTMATTER_PROPERTIES
        assert "license" in ALLOWED_FRONTMATTER_PROPERTIES

    def test_reads_utf8_on_windows_locale(self, tmp_path, monkeypatch):
        skill_dir = _write_skill(
            tmp_path,
            '---\nname: demo-skill\ndescription: "Curly quotes: \u201cutf8\u201d"\n---\n\n# Demo Skill\n',
        )
        original_read_text = Path.read_text

        def read_text_with_gbk_default(self, *args, **kwargs):
            kwargs.setdefault("encoding", "gbk")
            return original_read_text(self, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", read_text_with_gbk_default)

        valid, msg, name = _validate_skill_frontmatter(skill_dir)
        assert valid is True
        assert msg == "Skill is valid!"
        assert name == "demo-skill"
