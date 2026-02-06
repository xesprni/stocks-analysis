from __future__ import annotations

from typing import Optional

from market_reporter.core.types import AnalysisInput, AnalysisOutput


class MockAnalysisProvider:
    provider_id = "mock"

    async def analyze(self, payload: AnalysisInput, model: str, api_key: Optional[str] = None) -> AnalysisOutput:
        quote_text = "暂无报价"
        if payload.quote is not None:
            quote_text = f"最新价 {payload.quote.price:.2f}"

        return AnalysisOutput(
            summary=f"[{model}] {payload.symbol}({payload.market}) 的快速分析已生成。",
            sentiment="neutral",
            key_levels=["阻力位待确认", "支撑位待确认"],
            risks=["数据源可能存在延迟", "宏观政策变化风险"],
            action_items=["结合成交量观察趋势延续", "设置止损并控制仓位"],
            confidence=0.56,
            markdown=(
                f"### {payload.symbol} 分析\n"
                f"- 结论：中性\n"
                f"- 行情：{quote_text}\n"
                "- 建议：等待更清晰的突破信号。\n"
            ),
            raw={"provider": self.provider_id, "model": model},
        )
