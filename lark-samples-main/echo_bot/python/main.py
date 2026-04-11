import json
import logging
import os
import sys

# 须在 import lark_oapi 之前：从 .env 注入 APP_ID / APP_SECRET（lark 从 os.environ 读取）
_BASE = os.path.dirname(os.path.abspath(__file__))
try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(_BASE, ".env"))
except ImportError:
    pass

import lark_oapi as lark
from lark_oapi.api.im.v1 import *


def _lark_domain() -> str:
    return (os.getenv("LARK_DOMAIN") or "https://open.feishu.cn").strip() or "https://open.feishu.cn"


# 注册接收消息事件，处理接收到的消息。
# Register event handler to handle received messages.
# https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message/events/receive
def do_p2_im_message_receive_v1(data: P2ImMessageReceiveV1) -> None:
    res_content = ""
    if data.event.message.message_type == "text":
        res_content = json.loads(data.event.message.content)["text"]
    else:
        res_content = "解析消息失败，请发送文本消息\nparse message failed, please send text message"

    content = json.dumps(
        {
            "text": "收到你发送的消息："
            + res_content
            + "\nReceived message:"
            + res_content
        }
    )

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
        # 使用OpenAPI发送消息
        # Use send OpenAPI to send messages
        # https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message/create
        response = client.im.v1.message.create(request)

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
        # 使用OpenAPI回复消息
        # Reply to messages using send OpenAPI
        # https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/im-v1/message/reply
        response: ReplyMessageResponse = client.im.v1.message.reply(request)
        if not response.success():
            raise Exception(
                f"client.im.v1.message.reply failed, code: {response.code}, msg: {response.msg}, log_id: {response.get_log_id()}"
            )


# 注册事件回调
# Register event handler.
event_handler = (
    lark.EventDispatcherHandler.builder("", "")
    .register_p2_im_message_receive_v1(do_p2_im_message_receive_v1)
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
    from tls_extra import apply_feishu_tls_workarounds

    apply_feishu_tls_workarounds()
    logging.info("LARK_DOMAIN=%s", _lark_domain())
    # 启动长连接，并注册事件处理器。
    # Start long connection and register event handler.
    wsClient.start()


if __name__ == "__main__":
    main()
