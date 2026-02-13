import tempfile
import unittest
from pathlib import Path

import yaml

from market_reporter.config import default_app_config
from market_reporter.services.config_store import ConfigStore


class ConfigStoreAgentDefaultsTest(unittest.TestCase):
    def test_load_backfills_agent_defaults(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "config" / "settings.yaml"
            config_path.parent.mkdir(parents=True, exist_ok=True)

            config = default_app_config()
            payload = config.model_dump(mode="json")
            payload.pop("agent", None)
            config_path.write_text(
                yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )

            store = ConfigStore(config_path=config_path)
            loaded = store.load()

            self.assertTrue(loaded.agent.enabled)
            self.assertEqual(loaded.agent.max_steps, 8)
            persisted = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            self.assertIn("agent", persisted)
            self.assertEqual(persisted["agent"]["default_price_window_days"], 365)


if __name__ == "__main__":
    unittest.main()
