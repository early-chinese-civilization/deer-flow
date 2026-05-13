from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

PLATFORM_GENERATED_CONTENT_PATHS = frozenset()


def split_skill_md_frontmatter(content: str) -> tuple[dict, str]:
    """Return SKILL.md frontmatter and body text."""
    if not content.startswith("---"):
        raise ValueError("No YAML frontmatter found")
    lines = content.splitlines(keepends=True)
    end_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = index
            break
    if end_index is None:
        raise ValueError("Invalid frontmatter format")
    frontmatter_text = "".join(lines[1:end_index])
    frontmatter = yaml.safe_load(frontmatter_text)
    if not isinstance(frontmatter, dict):
        raise ValueError("Frontmatter must be a YAML dictionary")
    body = "".join(lines[end_index + 1 :])
    return frontmatter, body


def canonical_skill_md_bytes(skill_md_path: Path) -> bytes:
    """Canonicalize SKILL.md for platform content hashing.

    The source package ``version`` key is intentionally excluded so changing
    only package metadata does not mint a new platform SkillVersion.
    """
    frontmatter, body = split_skill_md_frontmatter(skill_md_path.read_text(encoding="utf-8"))
    frontmatter.pop("version", None)
    canonical_frontmatter = yaml.safe_dump(frontmatter, sort_keys=True, allow_unicode=False).strip()
    return f"---\n{canonical_frontmatter}\n---\n{body}".encode()


def hash_skill_file_manifest(skill_dir: Path) -> str:
    """Compute the raw file-manifest hash for an on-disk skill directory."""
    manifest_hash = hashlib.sha256()
    for path in sorted(item for item in skill_dir.rglob("*") if item.is_file()):
        relative = path.relative_to(skill_dir).as_posix()
        raw_bytes = path.read_bytes()
        manifest_hash.update(relative.encode("utf-8"))
        manifest_hash.update(b"\0")
        manifest_hash.update(hashlib.sha256(raw_bytes).hexdigest().encode("ascii"))
        manifest_hash.update(b"\0")
    return manifest_hash.hexdigest()


def hash_skill_directory(skill_dir: Path) -> tuple[str, str]:
    """Compute canonical content and raw file-manifest hashes for a skill dir."""
    canonical_hash = hashlib.sha256()
    for path in sorted(item for item in skill_dir.rglob("*") if item.is_file()):
        relative = path.relative_to(skill_dir).as_posix()
        if relative in PLATFORM_GENERATED_CONTENT_PATHS:
            continue
        raw_bytes = path.read_bytes()
        canonical_bytes = canonical_skill_md_bytes(path) if relative == "SKILL.md" else raw_bytes
        canonical_hash.update(relative.encode("utf-8"))
        canonical_hash.update(b"\0")
        canonical_hash.update(canonical_bytes)
        canonical_hash.update(b"\0")
    return canonical_hash.hexdigest(), hash_skill_file_manifest(skill_dir)
