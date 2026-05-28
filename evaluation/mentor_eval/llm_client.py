from __future__ import annotations

import json
import ast
import http.client
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


def _clean_json_like(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:].strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:].strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()
    cleaned = re.sub(r"\bNone\b", "null", cleaned)
    cleaned = re.sub(r"\bTrue\b", "true", cleaned)
    cleaned = re.sub(r"\bFalse\b", "false", cleaned)
    cleaned = re.sub(r"\.\.\.", "null", cleaned)
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    return cleaned


def _parse_dict_candidate(text: str) -> Dict[str, Any] | None:
    cleaned = _clean_json_like(text)
    decoder = json.JSONDecoder()
    try:
        value, _ = decoder.raw_decode(cleaned.lstrip())
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    try:
        value = ast.literal_eval(text.strip())
        if isinstance(value, dict):
            return value
    except (SyntaxError, ValueError):
        pass
    return None


def extract_json_block(text: str) -> Dict[str, Any]:
    stripped = text.strip()
    if not stripped:
        raise ValueError("Empty model response")
    decoder = json.JSONDecoder()
    candidates: List[Dict[str, Any]] = []
    first = _parse_dict_candidate(stripped)
    if first is not None:
        candidates.append(first)
    match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if match:
        candidate = _parse_dict_candidate(match.group(0))
        if candidate is not None:
            candidates.append(candidate)
    for match in re.finditer(r"\{", stripped):
        candidate = _parse_dict_candidate(stripped[match.start():].lstrip())
        if candidate is not None:
            candidates.append(candidate)
    if candidates:
        known_shapes = [
            ({"learner_information", "learning_goal", "cognitive_status", "learning_preferences", "behavioral_patterns"}, 100),
            ({"skill_gaps"}, 90),
            ({"skill_requirements"}, 85),
            ({"learning_path"}, 80),
            ({"learning_sessions"}, 80),
            ({"content", "quiz"}, 75),
            ({"dominant_type", "distribution", "confidence", "evidence_summary"}, 40),
        ]

        def schema_score(item: Dict[str, Any]) -> tuple[int, int]:
            keys = set(item.keys())
            best = 0
            for required, score in known_shapes:
                if required.issubset(keys):
                    best = max(best, score)
            return best, len(json.dumps(item, ensure_ascii=False))

        return max(candidates, key=schema_score)
    raise ValueError(f"Model response is not valid JSON: {text[:500]}")


@dataclass
class OpenAICompatibleClient:
    api_key: str
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o"
    temperature: float = 0.0
    timeout_seconds: Optional[float] = None

    @classmethod
    def from_env(
        cls,
        model: str = "gpt-4o",
        base_url: str = "https://api.openai.com/v1",
        api_key: str = "",
        api_key_env: str = "OPENAI_API_KEY",
        temperature: float = 0.0,
        timeout_seconds: Optional[float] = None,
    ) -> "OpenAICompatibleClient":
        api_key = api_key.strip() or os.getenv(api_key_env, "").strip()
        if not api_key:
            raise EnvironmentError(f"Missing API key in config field api_key or environment variable {api_key_env}")
        return cls(api_key=api_key, base_url=base_url, model=model, temperature=temperature, timeout_seconds=timeout_seconds)

    def chat(self, messages: List[Dict[str, str]], model: Optional[str] = None, temperature: Optional[float] = None) -> str:
        payload = {
            "model": model or self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
        }
        data = json.dumps(payload).encode("utf-8")
        
        # Retry up to 3 times with exponential backoff
        max_retries = 3
        for attempt in range(max_retries):
            try:
                request = urllib.request.Request(
                    f"{self.base_url.rstrip('/')}/chat/completions",
                    data=data,
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}",
                    },
                    method="POST",
                )
                if self.timeout_seconds is None:
                    response_handle = urllib.request.urlopen(request)
                else:
                    response_handle = urllib.request.urlopen(request, timeout=self.timeout_seconds)
                with response_handle as response:
                    response_payload = json.loads(response.read().decode("utf-8"))
                
                choices = response_payload.get("choices", [])
                if not choices:
                    raise RuntimeError(f"Unexpected OpenAI response: {response_payload}")
                message = choices[0].get("message", {})
                content = message.get("content", "")
                return str(content)
            
            except urllib.error.HTTPError as exc:
                message = exc.read().decode("utf-8", errors="replace")
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # 1s, 2s, 4s
                    print(f"[Retry {attempt + 1}/{max_retries}] API error {exc.code}, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise RuntimeError(f"OpenAI-compatible request failed after {max_retries} attempts: {exc.code} {message}") from exc
            
            except (urllib.error.URLError, TimeoutError, http.client.RemoteDisconnected, ConnectionResetError) as exc:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"[Retry {attempt + 1}/{max_retries}] Connection error, retrying in {wait_time}s...")
                    time.sleep(wait_time)
                else:
                    raise RuntimeError(f"OpenAI-compatible request failed after {max_retries} attempts: {exc}") from exc
