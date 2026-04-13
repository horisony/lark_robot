#!/usr/bin/env python3
"""
多模型：优先 MiniMax（Anthropic 兼容 API），失败则回退 Packy（OpenAI 兼容 /chat/completions）。
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

import requests

_MAX_REPLY_CHARS = 12000


class PackyApiError(Exception):
    """LLM 调用失败（历史名称，含 MiniMax / Packy）。"""

    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


def _truncate(text: str) -> str:
    text = text.strip()
    if len(text) > _MAX_REPLY_CHARS:
        return text[:_MAX_REPLY_CHARS] + "\n…（已截断）"
    return text


def _anthropic_message_to_text(message: Any) -> str:
    parts: list[str] = []
    for block in message.content:
        t = getattr(block, "type", None)
        if t == "text":
            parts.append(getattr(block, "text", "") or "")
    s = "".join(parts).strip()
    if s:
        return _truncate(s)
    raise PackyApiError("MiniMax 无文本回复（仅 thinking 等）")


def _effective_system(override: str | None) -> str:
    if override is not None:
        s = override.strip()
        if s:
            return s
    return (
        os.getenv("MINIMAX_SYSTEM")
        or os.getenv("SYSTEM_PROMPT")
        or "You are a helpful assistant."
    ).strip()


def _minimax_anthropic(
    user_text: str,
    system_override: str | None = None,
    max_tokens_override: int | None = None,
) -> str:
    """MiniMax via Anthropic-compatible API (官方文档 base_url + messages.create)."""
    import anthropic

    logging.info("LLM: calling MiniMax via Anthropic-compatible API (base=%s)", os.getenv("ANTHROPIC_BASE_URL", "https://api.minimax.io/anthropic"))

    api_key = (os.getenv("ANTHROPIC_API_KEY") or os.getenv("MINIMAX_API_KEY") or "").strip()
    if not api_key:
        raise PackyApiError("ANTHROPIC_API_KEY / MINIMAX_API_KEY is not set")

    base = (os.getenv("ANTHROPIC_BASE_URL") or "https://api.minimax.io/anthropic").rstrip("/")
    model = (os.getenv("MINIMAX_MODEL") or "MiniMax-M2.7").strip()
    if max_tokens_override is not None:
        max_tokens = max_tokens_override
    else:
        max_tokens = int(os.getenv("MINIMAX_MAX_TOKENS") or "4096")
    system = _effective_system(system_override)

    client = anthropic.Anthropic(api_key=api_key, base_url=base)
    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[
            {
                "role": "user",
                "content": [{"type": "text", "text": user_text}],
            }
        ],
    )
    return _anthropic_message_to_text(message)


def _packy_openai(
    user_text: str,
    system_override: str | None = None,
    max_tokens_override: int | None = None,
) -> str:
    """OpenAI-compatible POST .../chat/completions（Packy 等）。"""
    logging.info("LLM: calling Packy/OpenAI-compatible API (base=%s)", os.getenv("PACKY_API_BASE", "https://www.packyapi.com/v1"))

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
    system = _effective_system(system_override)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_text},
    ]
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if max_tokens_override is not None:
        payload["max_tokens"] = max_tokens_override

    resp = requests.post(url, headers=headers, json=payload, timeout=120)

    if resp.status_code != 200:
        snippet = (resp.text or "")[:500]
        logging.error("Packy(OpenAI兼容) HTTP %s: %s", resp.status_code, snippet)
        raise PackyApiError(
            "Packy 备用接口不可用（HTTP {}），非 MiniMax 直连错误。响应片段: {}".format(
                resp.status_code, snippet[:200]
            ),
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

    return _truncate(str(content))


def _no_packy_fallback() -> bool:
    return (os.getenv("LLM_DISABLE_PACKY_FALLBACK") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def chat_completion(
    user_text: str,
    system: str | None = None,
    *,
    max_tokens: int | None = None,
) -> str:
    """
    优先 MiniMax（已配置 ANTHROPIC_API_KEY 或 MINIMAX_API_KEY 时）；
    失败则回退 Packy（PACKY_API_KEY），除非 LLM_DISABLE_PACKY_FALLBACK=1。
    仅配其一则只走该路。

    system: 非 None 时作为系统提示（覆盖 MINIMAX_SYSTEM / SYSTEM_PROMPT）。
    max_tokens: 非 None 时覆盖 MINIMAX_MAX_TOKENS（用于路由等短输出）。
    """
    has_minimax = bool(
        (os.getenv("ANTHROPIC_API_KEY") or os.getenv("MINIMAX_API_KEY") or "").strip()
    )
    has_packy = bool((os.getenv("PACKY_API_KEY") or "").strip())

    if not has_minimax and not has_packy:
        raise PackyApiError("请配置 ANTHROPIC_API_KEY（MiniMax）或 PACKY_API_KEY")

    if has_minimax:
        try:
            return _minimax_anthropic(user_text, system, max_tokens)
        except Exception as e:
            logging.warning(
                "MiniMax 调用失败，将尝试说明见下；是否回退 Packy=%s",
                has_packy and not _no_packy_fallback(),
                exc_info=True,
            )
            err_mini = "{}: {}".format(type(e).__name__, e)
            if has_packy and not _no_packy_fallback():
                try:
                    return _packy_openai(user_text, system, max_tokens)
                except Exception as e2:
                    raise PackyApiError(
                        "MiniMax 失败: {}；备用 Packy 也失败: {}: {}".format(
                            err_mini, type(e2).__name__, e2
                        )
                    ) from e2
            raise PackyApiError(
                "MiniMax 失败（未使用或未成功 Packy 备用）: {}".format(err_mini)
            ) from e

    return _packy_openai(user_text, system, max_tokens)
