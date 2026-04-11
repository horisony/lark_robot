#!/usr/bin/env python3
"""Interactive setup: write .env with APP_ID and APP_SECRET (optional LARK_DOMAIN)."""

from __future__ import annotations

import os
from getpass import getpass
from pathlib import Path


def _quote_env_value(value: str) -> str:
    if value == "":
        return ""
    if any(c in value for c in ' \n\\"\'#=$'):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def main() -> None:
    base = Path(__file__).resolve().parent
    env_path = base / ".env"
    if env_path.exists():
        ans = input(f"{env_path} already exists. Overwrite? [y/N]: ").strip().lower()
        if ans not in ("y", "yes"):
            print("Aborted.")
            return

    print("Paste credentials from Feishu Open Platform → Credentials & Basic Info.")
    app_id = input("APP_ID (cli_...): ").strip()
    app_secret = getpass("APP_SECRET (hidden): ").strip()
    if not app_id or not app_secret:
        print("APP_ID and APP_SECRET are required.")
        raise SystemExit(1)

    default_domain = "https://open.feishu.cn"
    domain_in = input(f"LARK_DOMAIN [{default_domain}]: ").strip() or default_domain

    print()
    print(
        "TLS：若出现 certificate verify failed / self-signed certificate（公司代理常见），"
        "可填公司根证书 PEM 路径；或仅在本地调试时关闭校验。"
    )
    ca_path = input("FEISHU_SSL_CA_BUNDLE（.pem 绝对路径，无则回车跳过）: ").strip()
    if ca_path and not os.path.isfile(ca_path):
        print(f"Warning: file not found: {ca_path} — skipping FEISHU_SSL_CA_BUNDLE")
        ca_path = ""

    insecure_ans = (
        input("仅调试：关闭 TLS 校验 FEISHU_INSECURE_SSL=1 ? [y/N]: ").strip().lower()
    )
    insecure = insecure_ans in ("y", "yes")

    print()
    print("PackyAPI：POST /v1/chat/completions（Bearer + OpenAI 兼容 JSON）")
    packy_key = getpass("PACKY_API_KEY（必填，隐藏输入）: ").strip()
    if not packy_key:
        print("PACKY_API_KEY is required.")
        raise SystemExit(1)
    default_packy_base = "https://www.packyapi.com/v1"
    packy_base = input(f"PACKY_API_BASE [{default_packy_base}]: ").strip() or default_packy_base
    default_model = "claude-opus-4-6"
    packy_model = input(f"PACKY_MODEL [{default_model}]: ").strip() or default_model

    lines = [
        f"APP_ID={_quote_env_value(app_id)}",
        f"APP_SECRET={_quote_env_value(app_secret)}",
        f"LARK_DOMAIN={_quote_env_value(domain_in)}",
        "LOG_LEVEL=INFO",
    ]
    if ca_path:
        lines.append(f"FEISHU_SSL_CA_BUNDLE={_quote_env_value(ca_path)}")
    if insecure:
        lines.append("FEISHU_INSECURE_SSL=1")
    lines.append(f"PACKY_API_KEY={_quote_env_value(packy_key)}")
    lines.append(f"PACKY_API_BASE={_quote_env_value(packy_base)}")
    lines.append(f"PACKY_MODEL={_quote_env_value(packy_model)}")
    lines.append("")
    text = "\n".join(lines)
    old_umask = os.umask(0o077)
    try:
        env_path.write_text(text, encoding="utf-8")
    finally:
        os.umask(old_umask)
    try:
        env_path.chmod(0o600)
    except OSError:
        pass
    print(f"Wrote {env_path} (permissions 600).")
    print("Next: python3 main.py   or   docker compose up --build")


if __name__ == "__main__":
    main()
