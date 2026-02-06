from __future__ import annotations

import json
from typing import Optional

from openai import AsyncOpenAI

from market_reporter.config import AnalysisProviderConfig
from market_reporter.core.types import AnalysisInput, AnalysisOutput
from market_reporter.modules.analysis_engine.prompt_builder import SYSTEM_PROMPT, build_user_prompt


class OpenAICompatibleProvider:
    provider_id = "openai_compatible"

    def __init__(self, provider_config: AnalysisProviderConfig) -> None:
        self.provider_config = provider_config

    async def analyze(self, payload: AnalysisInput, model: str, api_key: Optional[str] = None) -> AnalysisOutput:
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
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(payload)},
            ],
        )

        content = (response.choices[0].message.content or "").strip()
        structured = self._parse_json(content)
        if structured is None:
            structured = {
                "summary": content[:300] if content else "模型未返回结构化内容",
                "sentiment": "neutral",
                "key_levels": [],
                "risks": [],
                "action_items": [],
                "confidence": 0.4,
                "markdown": content or "模型未返回可读内容。",
            }

        output = AnalysisOutput.model_validate({
            "summary": structured.get("summary", ""),
            "sentiment": structured.get("sentiment", "neutral"),
            "key_levels": structured.get("key_levels", []),
            "risks": structured.get("risks", []),
            "action_items": structured.get("action_items", []),
            "confidence": float(structured.get("confidence", 0.5)),
            "markdown": structured.get("markdown") or structured.get("summary", ""),
            "raw": structured,
        })
        return output

    @staticmethod
    def _parse_json(content: str):
        if not content:
            return None
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(content[start : end + 1])
                except json.JSONDecodeError:
                    return None
            return None
