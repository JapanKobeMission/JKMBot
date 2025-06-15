from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from googletrans import Translator
import re
import os

app = Flask(__name__)

# LINE credentials from environment variables
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

translator = Translator()

# Helper regex patterns
JP_SUBSTRING_PATTERN = re.compile(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uff66-\uff9f]+')  # contiguous Japanese
ASCII_PATTERN = re.compile(r'[\u0000-\u007F]')

# Use unique, non-alphabetic placeholders (lowercase for consistency)
PLACEHOLDER_TEMPLATE = '__jp{}__'
PLACEHOLDER_REGEX = re.compile(r'__jp(\d+)__', re.IGNORECASE)
TERM_PLACEHOLDER_TEMPLATE = '__term{}__'
TERM_PLACEHOLDER_REGEX = re.compile(r'__term(\d+)__', re.IGNORECASE)

# Example custom vocabulary dictionaries
EN_TO_JA_TERMS = {
    'baptism': 'バプテスマ',
    'missionary': '宣教師',
    'missionaries': '宣教師たち',
    'the church of jesus christ of latter-day saints': '末日聖徒イエス・キリスト教会',
    'sacrament': '聖餐',
    'sacrament meeting': '聖餐会',
    'the book of mormon': 'モルモン書',
    'doctrine and covenants': '教義と聖約',
    'd&c': '教義と聖約',
    'pearl of great price': '高価なる真珠',
    'latter-day saints': '末日聖徒',
    'lds': '末日聖徒',
    'jesus christ': 'イエス・キリスト',
    'god': '神様',
    'japan kobe mission': '日本神戸伝道部',
    'mission': '伝道部',
    'missionary work': '伝道',
    'ward': 'ワード',
    'Nephi': 'ニーファイ',
    'Jacob': 'ヤコブ',
    'Enos': 'エノス',
    'Jarom': 'ジェロム',
    'Omni': 'オムナイ',
    'Mormon': 'モルモン',
    'Mosiah': 'モーサヤ',
    'Alma': 'アルマ',
    'Helaman': 'ヘラマン',
    'Ether': 'エテル',
    'Moroni': 'モロナイ',
    'kaichou': '会長',
    'member': '会員',
    'church member': '教会員',
    'members': '会員たち',
    'mission president': '伝道部会長',
    'law of chastity': '純潔の律法',
    'law of tithing': '什分の一の律法',
    'tithing': '什分の一',
    'zone conference': 'ゾーン大会',
    # Add more terms as needed
}
JA_TO_EN_TERMS = {
    'バプテスマ': 'baptism',
    '宣教師': 'missionary',
    '宣教師たち': 'missionaries',
    '末日聖徒イエス・キリスト教会': 'The Church of Jesus Christ of Latter-day Saints',
    '聖餐': 'sacrament',
    '聖餐会': 'sacrament meeting',
    'モルモン書': 'The Book of Mormon',
    '教義と聖約': 'Doctrine and Covenants',
    '高価なる真珠': 'Pearl of Great Price',
    '末日聖徒': 'Latter-day Saints',
    'イエス・キリスト': 'Jesus Christ',
    '神様': 'God',
    '日本神戸伝道部': 'Japan Kobe Mission',
    '伝道': 'missionary work',
    '伝道部': 'mission',
    'ワード': 'Ward',
    'ニーファイ': 'Nephi',
    'ヤコブ': 'Jacob',
    'エノス': 'Enos',
    'ジェロム': 'Jarom',
    'オムナイ': 'Omni',
    'モルモン': 'Mormon',
    'モーサヤ': 'Mosiah',
    'アルマ': 'Alma',
    'ヘラマン': 'Helaman',
    'エテル': 'Ether',
    'モロナイ': 'Moroni',
    '会員': 'member',
    '教会員': 'church member',
    '会員たち': 'members',
    '純潔の律法': 'law of chastity',
    '伝道部会長': 'mission president',
    '什分の一': 'tithing',
    'ゾーン大会': 'zone conference',
    # Add more terms as needed
}

def count_japanese(text):
    return len(JP_SUBSTRING_PATTERN.findall(text))

def count_ascii(text):
    return len(ASCII_PATTERN.findall(text))

def replace_japanese_with_placeholders(text):
    jp_substrings = JP_SUBSTRING_PATTERN.findall(text)
    placeholder_map = {}
    new_text = text
    for idx, jp in enumerate(jp_substrings):
        placeholder = PLACEHOLDER_TEMPLATE.format(idx)
        new_text = new_text.replace(jp, placeholder, 1)
        placeholder_map[placeholder.lower()] = jp  # store as lowercase
    return new_text, placeholder_map

