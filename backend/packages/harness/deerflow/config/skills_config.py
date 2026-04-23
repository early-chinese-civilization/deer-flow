import os
from pathlib import Path

from pydantic import BaseModel, Field


class SkillsConfig(BaseModel):
    """Configuration for skills system"""

    path: str | None = Field(
        default=None,
        description="Path to the shared skills directory. If omitted, defaults to DEER_FLOW_SHARED_FS_ROOT/skills.",
    )
    container_path: str = Field(
        default="/mnt/skills",
        description="Path where skills are mounted in the sandbox container",
    )

    def get_skills_path(self) -> Path:
        """
        Get the resolved skills directory path.

        Returns:
            Path to the skills directory
        """
        if self.path:
            # Use configured path (can be absolute or relative)
            path = Path(self.path)
            if not path.is_absolute():
                # If relative, resolve from current working directory
                path = Path.cwd() / path
            return path.resolve()
        if shared_root := os.getenv("DEER_FLOW_SHARED_FS_ROOT"):
            return (Path(shared_root) / "skills").resolve()
        else:
            # Default: shared-fs root + /skills
            from deerflow.skills.loader import get_skills_root_path

            return get_skills_root_path()

    def get_skill_container_path(self, skill_name: str, category: str = "public") -> str:
        """
        Get the stable virtual container path for a specific skill.

        Args:
            skill_name: Name of the skill (directory name)
            category: Deprecated. Runtime virtual paths are category-agnostic.

        Returns:
            Full path to the skill in the container
        """
        del category
        return f"{self.container_path.rstrip('/')}/{skill_name}"
