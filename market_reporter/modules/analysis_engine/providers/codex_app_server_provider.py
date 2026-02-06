from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence

import httpx

from market_reporter.config import AnalysisProviderConfig
from market_reporter.core.types import AnalysisInput, AnalysisOutput
from market_reporter.modules.analysis_engine.prompt_builder import SYSTEM_PROMPT, build_user_prompt


class CodexAppServerProvider:
    provider_id = "codex_app_server"

    def __init__(self, provider_config: AnalysisProviderConfig) -> None:
        self.provider_config = provider_config

    async def start_login(
        self,
        state: str,
        callback_url: str,
        redirect_to: Optional[str] = None,
    ) -> Dict[str, object]:
        payload = {
            "type": "chatgpt",
            "state": state,
            "redirect_uri": callback_url,
            "redirectUri": callback_url,
        }
        if redirect_to:
            payload["redirect_to"] = redirect_to
            payload["redirectTo"] = redirect_to

        data = await self._post_with_fallback(
            paths=["/account/login/start", "/v1/account/login/start"],
            json_body=payload,
        )
        auth_url = self._pick_string(data, ["authUrl", "auth_url", "url", "loginUrl", "login_url"])
        if not auth_url:
            raise ValueError("Codex App Server did not return auth URL")
        return {
            "auth_url": auth_url,
            "state": state,
            "raw": data,
        }

    async def complete_login(
        self,
        code: Optional[str],
        state: str,
        callback_url: str,
        query_params: Optional[Dict[str, str]] = None,
    ) -> Dict[str, object]:
        query_params = query_params or {}

        direct_access_token = (
            query_params.get("access_token")
            or query_params.get("token")
            or query_params.get("id_token")
        )
        if direct_access_token:
            return {
                "access_token": direct_access_token,
                "refresh_token": query_params.get("refresh_token"),
                "expires_at": query_params.get("expires_at"),
                "token_type": query_params.get("token_type") or "Bearer",
                "raw": query_params,
            }

        if not code:
            raise ValueError("Missing login code from callback.")

        payload = {
            "type": "chatgpt",
            "code": code,
            "state": state,
            "redirect_uri": callback_url,
            "redirectUri": callback_url,
        }
        data = await self._post_with_fallback(
            paths=[
                "/account/login/complete",
                "/v1/account/login/complete",
                "/account/login/callback",
                "/v1/account/login/callback",
            ],
            json_body=payload,
        )
        access_token = self._pick_string(
            data,
            ["access_token", "accessToken", "token", "id_token"],
        )
        if not access_token:
            raise ValueError("Codex App Server did not return access token")
        return {
            "access_token": access_token,
            "refresh_token": self._pick_string(data, ["refresh_token", "refreshToken"]),
            "expires_at": self._pick_string(data, ["expires_at", "expiresAt"]),
            "expires_in": self._pick_number(data, ["expires_in", "expiresIn"]),
            "token_type": self._pick_string(data, ["token_type", "tokenType"]) or "Bearer",
            "raw": data,
        }

    async def list_models(self, access_token: str) -> List[str]:
        headers = {"Authorization": f"Bearer {access_token}"}
        data = await self._get_with_fallback(paths=["/models", "/v1/models"], headers=headers, allow_error=True)
        if data is None:
            return []
        models = self._extract_models(data)
        return models

    async def analyze(
        self,
        payload: AnalysisInput,
        model: str,
        api_key: Optional[str] = None,
        access_token: Optional[str] = None,
    ) -> AnalysisOutput:
        token = access_token or api_key
        if not token:
            raise ValueError("Codex account is not connected.")

        request_payload = {
            "model": model,
            "temperature": 0.2,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(payload)},
            ],
        }
        headers = {"Authorization": f"Bearer {token}"}
        data = await self._post_with_fallback(
            paths=["/v1/chat/completions", "/chat/completions"],
            json_body=request_payload,
            headers=headers,
        )
        content = self._extract_content(data)
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

        return AnalysisOutput.model_validate(
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

    async def _post_with_fallback(
        self,
        paths: Sequence[str],
        json_body: Dict[str, object],
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, object]:
        errors: List[str] = []
        for path in paths:
            try:
                response = await self._request("POST", path=path, headers=headers, json_body=json_body)
                return self._to_json(response)
            except Exception as exc:
                errors.append(str(exc))
        raise ValueError("; ".join(errors) if errors else "Codex App Server request failed")

    async def _get_with_fallback(
        self,
        paths: Sequence[str],
        headers: Optional[Dict[str, str]] = None,
        allow_error: bool = False,
    ) -> Optional[Dict[str, object]]:
        errors: List[str] = []
        for path in paths:
            try:
                response = await self._request("GET", path=path, headers=headers)
                return self._to_json(response)
            except Exception as exc:
                errors.append(str(exc))
        if allow_error:
            return None
        raise ValueError("; ".join(errors) if errors else "Codex App Server request failed")

    async def _request(
        self,
        method: str,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        json_body: Optional[Dict[str, object]] = None,
    ) -> httpx.Response:
        base_url = (self.provider_config.base_url or "").strip()
        if not base_url:
            raise ValueError("Provider base_url is empty. Please configure codex_app_server base_url first.")
        url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=self.provider_config.timeout) as client:
            response = await client.request(
                method=method,
                url=url,
                json=json_body,
                headers=headers,
            )
        if response.status_code >= 400:
            raise ValueError(f"{method} {path} failed ({response.status_code}): {response.text[:300]}")
        return response

    @staticmethod
    def _to_json(response: httpx.Response) -> Dict[str, object]:
        try:
            payload = response.json()
        except Exception as exc:
            raise ValueError(f"Invalid JSON response: {exc}") from exc
        if isinstance(payload, dict):
            return payload
        return {"data": payload}

    @staticmethod
    def _extract_models(data: Dict[str, object]) -> List[str]:
        rows = data.get("data")
        values: List[str] = []
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    model_id = row.get("id") or row.get("model") or row.get("name")
                    if isinstance(model_id, str) and model_id.strip():
                        values.append(model_id.strip())
                elif isinstance(row, str) and row.strip():
                    values.append(row.strip())
        elif isinstance(rows, dict):
            model_id = rows.get("id") or rows.get("model") or rows.get("name")
            if isinstance(model_id, str) and model_id.strip():
                values.append(model_id.strip())
        unique = sorted({value for value in values if value})
        return unique

    @staticmethod
    def _extract_content(data: Dict[str, object]) -> str:
        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str):
                        return content.strip()
                content = first.get("text")
                if isinstance(content, str):
                    return content.strip()
        output = data.get("output_text")
        if isinstance(output, str):
            return output.strip()
        return json.dumps(data, ensure_ascii=False)

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

    @staticmethod
    def _pick_string(data: Dict[str, object], keys: Sequence[str]) -> Optional[str]:
        for key in keys:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        nested = data.get("data")
        if isinstance(nested, dict):
            for key in keys:
                value = nested.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    @staticmethod
    def _pick_number(data: Dict[str, object], keys: Sequence[str]) -> Optional[float]:
        for key in keys:
            value = data.get(key)
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value)
                except ValueError:
                    continue
        nested = data.get("data")
        if isinstance(nested, dict):
            for key in keys:
                value = nested.get(key)
                if isinstance(value, (int, float)):
                    return float(value)
                if isinstance(value, str):
                    try:
                        return float(value)
                    except ValueError:
                        continue
        return None

    @staticmethod
    def normalize_expires_at(expires_at: Optional[str], expires_in: Optional[float]) -> Optional[datetime]:
        if expires_at:
            raw = expires_at.strip()
            if raw:
                if raw.endswith("Z"):
                    raw = raw[:-1] + "+00:00"
                try:
                    parsed = datetime.fromisoformat(raw)
                    if parsed.tzinfo is not None:
                        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
                    return parsed
                except ValueError:
                    pass
        if expires_in is not None and expires_in > 0:
            now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
            return now_utc + timedelta(seconds=expires_in)
        return None
