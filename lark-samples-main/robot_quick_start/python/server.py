#!/usr/bin/env python3.8

import json
import logging
import os
import requests
from api import MessageApiClient
from event import MessageReceiveEvent, UrlVerificationEvent, EventManager
from flask import Flask, jsonify
from dotenv import load_dotenv

from llm_client import PackyApiError, chat_completion

# Always load .env beside this file (Gunicorn cwd may differ).
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_BASE_DIR, ".env"))

app = Flask(__name__)

# load from env
APP_ID = os.getenv("APP_ID")
APP_SECRET = os.getenv("APP_SECRET")
VERIFICATION_TOKEN = (os.getenv("VERIFICATION_TOKEN") or "").strip()
ENCRYPT_KEY = (os.getenv("ENCRYPT_KEY") or "").strip()
LARK_HOST = os.getenv("LARK_HOST")

# init service
message_api_client = MessageApiClient(APP_ID, APP_SECRET, LARK_HOST)
event_manager = EventManager()


@event_manager.register("url_verification")
def request_url_verify_handler(req_data: UrlVerificationEvent):
    # url verification, just need return challenge
    if req_data.event.token != VERIFICATION_TOKEN:
        raise Exception("VERIFICATION_TOKEN is invalid")
    return jsonify({"challenge": req_data.event.challenge})


@event_manager.register("im.message.receive_v1")
def message_receive_event_handler(req_data: MessageReceiveEvent):
    sender_id = req_data.event.sender.sender_id
    message = req_data.event.message
    if message.message_type != "text":
        logging.warning("Other types of messages have not been processed yet")
        return jsonify()

    try:
        body = json.loads(message.content)
        user_text = body.get("text") or ""
    except (TypeError, ValueError):
        logging.warning("Failed to parse text message content")
        return jsonify()

    try:
        reply_plain = chat_completion(user_text)
    except PackyApiError as e:
        reply_plain = str(e)
    except Exception as e:
        logging.exception("PackyAPI call failed: %s", e)
        reply_plain = "模型调用失败，请稍后重试"

    content_json = json.dumps({"text": reply_plain}, ensure_ascii=False)

    chat_type = getattr(message, "chat_type", None) or "p2p"
    if chat_type == "p2p":
        open_id = sender_id.open_id
        message_api_client.send_text_with_open_id(open_id, content_json)
    else:
        message_id = getattr(message, "message_id", None)
        if not message_id:
            logging.error("Missing message_id for non-p2p chat")
            return jsonify()
        message_api_client.reply_text(message_id, content_json)

    return jsonify()


@app.errorhandler(Exception)
def msg_error_handler(ex):
    logging.error(ex)
    response = jsonify(message=str(ex))
    response.status_code = (
        ex.response.status_code if isinstance(ex, requests.HTTPError) else 500
    )
    return response


@app.route("/", methods=["POST"])
def callback_event_handler():
    # init callback instance and handle
    event_handler, event = event_manager.get_handler_with_event(VERIFICATION_TOKEN, ENCRYPT_KEY)

    return event_handler(event)


if __name__ == "__main__":
    # Allow overriding port to avoid collisions with other local services.
    port = int(os.getenv("PORT", "3000"))
    app.run(host="0.0.0.0", port=port, debug=True)
