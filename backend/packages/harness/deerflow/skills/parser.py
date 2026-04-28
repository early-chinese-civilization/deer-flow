import logging
import re
from pathlib import Path
from typing import Any

import yaml

from .types import Skill
from .validation import validate_optional_frontmatter_metadata

logger = logging.getLogger(__name__)


def _parse_frontmatter_legacy(front_matter: str) -> dict[str, Any]:
    """Parse legacy SKILL.md frontmatter cases supported by the original loader."""
    metadata: dict[str, Any] = {}
    lines = front_matter.split("\n")
    current_key: str | None = None
    current_value: list[str] = []
    multiline_style: str | None = None
    indent_level: int | None = None

    def flush_multiline() -> None:
        nonlocal current_key, current_value, multiline_style, indent_level
        if current_key is None:
            return
        if multiline_style == "|":
            metadata[current_key] = "\n".join(current_value).rstrip()
        else:
            text = "\n".join(current_value).rstrip()
            metadata[current_key] = re.sub(r"(?<!\n)\n(?!\n)", " ", text)
        current_key = None
        current_value = []
        multiline_style = None
        indent_level = None

    for line in lines:
        if current_key is not None:
            if not line.strip():
                current_value.append("")
                continue

            current_indent = len(line) - len(line.lstrip())
            if indent_level is None:
                if current_indent > 0:
                    indent_level = current_indent
                    current_value.append(line[indent_level:])
                    continue
            elif current_indent >= indent_level:
                current_value.append(line[indent_level:])
                continue

            flush_multiline()

        if not line.strip():
            continue

        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value in (">", "|"):
                current_key = key
                multiline_style = value
                current_value = []
                indent_level = None
            else:
                metadata[key] = value

    flush_multiline()
    return metadata


def _parse_frontmatter_lenient(front_matter: str) -> dict[str, Any] | None:
    """Parse SKILL.md frontmatter while preserving legacy permissive cases."""
    try:
        parsed = yaml.safe_load(front_matter)
        if isinstance(parsed, dict):
            if re.search(r"(?m)^description:\s*[>|]\s*$", front_matter):
                legacy = _parse_frontmatter_legacy(front_matter)
                if isinstance(legacy.get("description"), str):
                    parsed["description"] = legacy["description"]
            return parsed
    except yaml.YAMLError:
        pass

    return _parse_frontmatter_legacy(front_matter)


def _string_metadata(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    if not isinstance(value, str):
        return None
    return value.strip()


def parse_skill_file(skill_file: Path, category: str, relative_path: Path | None = None) -> Skill | None:
    """
    Parse a SKILL.md file and extract metadata.

    Args:
        skill_file: Path to the SKILL.md file
        category: Category of the skill ('public' or 'custom')

    Returns:
        Skill object if parsing succeeds, None otherwise
    """
    if not skill_file.exists() or skill_file.name != "SKILL.md":
        return None

    try:
        content = skill_file.read_text(encoding="utf-8")

        # Extract YAML front matter.
        front_matter_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
        if not front_matter_match:
            return None

        front_matter = front_matter_match.group(1)
        metadata = _parse_frontmatter_lenient(front_matter)
        if not isinstance(metadata, dict):
            return None

        metadata_error = validate_optional_frontmatter_metadata(metadata)
        if metadata_error:
            logger.error("Error parsing skill file %s: %s", skill_file, metadata_error)
            return None

        # Extract required fields.
        name = _string_metadata(metadata, "name")
        description = _string_metadata(metadata, "description")

        if not name or not description:
            return None

        return Skill(
            name=name,
            description=description,
            license=_string_metadata(metadata, "license"),
            skill_dir=skill_file.parent,
            skill_file=skill_file,
            relative_path=relative_path or Path(skill_file.parent.name),
            category=category,
            enabled=True,  # Default to enabled, actual state comes from config file
            package_version=_string_metadata(metadata, "version"),
            author=_string_metadata(metadata, "author"),
            compatibility=_string_metadata(metadata, "compatibility"),
        )

    except Exception as e:
        logger.error("Error parsing skill file %s: %s", skill_file, e)
        return None