def restore_placeholders(translated, placeholder_map):
    # Replace all placeholders (case-insensitive) with their original Japanese substrings
    def repl(match):
        key = match.group(0).lower()
        return placeholder_map.get(key, key)
    return PLACEHOLDER_REGEX.sub(repl, translated)

def replace_terms_with_placeholders(text, term_dict):
    term_map = {}
    new_text = text
    idx = 0
    # Sort terms by length (descending) to match longer terms first
    sorted_terms = sorted(term_dict.items(), key=lambda x: len(x[0]), reverse=True)
    for term, translation in sorted_terms:
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        while True:
            match = pattern.search(new_text)
            if not match:
                break
            placeholder = TERM_PLACEHOLDER_TEMPLATE.format(idx)
            new_text = new_text[:match.start()] + placeholder + new_text[match.end():]
            term_map[placeholder] = translation
            idx += 1
    return new_text, term_map

def restore_term_placeholders(translated, term_map):
    def repl(match):
        key = match.group(0).lower()
        return term_map.get(key, key)
    return TERM_PLACEHOLDER_REGEX.sub(repl, translated)

def move_president_after_name_en_to_ja(text):
    # Converts "President Name" (case-insensitive) to "Name会長"
    pattern = re.compile(r'\bPresident ([A-Z][a-zA-Zぁ-んァ-ン一-龥]+)\b', re.IGNORECASE)
    return pattern.sub(r'\1会長', text)

def move_president_before_name_ja_to_en(text):
    # Converts "Name会長" to "President Name"
    pattern = re.compile(r'([A-Zぁ-んァ-ン一-龥][a-zA-Zぁ-んァ-ン一-龥]+)会長')
    return pattern.sub(lambda m: f"President {m.group(1)}", text)

def postprocess_japanese_translation(text):
    # If 'アクセス' appears in a sentence with '友達' (friend) or '会員' (member), replace with '訪問'
    # List of context words that suggest 'visit' means '訪問'
    context_words = ['友達', '会員', 'メンバー', '家族', '兄弟', '姉妹', '教会員']
    for word in context_words:
        # Look for the context word within 10 characters of 'アクセス'
        pattern = re.compile(rf'{word}.{{0,10}}アクセス|アクセス.{{0,10}}{word}')
        if pattern.search(text):
            text = text.replace('アクセス', '訪問')
    return text

@app.route("/")
def health_check():
    return "JKMBot is running!"

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

    # Check for custom commands
    if text.startswith('/'):
        command = text[1:].split()[0].lower()
        if command == 'no':
            # Do not reply at all for /no
            return
        elif command == 'help':
            reply = TextSendMessage(text="This bot translates between English and Japanese, \
                                        and vice versa, for Japan Kobe Mission missionaries and church members.  \
                                        \n\nCommands: \
                                        \n/no - Do not translate \
                                        \n/help - Displays this help message \
                                        ")
            line_bot_api.reply_message(event.reply_token, reply)
            return
        # other commands can be added here
    # Process the text for translation

    jp_count = len(JP_SUBSTRING_PATTERN.findall(text))
    ascii_count = len(ASCII_PATTERN.findall(text))

    try:
        if ascii_count >= jp_count:
            # English dominant
            # 0. Move 'President' after name for Japanese
            text = move_president_after_name_en_to_ja(text)
            # 1. Replace special terms with placeholders
            text_terms, term_map = replace_terms_with_placeholders(text, EN_TO_JA_TERMS)
            # 2. Replace Japanese substrings with placeholders
            text_with_placeholders, placeholder_map = replace_japanese_with_placeholders(text_terms)
            # 3. Translate
            translation = translator.translate(text_with_placeholders, src='en', dest='ja')
            # 4. Restore Japanese substrings
            translated = restore_placeholders(translation.text, placeholder_map)
            # 5. Restore special terms
            translated = restore_term_placeholders(translated, term_map)
            # Post-process for context-sensitive corrections
            translated = postprocess_japanese_translation(translated)
            print(f"Translated text: {translated}")
        else:
            # Japanese dominant
            # 1. Replace special terms with placeholders
            text_terms, term_map = replace_terms_with_placeholders(text, JA_TO_EN_TERMS)
            # 2. Translate
            translation = translator.translate(text_terms, src='ja', dest='en')
            # 3. Restore special terms
            translated = restore_term_placeholders(translation.text, term_map)
            # 4. Move 'President' before name for English
            translated = move_president_before_name_ja_to_en(translated)
            print(f"Translated text: {translated}")
    except Exception as e:
        translated = "Translation error: " + str(e)

    reply = TextSendMessage(text=translated)
    line_bot_api.reply_message(event.reply_token, reply)

