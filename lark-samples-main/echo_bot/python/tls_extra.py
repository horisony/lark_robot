"""企业 TLS：自签证书 / 调试关闭校验。在 main() 里、wsClient.start() 之前调用。"""
from __future__ import annotations

import logging
import os
import ssl
import sys
import warnings
from typing import Any, Callable


def _truthy(name: str) -> bool:
    v = (os.getenv(name) or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def apply_feishu_tls_workarounds() -> None:
    insecure = _truthy("FEISHU_INSECURE_SSL")
    ca_path = os.getenv("FEISHU_SSL_CA_BUNDLE")
    if ca_path:
        ca_path = ca_path.strip()
    if not ca_path:
        ca_path = None

    if not insecure and not ca_path:
        return

    if ca_path and not os.path.isfile(ca_path):
        logging.error("FEISHU_SSL_CA_BUNDLE is not a file: %s", ca_path)
        sys.exit(1)

    import requests

    _post: Callable[..., Any] = requests.post

    def post_patched(*args: Any, **kwargs: Any) -> Any:
        if insecure:
            kwargs.setdefault("verify", False)
        elif ca_path:
            kwargs.setdefault("verify", ca_path)
        return _post(*args, **kwargs)

    requests.post = post_patched  # type: ignore[assignment]

    import websockets

    _connect = websockets.connect

    def _ssl_context_for_wss() -> ssl.SSLContext:
        if insecure:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        return ssl.create_default_context(cafile=ca_path)

    def connect_patched(uri: Any, *args: Any, **kwargs: Any) -> Any:
        u = uri if isinstance(uri, str) else str(uri)
        if u.startswith("wss:") and kwargs.get("ssl") is None:
            kwargs["ssl"] = _ssl_context_for_wss()
        return _connect(uri, *args, **kwargs)

    websockets.connect = connect_patched  # type: ignore[assignment]

    if insecure:
        try:
            import urllib3

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass
        warnings.warn(
            "FEISHU_INSECURE_SSL is set: TLS verification is disabled. Do not use in production.",
            UserWarning,
            stacklevel=1,
        )
    else:
        logging.info("Using custom CA bundle for TLS: %s", ca_path)
