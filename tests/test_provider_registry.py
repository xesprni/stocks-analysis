import unittest

from market_reporter.core.registry import ProviderRegistry


class ProviderRegistryTest(unittest.TestCase):
    def test_register_and_resolve(self):
        registry = ProviderRegistry()
        registry.register("analysis", "mock", lambda: {"ok": True})

        self.assertTrue(registry.has("analysis", "mock"))
        payload = registry.resolve("analysis", "mock")
        self.assertEqual(payload["ok"], True)
        self.assertEqual(registry.list_ids("analysis"), ["mock"])


if __name__ == "__main__":
    unittest.main()
