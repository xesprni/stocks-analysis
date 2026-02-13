import tempfile
import unittest
from pathlib import Path

import yaml

from market_reporter.config import default_app_config
from market_reporter.services.config_store import ConfigStore


class ConfigStoreDashboardDefaultsTest(unittest.TestCase):
    def test_load_backfills_dashboard_defaults(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "config" / "settings.yaml"
            config_path.parent.mkdir(parents=True, exist_ok=True)

            config = default_app_config()
            payload = config.model_dump(mode="json")
            payload.pop("dashboard", None)
            config_path.write_text(
                yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )

            store = ConfigStore(config_path=config_path)
            loaded = store.load()

            self.assertTrue(loaded.dashboard.auto_refresh_enabled)
            self.assertEqual(loaded.dashboard.auto_refresh_seconds, 15)
            self.assertGreaterEqual(len(loaded.dashboard.indices), 1)

            persisted = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            self.assertIn("dashboard", persisted)
            self.assertIn("indices", persisted["dashboard"])


if __name__ == "__main__":
    unittest.main()
