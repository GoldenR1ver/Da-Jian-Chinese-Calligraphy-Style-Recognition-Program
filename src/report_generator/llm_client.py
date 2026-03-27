"""OpenAI 兼容 chat/completions HTTP 调用。"""

from __future__ import annotations

import json
import re
from typing import Any

import requests


def parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError("No JSON object in LLM response")
    return json.loads(m.group(0))


def chat_completion(
    user_content: str,
    *,
    api_key: str,
    base_url: str,
    model: str,
    timeout: float = 120.0,
) -> str:
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    base_body: dict[str, Any] = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You output only valid JSON for the user instruction.",
            },
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.4,
    }
    body = {**base_body, "response_format": {"type": "json_object"}}
    resp = requests.post(url, headers=headers, json=body, timeout=timeout)
    if resp.status_code != 200:
        body_retry = dict(base_body)
        resp = requests.post(url, headers=headers, json=body_retry, timeout=timeout)
        if resp.status_code != 200:
            raise RuntimeError(f"LLM HTTP {resp.status_code}: {resp.text[:500]}")
    data = resp.json()
    try:
        return str(data["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"Unexpected LLM response shape: {data!r}") from e
