from __future__ import annotations

from typing import Any, Dict, List, Optional

from market_reporter.modules.agent.schemas import AgentEvidence, GuardrailIssue


class AgentGuardrails:
    def validate(
        self,
        tool_results: Dict[str, Dict[str, Any]],
        conclusions: List[str],
        evidence_map: List[AgentEvidence],
        consistency_tolerance: float,
    ) -> List[GuardrailIssue]:
        issues: List[GuardrailIssue] = []

        issues.extend(self._validate_tool_metadata(tool_results))
        pe_issue = self._validate_pe_consistency(tool_results, consistency_tolerance)
        if pe_issue is not None:
            issues.append(pe_issue)
        issues.extend(self._validate_evidence(conclusions, evidence_map))
        return issues

    def apply_confidence_penalty(
        self,
        base_confidence: float,
        issues: List[GuardrailIssue],
    ) -> float:
        penalty = 0.0
        for issue in issues:
            if issue.severity == "HIGH":
                penalty += 0.25
            elif issue.severity == "MEDIUM":
                penalty += 0.2
            else:
                penalty += 0.1
        if issues:
            penalty = max(penalty, 0.2)
        return max(0.2, min(1.0, base_confidence - penalty))

    @staticmethod
    def _validate_tool_metadata(tool_results: Dict[str, Dict[str, Any]]) -> List[GuardrailIssue]:
        issues: List[GuardrailIssue] = []
        for tool_name, payload in tool_results.items():
            if not isinstance(payload, dict):
                issues.append(
                    GuardrailIssue(
                        code="tool_payload_invalid",
                        severity="MEDIUM",
                        message=f"Tool output is not object: {tool_name}",
                        details={"tool": tool_name},
                    )
                )
                continue
            if not str(payload.get("as_of") or "").strip():
                issues.append(
                    GuardrailIssue(
                        code="missing_as_of",
                        severity="HIGH",
                        message=f"Tool result missing as_of: {tool_name}",
                        details={"tool": tool_name},
                    )
                )
            if not str(payload.get("source") or "").strip():
                issues.append(
                    GuardrailIssue(
                        code="missing_source",
                        severity="HIGH",
                        message=f"Tool result missing source: {tool_name}",
                        details={"tool": tool_name},
                    )
                )
        return issues

    @staticmethod
    def _validate_pe_consistency(
        tool_results: Dict[str, Dict[str, Any]],
        tolerance: float,
    ) -> Optional[GuardrailIssue]:
        fundamentals = tool_results.get("get_fundamentals")
        if not isinstance(fundamentals, dict):
            return None
        metrics = fundamentals.get("metrics")
        if not isinstance(metrics, dict):
            return None
        market_cap = _to_float(metrics.get("market_cap"))
        net_income = _to_float(metrics.get("net_income"))
        trailing_pe = _to_float(metrics.get("trailing_pe"))
        if market_cap is None or net_income is None or trailing_pe is None:
            return None
        if net_income == 0:
            return GuardrailIssue(
                code="pe_consistency_skip",
                severity="LOW",
                message="PE consistency check skipped because net_income is zero.",
                details={},
            )

        computed = market_cap / net_income
        baseline = max(abs(trailing_pe), 1.0)
        delta_ratio = abs(computed - trailing_pe) / baseline
        if delta_ratio <= tolerance:
            return None
        return GuardrailIssue(
            code="pe_inconsistency",
            severity="HIGH",
            message="PE consistency mismatch detected (PE != market_cap / net_income).",
            details={
                "trailing_pe": trailing_pe,
                "computed_pe": computed,
                "delta_ratio": delta_ratio,
                "tolerance": tolerance,
            },
        )

    @staticmethod
    def _validate_evidence(
        conclusions: List[str],
        evidence_map: List[AgentEvidence],
    ) -> List[GuardrailIssue]:
        issues: List[GuardrailIssue] = []
        if not evidence_map:
            issues.append(
                GuardrailIssue(
                    code="evidence_missing",
                    severity="HIGH",
                    message="No evidence entries available.",
                    details={},
                )
            )
            return issues

        for idx, row in enumerate(conclusions):
            if "[E" not in row:
                issues.append(
                    GuardrailIssue(
                        code="conclusion_without_evidence",
                        severity="MEDIUM",
                        message=f"Conclusion {idx + 1} has no evidence pointer.",
                        details={"index": idx, "conclusion": row},
                    )
                )
        return issues


def _to_float(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None
