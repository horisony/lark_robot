#!/usr/bin/env python3
"""OpenAI-compatible POST /chat/completions → PackyAPI."""
import json
import logging
import os

import requests

_MAX_REPLY_CHARS = 12000


class PackyApiError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def chat_completion(user_text: str) -> str:
    """
    POST https://www.packyapi.com/v1/chat/completions (base configurable).
    Bearer token + JSON: model, messages[{role,user,content}].
    """
    api_key = (os.getenv("PACKY_API_KEY") or "").strip()
    base = (os.getenv("PACKY_API_BASE") or "https://www.packyapi.com/v1").rstrip("/")
    model = (os.getenv("PACKY_MODEL") or "claude-opus-4-6").strip()

    if not api_key:
        raise PackyApiError("PACKY_API_KEY is not set")

    url = "{}/chat/completions".format(base)
    headers = {
        "Authorization": "Bearer {}".format(api_key),
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": user_text}],
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=120)

    if resp.status_code != 200:
        snippet = (resp.text or "")[:500]
        logging.error("PackyAPI HTTP %s: %s", resp.status_code, snippet)
        raise PackyApiError(
            "模型服务暂时不可用（HTTP {}）".format(resp.status_code),
            status_code=resp.status_code,
        )

    try:
        data = resp.json()
    except ValueError as e:
        logging.error("PackyAPI invalid JSON: %s", (resp.text or "")[:500])
        raise PackyApiError("模型返回格式异常") from e

    err = data.get("error")
    if err:
        msg = err.get("message") if isinstance(err, dict) else str(err)
        logging.error("PackyAPI error field: %s", msg)
        raise PackyApiError("模型错误: {}".format(msg))

    choices = data.get("choices") or []
    if not choices:
        logging.error("PackyAPI empty choices: %s", json.dumps(data)[:500])
        raise PackyApiError("模型无返回内容")

    msg = choices[0].get("message") or {}
    content = msg.get("content")
    if content is None:
        raise PackyApiError("模型无文本内容")

    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(p.get("text") or "")
            elif isinstance(p, str):
                parts.append(p)
        content = "".join(parts)

    text = str(content).strip()
    if len(text) > _MAX_REPLY_CHARS:
        text = text[: _MAX_REPLY_CHARS] + "\n…（已截断）"
    return text
