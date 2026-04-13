import json
import logging
import os
import sys
import threading
import time

# region agent log
_AGENT_SESSION = "d3cb0b"


def _agent_debug_log(hypothesis_id: str, location: str, message: str, data: dict) -> None:
    """NDJSON for debug session + always logging.info for remote docker logs."""
    payload = {
        "sessionId": _AGENT_SESSION,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data,
        "timestamp": int(time.time() * 1000),
    }
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    _here = os.path.dirname(os.path.abspath(__file__))
    for path in (
        os.environ.get("DEBUG_AGENT_LOG"),
        "/Users/baoling/lark-samples-main/.cursor/debug-d3cb0b.log",
        os.path.join(_here, ".cursor", "debug-d3cb0b.log"),
        os.path.join(_here, "debug_agent_d3cb0b.ndjson"),
    ):
        if not path:
            continue
        try:
            d = os.path.dirname(path)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            continue
    logging.warning("AGENT_DEBUG %s", line.strip())


# endregion

# 须在 import lark_oapi 之前：从 .env 注入 APP_ID / APP_SECRET（lark 从 os.environ 读取）
_BASE = os.path.dirname(os.path.abspath(__file__))
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(_BASE, ".env"))
except ImportError:
    pass

import lark_oapi as lark
from lark_oapi.api.im.v1 import *

from llm_client import PackyApiError, chat_completion
from skill_router import select_skill_system
from skill_executor import execute_skill
from session_store import get_session_store, SessionData

# 长连接可能对同一事件至少投递一次以上：按 message_id + event_id 幂等去重
_dedupe_lock = threading.Lock()
_dedupe_seen_at: dict[str, float] = {}

# 同一会话短时间内多条消息：只处理最后一条（可选 MESSAGE_DEBOUNCE_SEC）
_debounce_lock = threading.Lock()
_debounce_timers: dict[str, threading.Timer] = {}
_debounce_pending: dict[str, object] = {}


def _dedupe_key_for_event(message_id: object, event_id: object) -> str | None:
    """
    默认只按 message_id 去重：长连接重投可能换 event_id，若用 m|e 组合会误判为「新事件」再次回复。
    需要旧行为时设置 DEDUPE_INCLUDE_EVENT_ID=1。
    """
    mid = str(message_id).strip() if message_id else ""
    eid = str(event_id).strip() if event_id else ""
    if mid and eid and (os.getenv("DEDUPE_INCLUDE_EVENT_ID") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return f"m:{mid}|e:{eid}"
    if mid:
        return f"m:{mid}"
    if eid:
        return f"e:{eid}"
    return None


def _message_age_sec(msg: object) -> float | None:
    ct = getattr(msg, "create_time", None)
    if ct is None:
        return None
    try:
        ms = int(str(ct).strip())
    except ValueError:
        return None
    now_ms = int(time.time() * 1000)
    return (now_ms - ms) / 1000.0


def _should_skip_duplicate(key: str | None) -> bool:
    if not key:
        return False
    ttl = float(os.getenv("DEDUPE_TTL_SEC") or "600")
    now = time.monotonic()
    with _dedupe_lock:
        for k, t in list(_dedupe_seen_at.items()):
            if now - t > ttl:
                del _dedupe_seen_at[k]
        if key in _dedupe_seen_at:
            return True
        _dedupe_seen_at[key] = now
        return False


def _reply_to_thread_messages_enabled() -> bool:
    v = (os.getenv("REPLY_TO_THREAD_MESSAGES") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _flush_debounced(chat_key: str) -> None:
    with _debounce_lock:
        data = _debounce_pending.pop(chat_key, None)
        _debounce_timers.pop(chat_key, None)
    if data is None:
        return
    _msg = getattr(getattr(data, "event", None), "message", None)
    _mid = getattr(_msg, "message_id", None) if _msg is not None else None
    _agent_debug_log(
        "DEBOUNCE",
        "main.py:_flush_debounced",
        "debounce_flushed",
        {"chat_key": chat_key, "message_id": _mid, "age_sec": _message_age_sec(_msg) if _msg is not None else None},
    )
    try:
        _process_im_message(data)  # type: ignore[arg-type]
    except Exception:
        logging.exception("debounced message processing failed")


def _process_im_message(data: P2ImMessageReceiveV1) -> None:
    msg = data.event.message
    mid = getattr(msg, "message_id", None)

    res_content = ""
    if data.event.message.message_type == "text":
        res_content = json.loads(data.event.message.content)["text"]
    else:
        res_content = ""

    _preview = (res_content or "").replace("\n", " ")[:120]
    _agent_debug_log(
        "H6",
        "main.py:_process_im_message",
        "llm_input_preview",
        {"message_id": mid, "text_len": len(res_content or ""), "preview": _preview},
    )

    if not res_content.strip():
        reply_plain = "请发送文本消息\nPlease send a text message"
    else:
        # 获取会话上下文
        chat_id = getattr(msg, "chat_id", "unknown")
        sender = getattr(data.event, "sender", None)
        user_id = None
        if sender:
            sid = getattr(sender, "sender_id", None)
            if sid:
                user_id = getattr(sid, "open_id", None) or getattr(sid, "union_id", None)
        
        session_store = get_session_store()
        session = session_store.get(chat_id)
        
        # 准备执行上下文
        context = {
            "chat_id": chat_id,
            "user_id": user_id,
            "message_id": mid,
            "history": session.history[-10:],  # 最近 10 条消息
            "vars": session.vars,
        }
        
        # 保存用户消息到历史
        session_store.add_message(chat_id, "user", res_content, {"message_id": mid})
        
        try:
            # 使用新的技能执行器
            result = execute_skill(res_content, context)
            
            # 处理结果
            if "error" in result:
                reply_plain = f"技能执行失败：{result['error']}"
                logging.error(f"Skill execution error: {result['error']}")
            elif "text" in result:
                reply_plain = result["text"]
                # 保存助手回复到历史
                session_store.add_message(chat_id, "assistant", reply_plain, {"message_id": mid})
            else:
                reply_plain = "技能未返回有效内容"
                
        except PackyApiError as e:
            reply_plain = str(e)
            logging.exception("PackyAPI call failed: %s", e)
        except Exception as e:
            logging.exception("Skill execution failed: %s", e)
            reply_plain = "模型调用失败，请稍后重试"

    content = json.dumps({"text": reply_plain}, ensure_ascii=False)

    if data.event.message.chat_type == "p2p":
        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(data.event.message.chat_id)
                .msg_type("text")
                .content(content)
                .build()
            )
            .build()
        )
        response = client.im.v1.message.create(request)
        _agent_debug_log(
            "H1-H5",
            "main.py:do_p2:p2p_sent",
            "message.create_done",
            {"message_id": mid, "success": response.success()},
        )

        if not response.success():
            raise Exception(
                f"client.im.v1.message.create failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}"
            )
    else:
        request: ReplyMessageRequest = (
            ReplyMessageRequest.builder()
            .message_id(data.event.message.message_id)
            .request_body(
                ReplyMessageRequestBody.builder()
                .content(content)
                .msg_type("text")
                .build()
            )
            .build()
        )
        response: ReplyMessageResponse = client.im.v1.message.reply(request)
        _agent_debug_log(
            "H1-H5",
            "main.py:do_p2:group_reply_sent",
            "message.reply_done",
            {"in_message_id": mid, "success": response.success()},
        )

        if not response.success():
            raise Exception(
                f"client.im.v1.message.reply failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}"
            )


