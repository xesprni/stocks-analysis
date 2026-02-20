from __future__ import annotations

from typing import Optional

from openai import AsyncOpenAI

from market_reporter.config import AnalysisProviderConfig
from market_reporter.core.types import AnalysisInput, AnalysisOutput
from market_reporter.core.utils import parse_json
from market_reporter.modules.analysis.prompt_builder import (
    build_user_prompt,
    get_system_prompt,
)


class OpenAICompatibleProvider:
    provider_id = "openai_compatible"

    def __init__(self, provider_config: AnalysisProviderConfig) -> None:
        self.provider_config = provider_config

    async def analyze(
        self, payload: AnalysisInput, model: str, api_key: Optional[str] = None
    ) -> AnalysisOutput:
        if not api_key:
            raise ValueError("API key is required for openai_compatible provider")

        client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.provider_config.base_url,
            timeout=self.provider_config.timeout,
        )

        response = await client.chat.completions.create(
            model=model,
            temperature=0.2,
            messages=[
                {"role": "system", "content": get_system_prompt(payload)},
                {"role": "user", "content": build_user_prompt(payload)},
            ],
        )

        content = (response.choices[0].message.content or "").strip()
        # Prefer strict JSON; fallback parser extracts first JSON object when wrapped.
        structured = parse_json(content)
        if structured is None:
            # Graceful degradation keeps API contract valid even on free-form model replies.
            structured = {
                "summary": content[:300] if content else "模型未返回结构化内容",
                "sentiment": "neutral",
                "key_levels": [],
                "risks": [],
                "action_items": [],
                "confidence": 0.4,
                "markdown": content or "模型未返回可读内容。",
            }

        output = AnalysisOutput.model_validate(
            {
                "summary": structured.get("summary", ""),
                "sentiment": structured.get("sentiment", "neutral"),
                "key_levels": structured.get("key_levels", []),
                "risks": structured.get("risks", []),
                "action_items": structured.get("action_items", []),
                "confidence": float(structured.get("confidence", 0.5)),
                "markdown": structured.get("markdown") or structured.get("summary", ""),
                "raw": structured,
            }
        )
        return output
