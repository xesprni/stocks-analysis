from __future__ import annotations

import unittest

from market_reporter.modules.news.providers.rss_provider import RSSNewsProvider


class RSSProviderContentExtractionTest(unittest.TestCase):
    def test_entry_content_text_extracts_and_sanitizes_html(self):
        entry = {
            "summary": "<p>Temu owner <b>Pinduoduo</b> posted results.</p>",
            "content": [
                {"value": "<div>Revenue growth accelerated in Q4.</div>"},
            ],
        }
        text = RSSNewsProvider._entry_content_text(entry)
        self.assertIn("Temu owner Pinduoduo posted results.", text)
        self.assertIn("Revenue growth accelerated in Q4.", text)
        self.assertNotIn("<p>", text)
        self.assertNotIn("<div>", text)


if __name__ == "__main__":
    unittest.main()
