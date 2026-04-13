#!/usr/bin/env python3.8
import json
import logging
import os

import requests

# Feishu text messages are limited; stay conservative.
_MAX_REPLY_CHARS = 12000

# Comma-separated provider names, first tried first. Example: minimax,packy
_DEFAULT_ORDER = "minimax,packy"


class PackyApiError(Exception):
    """Any LLM provider failure (name kept for backward compatibility with server.py)."""

    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def _truncate(text):
    text = str(text).strip()
    if len(text) > _MAX_REPLY_CHARS:
        return text[:_MAX_REPLY_CHARS] + "\n…（已截断）"
    return text


def _call_minimax_anthropic(user_text):
    """
    MiniMax via Anthropic-compatible HTTP API (no anthropic package; works on Python 3.6+).
    POST {ANTHROPIC_BASE_URL}/v1/messages — same shape as Anthropic Messages API.
    """
    api_key = (
        (os.getenv("ANTHROPIC_API_KEY") or os.getenv("MINIMAX_API_KEY") or "").strip()
    )
    base_url = (
        os.getenv("ANTHROPIC_BASE_URL") or "https://api.minimax.io/anthropic"
    ).rstrip("/")
    model = (os.getenv("MINIMAX_MODEL") or "MiniMax-M2.7").strip()
    system_prompt = (os.getenv("MINIMAX_SYSTEM") or "You are a helpful assistant.").strip()
    api_version = (os.getenv("ANTHROPIC_VERSION") or "2023-06-01").strip()
    try:
        max_tokens = int(os.getenv("MINIMAX_MAX_TOKENS") or "4096")
    except ValueError:
        max_tokens = 4096

    if not api_key:
        raise PackyApiError("MiniMax: ANTHROPIC_API_KEY（或 MINIMAX_API_KEY）未配置")

    url = "{}/v1/messages".format(base_url)
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": api_version,
    }
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [
            {
                "role": "user",
                "content": [{"type": "text", "text": user_text}],
            }
        ],
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=120)

    if resp.status_code != 200:
        snippet = (resp.text or "")[:500]
        logging.error("MiniMax HTTP %s: %s", resp.status_code, snippet)
        raise PackyApiError(
            "MiniMax: 服务不可用（HTTP {}）".format(resp.status_code),
            status_code=resp.status_code,
        )

    try:
        data = resp.json()
    except ValueError as e:
        logging.error("MiniMax invalid JSON: %s", (resp.text or "")[:500])
        raise PackyApiError("MiniMax: 返回格式异常") from e

    err = data.get("error")
    if err:
        msg = err.get("message") if isinstance(err, dict) else str(err)
        logging.error("MiniMax error field: %s", msg)
        raise PackyApiError("MiniMax: {}".format(msg))

    parts = []
    for block in data.get("content") or []:
        if not isinstance(block, dict):
            continue
        bt = block.get("type")
        if bt == "text":
            parts.append(block.get("text") or "")
        # skip "thinking" and other types

    text = "".join(parts).strip()
    if not text:
        raise PackyApiError("MiniMax: 模型无文本内容")
    return _truncate(text)


def _call_packy(user_text):
    """POST OpenAI-compatible /chat/completions to PackyAPI."""
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
            "Packy: 模型服务暂时不可用（HTTP {}）".format(resp.status_code),
            status_code=resp.status_code,
        )

    try:
        data = resp.json()
    except ValueError as e:
        logging.error("PackyAPI invalid JSON: %s", (resp.text or "")[:500])
        raise PackyApiError("Packy: 模型返回格式异常") from e

    err = data.get("error")
    if err:
        msg = err.get("message") if isinstance(err, dict) else str(err)
        logging.error("PackyAPI error field: %s", msg)
        raise PackyApiError("Packy: 模型错误: {}".format(msg))

    choices = data.get("choices") or []
    if not choices:
        logging.error("PackyAPI empty choices: %s", json.dumps(data)[:500])
        raise PackyApiError("Packy: 模型无返回内容")

    msg = choices[0].get("message") or {}
    content = msg.get("content")
    if content is None:
        raise PackyApiError("Packy: 模型无文本内容")

    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(p.get("text") or "")
            elif isinstance(p, str):
                parts.append(p)
        content = "".join(parts)

    return _truncate(content)


_PROVIDERS = {
    "minimax": _call_minimax_anthropic,
    "packy": _call_packy,
}


def chat_completion(user_text):
    """
    Try providers in LLM_PROVIDER_ORDER (comma-separated).
    Names: minimax, packy. First success wins; on failure logs and falls back.
    """
    raw = (os.getenv("LLM_PROVIDER_ORDER") or _DEFAULT_ORDER).strip()
    names = [n.strip().lower() for n in raw.split(",") if n.strip()]

    errors = []
    for name in names:
        fn = _PROVIDERS.get(name)
        if not fn:
            logging.warning("Unknown LLM provider skipped: %s", name)
            errors.append("{}: unknown provider".format(name))
            continue
        try:
            return fn(user_text)
        except PackyApiError as e:
            logging.warning("LLM provider %s failed: %s", name, e)
            errors.append("{}: {}".format(name, e))
        except Exception as e:
            logging.exception("LLM provider %s unexpected error", name)
            errors.append("{}: {}".format(name, str(e)))

    # All failed
    detail = "; ".join(errors) if errors else "no providers configured"
    raise PackyApiError("所有模型均不可用: {}".format(detail))
