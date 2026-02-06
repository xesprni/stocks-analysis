import tempfile
import unittest
from pathlib import Path

import yaml

from market_reporter.config import AnalysisConfig, AnalysisProviderConfig, default_app_config
from market_reporter.services.config_store import ConfigStore


class ConfigStoreAnalysisDefaultsTest(unittest.TestCase):
    def test_load_backfills_missing_default_analysis_providers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "config" / "settings.yaml"
            config_path.parent.mkdir(parents=True, exist_ok=True)

            config = default_app_config()
            config.analysis = AnalysisConfig(
                default_provider="mock",
                default_model="market-default",
                providers=[
                    AnalysisProviderConfig(
                        provider_id="mock",
                        type="mock",
                        base_url="",
                        models=["market-default"],
                        timeout=5,
                        enabled=True,
                        auth_mode="none",
                    )
                ],
            )
            config_path.write_text(
                yaml.safe_dump(config.model_dump(mode="json"), allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )

            store = ConfigStore(config_path=config_path)
            loaded = store.load()

            provider_ids = [item.provider_id for item in loaded.analysis.providers]
            self.assertIn("mock", provider_ids)
            self.assertIn("openai_compatible", provider_ids)
            self.assertIn("codex_app_server", provider_ids)

            persisted = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            persisted_ids = [item["provider_id"] for item in persisted["analysis"]["providers"]]
            self.assertIn("codex_app_server", persisted_ids)


if __name__ == "__main__":
    unittest.main()