def _lark_domain() -> str:
    return (os.getenv("LARK_DOMAIN") or "https://open.feishu.cn").strip() or "https://open.feishu.cn"


# 注册接收消息事件，处理接收到的消息。
# Register event handler to handle received messages.
# https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message/events/receive
def do_p2_im_message_receive_v1(data: P2ImMessageReceiveV1) -> None:
    msg = data.event.message
    mid = getattr(msg, "message_id", None)
    chat_id = getattr(msg, "chat_id", None)
    chat_type = getattr(msg, "chat_type", None)
    sender = getattr(data.event, "sender", None)
    sender_oid = None
    sender_type = getattr(sender, "sender_type", None) if sender is not None else None
    if sender is not None:
        sid = getattr(sender, "sender_id", None)
        if sid is not None:
            sender_oid = getattr(sid, "open_id", None) or getattr(sid, "union_id", None)
    header = getattr(data, "header", None)
    event_id = getattr(header, "event_id", None) if header is not None else None
    try:
        debounce_sec = float((os.getenv("MESSAGE_DEBOUNCE_SEC") or "0").strip() or "0")
    except ValueError:
        debounce_sec = 0.0
    _age = _message_age_sec(msg)
    _agent_debug_log(
        "H1-H6",
        "main.py:do_p2_im_message_receive_v1:entry",
        "handler_invoked",
        {
            "pid": os.getpid(),
            "message_id": mid,
            "event_id": event_id,
            "dedupe_key_will_be": _dedupe_key_for_event(mid, event_id),
            "chat_id": chat_id,
            "chat_type": chat_type,
            "sender_type": sender_type,
            "sender_open_id_or_union": sender_oid,
            "msg_type": getattr(msg, "message_type", None),
            "message_age_sec": _age,
            "debounce_sec_config": debounce_sec,
        },
    )

    # 应用机器人自己发出的消息也会走 receive_v1，若不跳过可能形成自激或「过一会又回一条」的错觉
    if (sender_type or "").lower() == "app":
        _agent_debug_log(
            "H3",
            "main.py:do_p2_im_message_receive_v1:sender",
            "skipped_sender_app",
            {"message_id": mid, "sender_type": sender_type},
        )
        return

    dk = _dedupe_key_for_event(mid, event_id)
    _ttl = float(os.getenv("DEDUPE_TTL_SEC") or "600")
    if _should_skip_duplicate(dk):
        _agent_debug_log(
            "H1",
            "main.py:do_p2_im_message_receive_v1:dedupe",
            "duplicate_event_skipped",
            {
                "dedupe_key": dk,
                "message_id": mid,
                "event_id": event_id,
                "dedupe_ttl_sec": _ttl,
                "message_age_sec": _age,
            },
        )
        return

    # 话题/线程内回复会带 parent_id：每条都是独立事件，默认只处理「顶层」消息，避免跟历史一条条回
    parent_id = getattr(msg, "parent_id", None)
    if parent_id and not _reply_to_thread_messages_enabled():
        _agent_debug_log(
            "THREAD",
            "main.py:do_p2_im_message_receive_v1:thread",
            "skipped_thread_reply",
            {"parent_id": parent_id, "message_id": mid, "root_id": getattr(msg, "root_id", None)},
        )
        return

    # H1/H2: 若消息创建时间距现在很久仍进入处理，多为长连接重投/补投旧事件（去重 TTL 已过期）
    _stale_thr = float((os.getenv("DEBUG_STALE_MESSAGE_SEC") or "300").strip() or "300")
    _redelivery_suspect = _age is not None and _age > _stale_thr
    _agent_debug_log(
        "H1-H2",
        "main.py:do_p2_im_message_receive_v1:post_dedupe",
        "will_process_after_dedupe",
        {
            "pid": os.getpid(),
            "message_id": mid,
            "event_id": event_id,
            "dedupe_key": dk,
            "dedupe_ttl_sec": _ttl,
            "message_age_sec": _age,
            "redelivery_suspect": _redelivery_suspect,
            "stale_threshold_sec": _stale_thr,
        },
    )

    if debounce_sec > 0:
        chat_key = str(chat_id or "default")
        with _debounce_lock:
            old = _debounce_timers.pop(chat_key, None)
            if old is not None:
                try:
                    old.cancel()
                except Exception:
                    pass
            _debounce_pending[chat_key] = data
            t = threading.Timer(debounce_sec, lambda k=chat_key: _flush_debounced(k))
            t.daemon = True
            _debounce_timers[chat_key] = t
            t.start()
        _agent_debug_log(
            "DEBOUNCE",
            "main.py:do_p2_im_message_receive_v1:debounce",
            "debounce_scheduled",
            {"chat_key": chat_key, "sec": debounce_sec, "message_id": mid},
        )
        return

    _process_im_message(data)


