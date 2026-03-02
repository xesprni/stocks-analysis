from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import yaml


@dataclass(frozen=True)
class SkillSummary:
    name: str
    description: str
    path: Path


class SkillCatalog:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self._skills_by_name: Dict[str, SkillSummary] = {}
        self.reload()

    @classmethod
    def from_default_path(cls) -> "SkillCatalog":
        project_root = Path(__file__).resolve().parents[4]
        return cls(root_dir=project_root / "skills")

    def reload(self) -> None:
        self._skills_by_name = {}
        if not self.root_dir.exists() or not self.root_dir.is_dir():
            return

        for skill_file in sorted(self.root_dir.glob("*/SKILL.md")):
            summary = self._parse_skill_file(skill_file)
            if summary is None:
                continue
            key = summary.name.lower()
            existing = self._skills_by_name.get(key)
            if existing is not None and existing.path != summary.path:
                raise ValueError(f"Duplicate skill name in catalog: {summary.name}")
            self._skills_by_name[key] = summary

    def list_skills(self) -> List[SkillSummary]:
        return sorted(self._skills_by_name.values(), key=lambda item: item.name)

    def list_skill_payloads(self) -> List[Dict[str, str]]:
        return [
            {
                "name": item.name,
                "description": item.description,
            }
            for item in self.list_skills()
        ]

    def get_summary(self, name: str) -> Optional[SkillSummary]:
        key = (name or "").strip().lower()
        if not key:
            return None
        return self._skills_by_name.get(key)

    def load_skill_content(self, name: str) -> Optional[str]:
        summary = self.get_summary(name)
        if summary is None:
            return None
        return summary.path.read_text(encoding="utf-8")

    @staticmethod
    def _parse_skill_file(path: Path) -> Optional[SkillSummary]:
        text = path.read_text(encoding="utf-8")
        metadata = SkillCatalog._parse_frontmatter(text)

        raw_name = str(metadata.get("name") or "").strip()
        name = raw_name or path.parent.name
        if not name:
            return None

        description = str(metadata.get("description") or "").strip()
        if not description:
            description = f"Skill loaded from {path.parent.name}"

        return SkillSummary(name=name, description=description, path=path)

    @staticmethod
    def _parse_frontmatter(text: str) -> Dict[str, object]:
        if not text.startswith("---"):
            return {}
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            return {}

        end_index = None
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                end_index = index
                break
        if end_index is None:
            return {}

        block = "\n".join(lines[1:end_index]).strip()
        if not block:
            return {}

        parsed = yaml.safe_load(block)
        if isinstance(parsed, dict):
            return parsed
        return {}
