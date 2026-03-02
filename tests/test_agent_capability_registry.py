from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from market_reporter.modules.analysis.agent.capability_registry import (
    CapabilityRegistry,
)
from market_reporter.modules.analysis.agent.skill_catalog import SkillCatalog
from market_reporter.modules.analysis.agent.subagents import SubAgentRegistry


class CapabilityRegistryTest(unittest.TestCase):
    def test_default_registry_contains_tool_skill_subagent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            skill_dir = root / "skills" / "alpha"
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / "SKILL.md").write_text(
                "\n".join(
                    [
                        "---",
                        "name: alpha",
                        "description: alpha skill",
                        "---",
                        "",
                        "# Alpha",
                    ]
                ),
                encoding="utf-8",
            )

            catalog = SkillCatalog(root_dir=root / "skills")
            registry = CapabilityRegistry.build_default(
                skill_catalog=catalog,
                subagent_registry=SubAgentRegistry(),
            )

            stock_names = {
                item["function"]["name"]
                for item in registry.tool_specs_for_mode("stock")
            }
            market_names = {
                item["function"]["name"]
                for item in registry.tool_specs_for_mode("market")
            }

            self.assertIn("get_price_history", stock_names)
            self.assertIn("skill", stock_names)
            self.assertIn("subagent", stock_names)
            self.assertNotIn("get_price_history", market_names)
            self.assertIn("search_news", market_names)
            self.assertIn("skill", market_names)

            self.assertFalse(registry.include_in_evidence("skill"))
            self.assertFalse(registry.include_in_evidence("subagent"))
            self.assertTrue(registry.include_in_evidence("search_news"))


if __name__ == "__main__":
    unittest.main()
