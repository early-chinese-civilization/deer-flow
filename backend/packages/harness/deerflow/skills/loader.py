import logging
import os
from pathlib import Path

from deerflow.config.paths import get_paths

from .parser import parse_skill_file
from .path_utils import LEGACY_CUSTOM_SKILLS_DIR, PUBLIC_SKILLS_DIR
from .types import Skill

logger = logging.getLogger(__name__)


def get_skills_root_path() -> Path:
    """
    Get the root path of the skills directory.

    Returns:
        Path to the shared skills directory.
    """
    return get_paths().shared_fs_root / "skills"


def load_skills(skills_path: Path | None = None, use_config: bool = True, enabled_only: bool = False) -> list[Skill]:
    """
    Load all skills from the skills directory.

    Scans public, legacy custom, and per-user private skill directories,
    parsing SKILL.md files to extract metadata. The enabled state is
    determined by the skills_state_config.json file.

    Args:
        skills_path: Optional custom path to skills directory.
                     If not provided and use_config is True, uses path from config.
                     Otherwise defaults to the shared skills directory.
        use_config: Whether to load skills path from config (default: True)
        enabled_only: If True, only return enabled skills (default: False)

    Returns:
        List of Skill objects, sorted by name
    """
    if skills_path is None:
        if use_config:
            try:
                from deerflow.config import get_app_config

                config = get_app_config()
                skills_path = config.skills.get_skills_path()
            except Exception:
                skills_path = get_skills_root_path()
        else:
            skills_path = get_skills_root_path()

    if not skills_path.exists():
        return []

    skills: list[Skill] = []
    scan_roots: list[tuple[str, Path]] = []

    public_path = skills_path / PUBLIC_SKILLS_DIR
    if public_path.exists() and public_path.is_dir():
        scan_roots.append(("public", public_path))

    legacy_custom_path = skills_path / LEGACY_CUSTOM_SKILLS_DIR
    if legacy_custom_path.exists() and legacy_custom_path.is_dir():
        scan_roots.append(("custom", legacy_custom_path))

    for child in sorted(skills_path.iterdir(), key=lambda item: item.name.lower()):
        if not child.is_dir() or child.name.startswith(".") or child.name in {PUBLIC_SKILLS_DIR, LEGACY_CUSTOM_SKILLS_DIR}:
            continue
        scan_roots.append(("custom", child))

    for category, scan_root in scan_roots:
        for current_root, dir_names, file_names in os.walk(scan_root, followlinks=True):
            dir_names[:] = sorted(name for name in dir_names if not name.startswith("."))
            if "SKILL.md" not in file_names:
                continue

            skill_file = Path(current_root) / "SKILL.md"
            relative_path = skill_file.parent.relative_to(skills_path)
            skill = parse_skill_file(skill_file, category=category, relative_path=relative_path)
            if skill:
                skills.append(skill)

    try:
        from deerflow.config.extensions_config import ExtensionsConfig

        extensions_config = ExtensionsConfig.from_file()
        for skill in skills:
            skill.enabled = extensions_config.is_skill_enabled(skill.name, skill.category)
    except Exception as e:
        logger.warning("Failed to load extensions config: %s", e)

    if enabled_only:
        skills = [skill for skill in skills if skill.enabled]

    skills.sort(key=lambda s: s.name)
    return skills
