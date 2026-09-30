#!/usr/bin/env python3
"""OpenAI-compatible LLM client shared by sql-review scripts.

Configured via environment variables:
  LLM_API_KEY   (required) — provider API key
  LLM_BASE_URL  (optional) — default https://api.deepseek.com
  LLM_MODEL     (optional) — default deepseek-v4-pro
"""

import json
import os
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"


def _config() -> tuple[str, str, str]:
    base_url = os.environ.get("LLM_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    api_key = os.environ.get("LLM_API_KEY", "")
    model = os.environ.get("LLM_MODEL", DEFAULT_MODEL)
    return base_url, api_key, model


def available() -> bool:
    return bool(os.environ.get("LLM_API_KEY", ""))


def call_llm(system_prompt: str, user_prompt: str, timeout: int = 60) -> str:
    base_url, api_key, model = _config()
    if not api_key:
        raise RuntimeError("LLM_API_KEY is not set")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
    }
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM HTTP {exc.code}: {body[:200]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"LLM network error: {exc.reason}") from exc

    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError(f"LLM response missing choices: {json.dumps(data, ensure_ascii=False)[:200]}")
    return choices[0]["message"]["content"]
