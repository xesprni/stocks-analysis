from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pydantic schemas for the API layer
# ---------------------------------------------------------------------------


class SkillView(BaseModel):
    name: str
    description: str


class SkillDetailView(SkillView):
    content: str


class SkillCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1)
    content: str = Field(default="")


class SkillUpdateRequest(BaseModel):
    description: Optional[str] = None
    content: Optional[str] = None


# ---------------------------------------------------------------------------
# Internal data class
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SkillSummary:
    name: str
    description: str
    path: Path
    mode: str = ""
    require_symbol: bool = False
    aliases: tuple = ()


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

    def load_skill_body(self, name: str) -> Optional[str]:
        """Load only the body (content after frontmatter) of a skill."""
        full_text = self.load_skill_content(name)
        if full_text is None:
            return None
        return self._extract_body(full_text)

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

        mode = str(metadata.get("mode") or "").strip()
        require_symbol = bool(metadata.get("require_symbol", False))
        raw_aliases = metadata.get("aliases")
        if isinstance(raw_aliases, list):
            aliases = tuple(str(a).strip() for a in raw_aliases if str(a).strip())
        elif isinstance(raw_aliases, str):
            aliases = tuple(a.strip() for a in raw_aliases.split(",") if a.strip())
        else:
            aliases = ()

        return SkillSummary(
            name=name,
            description=description,
            path=path,
            mode=mode,
            require_symbol=require_symbol,
            aliases=aliases,
        )

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------

    def create_skill(self, name: str, description: str, content: str) -> SkillSummary:
        slug = self._slugify(name)
        if not slug:
            raise ValueError("Skill name must contain at least one alphanumeric character.")
        key = slug.lower()
        if key in self._skills_by_name:
            raise ValueError(f"Skill already exists: {slug}")

        self.root_dir.mkdir(parents=True, exist_ok=True)
        skill_dir = self.root_dir / slug
        skill_dir.mkdir(exist_ok=True)

        skill_file = skill_dir / "SKILL.md"
        full_content = self._render_skill_md(name=slug, description=description, body=content)
        skill_file.write_text(full_content, encoding="utf-8")

        summary = SkillSummary(name=slug, description=description, path=skill_file)
        self._skills_by_name[key] = summary
        return summary

    def update_skill(self, name: str, description: Optional[str], content: Optional[str]) -> SkillSummary:
        key = (name or "").strip().lower()
        existing = self._skills_by_name.get(key)
        if existing is None:
            raise FileNotFoundError(f"Skill not found: {name}")

        # Read existing file to extract current frontmatter values
        old_text = existing.path.read_text(encoding="utf-8")
        old_meta = self._parse_frontmatter(old_text)
        old_body = self._extract_body(old_text)

        new_description = description if description is not None else str(old_meta.get("description", ""))
        new_body = content if content is not None else old_body

        full_content = self._render_skill_md(name=existing.name, description=new_description, body=new_body)
        existing.path.write_text(full_content, encoding="utf-8")

        updated = SkillSummary(name=existing.name, description=new_description, path=existing.path)
        self._skills_by_name[key] = updated
        return updated

    def delete_skill(self, name: str) -> bool:
        key = (name or "").strip().lower()
        existing = self._skills_by_name.get(key)
        if existing is None:
            return False

        skill_dir = existing.path.parent
        if skill_dir.is_dir():
            shutil.rmtree(skill_dir)

        del self._skills_by_name[key]
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _slugify(name: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9_-]", "-", name.strip()).strip("-")
        return re.sub(r"-+", "-", slug)

    @staticmethod
    def _render_skill_md(
        name: str,
        description: str,
        body: str,
        *,
        mode: str = "",
        require_symbol: bool = False,
        aliases: tuple = (),
    ) -> str:
        frontmatter_data: Dict[str, object] = {
            "name": name,
            "description": description,
        }
        if mode:
            frontmatter_data["mode"] = mode
        if require_symbol:
            frontmatter_data["require_symbol"] = require_symbol
        if aliases:
            frontmatter_data["aliases"] = list(aliases)
        frontmatter = yaml.safe_dump(
            frontmatter_data,
            allow_unicode=True,
            sort_keys=False,
        ).strip()
        return f"---\n{frontmatter}\n---\n\n{body.strip()}\n"

    @staticmethod
    def _extract_body(text: str) -> str:
        if not text.startswith("---"):
            return text.strip()
        lines = text.splitlines()
        end_index = None
        for idx in range(1, len(lines)):
            if lines[idx].strip() == "---":
                end_index = idx
                break
        if end_index is None:
            return text.strip()
        return "\n".join(lines[end_index + 1 :]).strip()

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
