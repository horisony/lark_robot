#!/usr/bin/env python3
"""
根据用户消息从 echo_bot/python/skills/<id>/ 下选择技能（读 YAML frontmatter + 正文），
可选走一轮轻量 LLM 路由（SKILL_ROUTER=llm）。
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

_BASE = Path(__file__).resolve().parent
_SKILLS_ROOT = Path(os.environ.get("SKILLS_DIR") or (_BASE / "skills")).resolve()

# 未在 YAML 写 router_keywords 时，按 skill 目录名使用的默认词（与子目录名对齐）
_DEFAULT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "BaoAI-strategy": (
        "转型",
        "商业模式",
        "战略规划",
        "战略报告",
        "商业战略",
        "企业战略",
        "七章",
        "营收",
        "竞争",
        "定价策略",
        "定价",
        "天势",
        "人谋",
        "主要矛盾",
        "根据地",
        "麦肯锡",
        "执行体系",
        "产业落地",
        "资源整合",
        "联盟",
        "风险",
        "创始人",
        "战役",
        "最小可行",
        "SaaS",
        "平台型",
        "品牌型",
    ),
    "IP": (
        "自媒体",
        "博主",
        "爆款",
        "口播",
        "口播稿",
        "选题",
        "粉丝",
        "个人ip",
        "人设",
        "内容矩阵",
        "叙事",
        "情感炸点",
        "账号运营",
        "账号",
        "带货",
        "视频文案",
        "拍摄",
        "年度日历",
        "内容策划",
        "短视频",
        "抖音",
        "小红书",
        "b站",
        "bilibili",
        "口播脚本",
        "文案",
        "个人品牌",
    ),
}


@dataclass(frozen=True)
class SkillEntry:
    skill_id: str
    path: Path
    name: str
    description: str
    body: str
    keywords: tuple[str, ...]


def _split_frontmatter(raw: str) -> tuple[dict, str]:
    raw = raw.lstrip("\ufeff")
    if not raw.startswith("---"):
        return {}, raw
    lines = raw.split("\n")
    if lines[0].strip() != "---":
        return {}, raw
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, raw
    block = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1 :])
    try:
        meta = yaml.safe_load(block) or {}
        if not isinstance(meta, dict):
            return {}, raw
        return meta, body
    except yaml.YAMLError:
        logging.warning("skill_router: YAML frontmatter parse failed, using raw body")
        return {}, raw


def _pick_markdown(skill_dir: Path) -> Path | None:
    direct = skill_dir / "SKILL.md"
    if direct.is_file():
        return direct
    candidates = sorted(skill_dir.glob("*_SKILL.md"))
    if candidates:
        return candidates[0]
    any_md = sorted(skill_dir.glob("*.md"))
    return any_md[0] if any_md else None


def discover_skills(skills_root: Path | None = None) -> list[SkillEntry]:
    root = skills_root or _SKILLS_ROOT
    out: list[SkillEntry] = []
    if not root.is_dir():
        return out
    for sub in sorted(root.iterdir()):
        if not sub.is_dir():
            continue
        md = _pick_markdown(sub)
        if md is None:
            continue
        try:
            text = md.read_text(encoding="utf-8")
        except OSError as e:
            logging.warning("skill_router: skip %s: %s", md, e)
            continue
        meta, body = _split_frontmatter(text)
        name = str(meta.get("name") or sub.name)
        desc = meta.get("description")
        if isinstance(desc, str):
            description = desc.strip()
        else:
            description = ""
        rk = meta.get("router_keywords")
        kws: list[str] = []
        if isinstance(rk, list):
            kws = [str(x).strip() for x in rk if str(x).strip()]
        elif isinstance(rk, str) and rk.strip():
            kws = [x.strip() for x in re.split(r"[,，\n]", rk) if x.strip()]
        if kws:
            keywords: tuple[str, ...] = tuple(dict.fromkeys(kws))
        else:
            keywords = _DEFAULT_KEYWORDS.get(sub.name, ())
        out.append(
            SkillEntry(
                skill_id=sub.name,
                path=md,
                name=name,
                description=description,
                body=body.strip(),
                keywords=keywords,
            )
        )
    return out


def _env_system_fallback() -> str:
    return (
        os.getenv("MINIMAX_SYSTEM") or os.getenv("SYSTEM_PROMPT") or "You are a helpful assistant."
    ).strip()


def _keyword_hit(haystack: str, kw: str) -> bool:
    """短英文词用边界匹配，其余用子串（忽略大小写）。"""
    kw = kw.strip()
    if not kw:
        return False
    if len(kw) <= 4 and kw.isascii() and kw.replace(".", "").isalnum():
        return (
            re.search(
                r"(?<![A-Za-z0-9])" + re.escape(kw) + r"(?![A-Za-z0-9])",
                haystack,
                re.I,
            )
            is not None
        )
    return kw.lower() in haystack.lower()


def _keyword_scores(user_text: str, entries: list[SkillEntry]) -> list[tuple[str, int]]:
    text = user_text or ""
    out: list[tuple[str, int]] = []
    for e in entries:
        if not e.keywords:
            out.append((e.skill_id, 0))
            continue
        s = sum(1 for kw in e.keywords if _keyword_hit(text, kw))
        out.append((e.skill_id, s))
    return out


def _route_keywords(user_text: str, entries: list[SkillEntry]) -> str | None:
    """
    关键词命中数最高且严格高于第二名则返回该 skill_id，否则 None（交 LLM）。
    """
    scores = _keyword_scores(user_text, entries)
    ranked = sorted(scores, key=lambda x: (-x[1], x[0]))
    if not ranked:
        return None
    best_id, best_s = ranked[0]
    second_s = ranked[1][1] if len(ranked) > 1 else 0
    if best_s <= 0:
        return None
    if best_s > second_s:
        logging.info(
            "skill_router: keyword winner skill_id=%s score=%s (runner-up=%s)",
            best_id,
            best_s,
            ranked[1] if len(ranked) > 1 else None,
        )
        return best_id
    logging.info(
        "skill_router: keyword tie or unclear scores=%s -> LLM",
        scores,
    )
    return None


def _parse_router_json(raw: str, entries: list[SkillEntry], default_id: str) -> str:
    text = (raw or "").strip()
    m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            sid = data.get("skill_id") or data.get("id")
            if isinstance(sid, str) and any(e.skill_id == sid for e in entries):
                return sid
        except json.JSONDecodeError:
            pass
    for e in entries:
        if e.skill_id in text:
            return e.skill_id
    return default_id


def _route_llm(user_text: str, entries: list[SkillEntry], default_id: str) -> str:
    from llm_client import PackyApiError, chat_completion

    lines = [
        "You are a skill router. Choose exactly one skill_id for the user message.",
        'Reply with ONLY JSON: {"skill_id":"<id>"} — no markdown fences, no extra keys, no explanation.',
        "Valid skill_id values:",
    ]
    for e in entries:
        desc = (e.description or e.name)[:600].replace("\n", " ")
        lines.append(f"- {e.skill_id} ({e.name}): {desc}")
    lines.append(f'If the message is small talk or ambiguous, use skill_id "{default_id}".')
    router_system = "\n".join(lines)
    try:
        raw = chat_completion(
            (user_text or "")[:8000],
            system=router_system,
            max_tokens=int(os.getenv("SKILL_ROUTER_MAX_TOKENS") or "256"),
        )
    except PackyApiError:
        raise
    except Exception as e:
        logging.warning("skill_router: router LLM failed: %s", e)
        return default_id
    chosen = _parse_router_json(raw, entries, default_id)
    logging.info("skill_router: chose skill_id=%s (default=%s)", chosen, default_id)
    return chosen


def select_skill_system(user_text: str) -> str:
    """
    返回本轮应答应使用的 system 字符串（技能正文或 env 回退）。
    """
    mode = (os.getenv("SKILL_ROUTER") or "llm").strip().lower()
    entries = discover_skills()

    if mode in ("0", "off", "false", "no"):
        return _env_system_fallback()

    if not entries:
        logging.info("skill_router: no skills under %s, using env SYSTEM", _SKILLS_ROOT)
        return _env_system_fallback()

    default_id = (os.getenv("SKILL_DEFAULT") or entries[0].skill_id).strip()
    fixed = None
    if mode.startswith("fixed:"):
        fixed = mode.split(":", 1)[1].strip()

    if fixed:
        for e in entries:
            if e.skill_id == fixed:
                logging.info("skill_router: fixed skill_id=%s", fixed)
                return e.body
        logging.warning("skill_router: fixed skill %r missing, using default", fixed)
        return next((e.body for e in entries if e.skill_id == default_id), entries[0].body)

    if len(entries) == 1:
        logging.info("skill_router: single skill %s", entries[0].skill_id)
        return entries[0].body

    if mode == "first":
        logging.info("skill_router: mode=first -> %s", entries[0].skill_id)
        return entries[0].body

    kw_first = (os.getenv("SKILL_ROUTER_KEYWORDS") or "1").strip().lower() not in (
        "0",
        "off",
        "false",
        "no",
    )
    if kw_first:
        kw_id = _route_keywords(user_text, entries)
        if kw_id is not None:
            for e in entries:
                if e.skill_id == kw_id:
                    return e.body

    chosen_id = _route_llm(user_text, entries, default_id)
    for e in entries:
        if e.skill_id == chosen_id:
            return e.body
    return next((e.body for e in entries if e.skill_id == default_id), entries[0].body)
