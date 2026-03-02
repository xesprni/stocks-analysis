from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from market_reporter.modules.analysis.agent.skill_catalog import SkillCatalog


class SkillCatalogTest(unittest.TestCase):
    def test_catalog_parses_frontmatter_and_lazy_loads_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            skill_dir = root / "skills" / "demo-skill"
            skill_dir.mkdir(parents=True, exist_ok=True)
            skill_file = skill_dir / "SKILL.md"
            skill_file.write_text(
                "\n".join(
                    [
                        "---",
                        "name: demo-skill",
                        "description: Demonstration skill",
                        "---",
                        "",
                        "# Demo",
                        "content",
                    ]
                ),
                encoding="utf-8",
            )

            catalog = SkillCatalog(root_dir=root / "skills")
            payloads = catalog.list_skill_payloads()
            self.assertEqual(len(payloads), 1)
            self.assertEqual(payloads[0]["name"], "demo-skill")
            self.assertEqual(payloads[0]["description"], "Demonstration skill")

            content = catalog.load_skill_content("demo-skill")
            self.assertIsNotNone(content)
            self.assertIn("# Demo", str(content))

    def test_missing_skill_returns_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            catalog = SkillCatalog(root_dir=Path(tmpdir) / "skills")
            self.assertIsNone(catalog.load_skill_content("missing"))


if __name__ == "__main__":
    unittest.main()
