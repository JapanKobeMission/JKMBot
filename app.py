from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from googletrans import Translator

import os

app = Flask(__name__)

# LINE credentials from environment variables
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

translator = Translator()

@app.route("/")
def health_check():
    return "Bot is running!"

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers["X-Line-Signature"]
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text

    # Detect language
    lang = 'ja' if all(ord(c) < 128 for c in text) else 'en'

    try:
        translated = translator.translate(text, dest=lang).text
    except Exception as e:
        translated = "Translation error: " + str(e)

    reply = TextSendMessage(text=translated)
    line_bot_api.reply_message(event.reply_token, reply)

