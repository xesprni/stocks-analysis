import tempfile
import unittest
from pathlib import Path

from market_reporter.services.config_store import ConfigStore


class ConfigStoreTest(unittest.TestCase):
    def test_load_creates_default_and_save_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config" / "settings.yaml"
            store = ConfigStore(config_path=config_path)

            loaded = store.load()
            self.assertTrue(config_path.exists())
            self.assertEqual(loaded.news_limit, 20)

            updated = loaded.model_copy(update={"news_limit": 35, "flow_periods": 16})
            store.save(updated)

            reloaded = store.load()
            self.assertEqual(reloaded.news_limit, 35)
            self.assertEqual(reloaded.flow_periods, 16)


if __name__ == "__main__":
    unittest.main()
