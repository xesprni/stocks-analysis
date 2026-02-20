import unittest

from market_reporter.modules.analysis.agent.guardrails import AgentGuardrails
from market_reporter.modules.analysis.agent.schemas import AgentEvidence


class AgentGuardrailsTest(unittest.TestCase):
    def test_pe_inconsistency_detected_and_penalized(self):
        guardrails = AgentGuardrails()
        tool_results = {
            "get_fundamentals": {
                "as_of": "2026-02-13",
                "source": "yfinance",
                "metrics": {
                    "market_cap": 1000.0,
                    "net_income": 10.0,
                    "trailing_pe": 20.0,
                },
            },
            "get_price_history": {
                "as_of": "2026-02-13",
                "source": "yfinance",
            },
        }
        conclusions = ["估值处于历史中位数 [E1]", "盈利质量稳定"]
        evidence = [
            AgentEvidence(
                evidence_id="E1",
                statement="核心财务指标",
                source="yfinance",
                as_of="2026-02-13",
                pointer="get_fundamentals",
            )
        ]

        issues = guardrails.validate(
            tool_results=tool_results,
            conclusions=conclusions,
            evidence_map=evidence,
            consistency_tolerance=0.05,
        )

        codes = {item.code for item in issues}
        self.assertIn("pe_inconsistency", codes)
        self.assertIn("conclusion_without_evidence", codes)

        adjusted = guardrails.apply_confidence_penalty(
            base_confidence=0.8, issues=issues
        )
        self.assertLess(adjusted, 0.8)
        self.assertGreaterEqual(adjusted, 0.2)


if __name__ == "__main__":
    unittest.main()
