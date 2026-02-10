from __future__ import annotations

import asyncio
import json
import os
import select
import shutil
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from market_reporter.config import AnalysisProviderConfig
from market_reporter.core.types import AnalysisInput, AnalysisOutput
from market_reporter.modules.analysis_engine.prompt_builder import (
    build_user_prompt,
    get_system_prompt,
)


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
        del state, callback_url, redirect_to
        # Codex app-server handles login in its own local session flow.
        result = await asyncio.to_thread(self._start_login_sync)
        auth_url = self._pick_string(
            result, ["authUrl", "auth_url", "url", "loginUrl", "login_url"]
        )
        if not auth_url:
            raise ValueError("Codex app-server did not return auth URL.")
        return {
            "auth_url": auth_url,
            "state": "codex-app-server",
            "raw": result,
        }

    async def complete_login(
        self,
        code: Optional[str],
        state: str,
        callback_url: str,
        query_params: Optional[Dict[str, str]] = None,
    ) -> Dict[str, object]:
        del code, state, callback_url, query_params
        # Completion checks local connection state instead of exchanging OAuth code here.
        status = await self.get_auth_status()
        if not status.get("connected"):
            raise ValueError("Codex account is not connected yet.")
        return {
            "access_token": "codex_app_server_session",
            "token_type": "Bearer",
            "raw": status.get("raw") or {},
        }

    async def get_auth_status(self) -> Dict[str, object]:
        try:
            payload = await asyncio.to_thread(self._read_account_payload_sync)
        except Exception as exc:
            return {
                "connected": False,
                "message": str(exc),
                "raw": {},
            }
        connected, message = self._extract_connection_status(payload)
        return {
            "connected": connected,
            "message": message,
            "raw": payload,
        }

    async def logout(self) -> bool:
        return await asyncio.to_thread(self._logout_sync)

    async def list_models(self, access_token: Optional[str] = None) -> List[str]:
        del access_token
        try:
            # Support both legacy and current RPC method names.
            payload = await asyncio.to_thread(
                self._request_with_fallback_sync,
                [
                    ("model/list", {}),
                    ("models/list", {}),
                ],
                float(self.provider_config.timeout),
            )
        except Exception:
            return []
        return self._extract_models(payload)

    async def analyze(
        self,
        payload: AnalysisInput,
        model: str,
        api_key: Optional[str] = None,
        access_token: Optional[str] = None,
    ) -> AnalysisOutput:
        del api_key, access_token
        status = await self.get_auth_status()
        if not status.get("connected"):
            raise ValueError(
                "Codex account is not connected. Please click Connect in Providers page."
            )

        content = await asyncio.to_thread(
            self._run_turn_sync,
            build_user_prompt(payload),
            model,
            get_system_prompt(payload),
        )
        # Provider output should be JSON; fallback path keeps output schema stable.
        structured = self._parse_json(content)
        if structured is None:
            structured = {
                "summary": content[:300]
                if content
                else "Model did not return structured output.",
                "sentiment": "neutral",
                "key_levels": [],
                "risks": [],
                "action_items": [],
                "confidence": 0.4,
                "markdown": content or "Model returned empty output.",
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

    def _start_login_sync(self) -> Dict[str, object]:
        return self._request_with_fallback_sync(
            calls=[
                ("account/login/start", {"type": "chatgpt"}),
                ("loginChatGpt", {}),
            ],
            timeout=float(self.provider_config.timeout),
        )

    def _logout_sync(self) -> bool:
        try:
            self._request_with_fallback_sync(
                calls=[
                    ("account/logout", {}),
                    ("logoutChatGpt", {}),
                ],
                timeout=float(self.provider_config.timeout),
            )
            return True
        except Exception:
            return False

    def _read_account_payload_sync(self) -> Dict[str, object]:
        return self._request_with_fallback_sync(
            calls=[
                ("account/read", {}),
                ("userInfo", {}),
                ("getAuthStatus", {}),
            ],
            timeout=float(self.provider_config.timeout),
        )

    def _run_turn_sync(
        self, user_prompt: str, model: str, system_prompt: str = ""
    ) -> str:
        timeout_seconds = float(max(self.provider_config.timeout * 3, 300))
        process = self._spawn_process()
        deadline = time.time() + timeout_seconds
        try:
            self._send_request(
                process=process,
                request_id=1,
                method="initialize",
                params={
                    "protocolVersion": "2025-09-01",
                    "clientInfo": {"name": "market-reporter", "version": "1.0"},
                },
            )
            self._wait_for_response(process=process, request_id=1, deadline=deadline)

            self._send_request(
                process=process,
                request_id=2,
                method="thread/start",
                params={
                    "ephemeral": True,
                    "model": model,
                    "approvalPolicy": "never",
                    "sandbox": "read-only",
                    "developerInstructions": system_prompt,
                    "personality": "pragmatic",
                },
            )
            # Thread id is required for subsequent turn/start call.
            thread_payload = self._wait_for_response(
                process=process, request_id=2, deadline=deadline
            )
            thread_id = self._extract_thread_id(thread_payload)
            if not thread_id:
                raise ValueError("Codex app-server did not return thread id.")

            self._send_request(
                process=process,
                request_id=3,
                method="turn/start",
                params={
                    "threadId": thread_id,
                    "input": [{"type": "text", "text": user_prompt}],
                    "model": model,
                    "approvalPolicy": "never",
                    "sandboxPolicy": {"type": "readOnly"},
                    "summary": "none",
                },
            )

            turn_started = False
            turn_status: Optional[str] = None
            turn_error: Optional[str] = None
            chunks: List[str] = []
            messages: List[str] = []

            # Consume streaming deltas until terminal turn/completed event arrives.
            while time.time() < deadline:
                message = self._read_message(process=process, deadline=deadline)
                if message is None:
                    continue

                response_id = message.get("id")
                if response_id == 3:
                    if "error" in message:
                        raise ValueError(self._format_rpc_error(message["error"]))
                    turn_started = True
                    continue

                method = message.get("method")
                params = message.get("params")
                if not isinstance(params, dict):
                    params = {}

                if method == "item/agentMessage/delta":
                    delta = params.get("delta")
                    if isinstance(delta, str) and delta:
                        chunks.append(delta)
                    continue

                if method == "item/completed":
                    item = params.get("item")
                    if isinstance(item, dict) and item.get("type") == "agentMessage":
                        text = item.get("text")
                        if isinstance(text, str) and text.strip():
                            messages.append(text.strip())
                    continue

                if method == "turn/completed":
                    turn = params.get("turn")
                    if isinstance(turn, dict):
                        status = turn.get("status")
                        if isinstance(status, str):
                            turn_status = status
                        error_payload = turn.get("error")
                        if isinstance(error_payload, dict):
                            turn_error = self._pick_string(
                                error_payload,
                                ["message", "additionalDetails"],
                            )
                    break

                if method == "error":
                    turn_error = self._pick_string(params, ["message"]) or turn_error

            if not turn_started:
                raise ValueError(
                    "Codex app-server did not acknowledge turn/start request."
                )
            final_text = messages[-1] if messages else "".join(chunks).strip()
            if turn_status is None:
                if final_text:
                    return final_text
                raise ValueError(
                    f"Timed out waiting for codex turn completion after {int(timeout_seconds)}s."
                )
            if turn_status != "completed":
                if final_text and turn_status in {"cancelled", "aborted"}:
                    return final_text
                suffix = f" ({turn_error})" if turn_error else ""
                raise ValueError(f"Codex turn failed: {turn_status}{suffix}")

            if not final_text:
                raise ValueError("Codex app-server returned empty analysis output.")
            return final_text
        finally:
            self._close_process(process)

    def _request_with_fallback_sync(
        self,
        calls: Sequence[Tuple[str, Dict[str, object]]],
        timeout: float,
    ) -> Dict[str, object]:
        errors: List[str] = []
        # Try equivalent RPC methods to handle app-server version differences.
        for method, params in calls:
            try:
                return self._request_once_sync(
                    method=method, params=params, timeout=timeout
                )
            except Exception as exc:
                errors.append(str(exc))
        raise ValueError(self._join_unique_errors(errors))

    def _request_once_sync(
        self,
        method: str,
        params: Dict[str, object],
        timeout: float,
    ) -> Dict[str, object]:
        process = self._spawn_process()
        deadline = time.time() + timeout
        try:
            # Every request starts with JSON-RPC initialize handshake.
            self._send_request(
                process=process,
                request_id=1,
                method="initialize",
                params={
                    "protocolVersion": "2025-09-01",
                    "clientInfo": {"name": "market-reporter", "version": "1.0"},
                },
            )
            self._wait_for_response(process=process, request_id=1, deadline=deadline)
            self._send_request(
                process=process, request_id=2, method=method, params=params
            )
            return self._wait_for_response(
                process=process, request_id=2, deadline=deadline
            )
        finally:
            self._close_process(process)

    def _wait_for_response(
        self,
        process: subprocess.Popen[str],
        request_id: int,
        deadline: float,
    ) -> Dict[str, object]:
        while time.time() < deadline:
            message = self._read_message(process=process, deadline=deadline)
            if message is None:
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise ValueError(self._format_rpc_error(message["error"]))
            payload = message.get("result")
            if isinstance(payload, dict):
                return payload
            if payload is None:
                return {}
            return {"data": payload}
        raise ValueError(f"Timed out waiting for response: request_id={request_id}")

    @staticmethod
    def _read_message(
        process: subprocess.Popen[str],
        deadline: float,
    ) -> Optional[Dict[str, object]]:
        if process.stdout is None:
            raise ValueError("Codex app-server stdout is unavailable.")

        while time.time() < deadline:
            remaining = max(0.0, deadline - time.time())
            readable, _, _ = select.select([process.stdout], [], [], remaining)
            if not readable:
                return None
            line = process.stdout.readline()
            if not line:
                if process.poll() is not None:
                    return None
                continue
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                # Ignore non-JSON log lines emitted by child process.
                continue
            if isinstance(message, dict):
                return message
        return None

    @staticmethod
    def _send_request(
        process: subprocess.Popen[str],
        request_id: int,
        method: str,
        params: Dict[str, object],
    ) -> None:
        if process.stdin is None:
            raise ValueError("Codex app-server stdin is unavailable.")
        packet = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        process.stdin.write(json.dumps(packet, ensure_ascii=False) + "\n")
        process.stdin.flush()

    @classmethod
    def _spawn_process(cls) -> subprocess.Popen[str]:
        binary = cls._resolve_codex_binary()
        process = subprocess.Popen(
            [binary, "app-server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        return process

    @staticmethod
    def _close_process(process: subprocess.Popen[str]) -> None:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=0.8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=0.8)
        if process.stdin:
            process.stdin.close()
        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()

    @staticmethod
    def _resolve_codex_binary() -> str:
        candidates: List[Optional[str]] = [
            os.environ.get("CODEX_BIN"),
            shutil.which("codex"),
            "/opt/homebrew/bin/codex",
            "/usr/local/bin/codex",
        ]
        # Probe explicit env var first, then common PATH/homebrew install locations.
        for candidate in candidates:
            if not candidate:
                continue
            path = Path(candidate).expanduser()
            if path.exists() and os.access(path, os.X_OK):
                return str(path)
        raise ValueError(
            "`codex` CLI not found. Please install Codex CLI and ensure it is in PATH."
        )

    @staticmethod
    def _extract_thread_id(payload: Dict[str, object]) -> Optional[str]:
        thread = payload.get("thread")
        if isinstance(thread, dict):
            thread_id = thread.get("id")
            if isinstance(thread_id, str) and thread_id.strip():
                return thread_id.strip()
        return None

    @staticmethod
    def _extract_connection_status(payload: Dict[str, object]) -> Tuple[bool, str]:
        account = payload.get("account")
        if isinstance(account, dict) and account:
            return True, "Connected."
        auth_token = payload.get("authToken")
        if isinstance(auth_token, str) and auth_token.strip():
            return True, "Connected."
        return False, "Provider account is not connected."

    @staticmethod
    def _format_rpc_error(error_payload: object) -> str:
        if isinstance(error_payload, dict):
            message = error_payload.get("message")
            code = error_payload.get("code")
            if isinstance(message, str) and isinstance(code, int):
                return f"{message} (code={code})"
            if isinstance(message, str):
                return message
        return "Codex app-server request failed."

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
        return sorted({entry for entry in values if entry})

    @staticmethod
    def _parse_json(content: str):
        if not content:
            return None
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            # Recover embedded JSON from mixed text responses.
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
    def _join_unique_errors(errors: Sequence[str]) -> str:
        values = [item.strip() for item in errors if item and item.strip()]
        unique = list(dict.fromkeys(values))
        if not unique:
            return "Codex app-server request failed."
        return "; ".join(unique)

    @staticmethod
    def normalize_expires_at(
        expires_at: Optional[str], expires_in: Optional[float]
    ) -> Optional[datetime]:
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