def do_p2_im_message_message_read_v1(_data: P2ImMessageMessageReadV1) -> None:
    """
    消息已读回执（im.message.message_read_v1）。
    若在开放平台订阅了该事件，必须注册处理器，否则长连接会报 processor not found。
    不触发任何回复。
    """
    return


# 注册事件回调
# Register event handler.
event_handler = (
    lark.EventDispatcherHandler.builder("", "")
    .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1)
    .register_p2_im_message_message_read_v1(do_p2_im_message_message_read_v1)
    .build()
)


# 创建 LarkClient 对象，用于请求OpenAPI, 并创建 LarkWSClient 对象，用于使用长连接接收事件。
# Create LarkClient object for requesting OpenAPI, and create LarkWSClient object for receiving events using long connection.
client = (
    lark.Client.builder()
    .app_id(lark.APP_ID)
    .app_secret(lark.APP_SECRET)
    .domain(_lark_domain())
    .build()
)
wsClient = lark.ws.Client(
    lark.APP_ID,
    lark.APP_SECRET,
    event_handler=event_handler,
    log_level=lark.LogLevel.DEBUG,
    domain=_lark_domain(),
)


def main() -> None:
    lv = (os.getenv("LOG_LEVEL") or "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, lv, logging.INFO),
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if not lark.APP_ID or not lark.APP_SECRET:
        print(
            "缺少 APP_ID 或 APP_SECRET。请设置环境变量，或复制 .env.example 为 .env 并填写，或运行 python3 wizard.py",
            file=sys.stderr,
        )
        sys.exit(1)
    _has_mini = (os.getenv("ANTHROPIC_API_KEY") or os.getenv("MINIMAX_API_KEY") or "").strip()
    _has_packy = (os.getenv("PACKY_API_KEY") or "").strip()
    if not _has_mini and not _has_packy:
        print(
            "请至少配置其一：ANTHROPIC_API_KEY（MiniMax Anthropic 兼容）或 PACKY_API_KEY。见 .env.example",
            file=sys.stderr,
        )
        sys.exit(1)
    from tls_extra import apply_feishu_tls_workarounds

    apply_feishu_tls_workarounds()
    logging.info("LARK_DOMAIN=%s", _lark_domain())
    _agent_debug_log(
        "BOOT",
        "main.py:main",
        "startup_before_ws",
        {
            "pid": os.getpid(),
            "build": "agent-d3cb0b",
            "dedupe_ttl_sec": float(os.getenv("DEDUPE_TTL_SEC") or "600"),
            "debounce_sec": float((os.getenv("MESSAGE_DEBOUNCE_SEC") or "0").strip() or "0"),
        },
    )
    # 启动长连接，并注册事件处理器。
    # Start long connection and register event handler.
    wsClient.start()


if __name__ == "__main__":
    main()
