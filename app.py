import os
import time
from datetime import datetime, timedelta

from flask import Flask, request, jsonify
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

# ====== ENV ======
API_ID = int(os.environ["API_ID"])            # my.telegram.org → api_id
API_HASH = os.environ["API_HASH"]             # my.telegram.org → api_hash
SESSION_STRING = os.environ.get("SESSION_STRING", "")  # ilk kurulumda boş olacak
PHONE_NUMBER = os.environ.get("PHONE_NUMBER", "")      # +90... biçiminde
AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "")  # login endpoint'i korumak için gizli anahtar
REPLY_TEXT = os.environ.get("REPLY_TEXT", "Merhaba! Şu anda meşgulüm ama mesajını aldım 😊")
ONCE_PER_HOURS = int(os.environ.get("ONCE_PER_HOURS", "24"))

# ====== GLOBAL ======
app = Flask(__name__)
client = None
last_reply_at = {}  # {user_id: datetime}

def build_client():
    global client
    if SESSION_STRING:
        client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    else:
        # İlk kurulum: boş session (StringSession üretilecek)
        client = TelegramClient(StringSession(), API_ID, API_HASH)
    return client

client = build_client()

# ====== TELETHON HANDLER ======
@client.on(events.NewMessage(incoming=True))
async def auto_reply(event):
    # yalnızca private (özel) sohbetlerde yanıtla
    if event.is_private and not (await event.get_sender()).bot:
        uid = event.sender_id
        now = datetime.utcnow()
        last = last_reply_at.get(uid)
        if not last or now - last >= timedelta(hours=ONCE_PER_HOURS):
            await event.respond(REPLY_TEXT)
            last_reply_at[uid] = now

# ====== LOGIN FLOW (BİR KEREYE MAHSUS) ======
# 1) /start_login?token=XXXX  → Telefona kod göndertir
@app.get("/start_login")
def start_login():
    if AUTH_TOKEN and request.args.get("token") != AUTH_TOKEN:
        return "unauthorized", 401
    if not PHONE_NUMBER:
        return "PHONE_NUMBER env yok. +90 ile başlatın.", 400

    async def _send_code():
        await client.connect()
        if await client.is_user_authorized():
            return "already_authorized"
        await client.send_code_request(PHONE_NUMBER)
        return "code_sent"

    import asyncio
    result = asyncio.get_event_loop().run_until_complete(_send_code())
    return result, 200

# 2) /submit_code?token=XXXX&code=12345[&password=twofactor]
#   → Kodu girersin, başarıyla giriş olursa StringSession döner (kopyalayıp Heroku'ya koyacaksın)
@app.get("/submit_code")
def submit_code():
    if AUTH_TOKEN and request.args.get("token") != AUTH_TOKEN:
        return "unauthorized", 401
    code = request.args.get("code", "")
    pwd = request.args.get("password")  # 2FA varsa

    if not code:
        return "code parametresi gerekli", 400

    async def _sign_in():
        await client.connect()
        try:
            me = await client.sign_in(PHONE_NUMBER, code)
        except SessionPasswordNeededError:
            if not pwd:
                return {"error": "PASSWORD_REQUIRED"}
            me = await client.sign_in(password=pwd)

        # başarılı olursa session string üret
        s = client.session.save()
        return {"session_string": s}

    import asyncio
    data = asyncio.get_event_loop().run_until_complete(_sign_in())
    return jsonify(data), 200

# Healthcheck / keep-alive
@app.get("/")
def index():
    return "OK", 200

def start_telethon():
    import asyncio
    loop = asyncio.get_event_loop()
    loop.create_task(client.start())
    # Telethon'u arkaplanda çalıştır
    # (Flask zaten web isteklerini karşılayacak)
    return

if __name__ == "__main__":
    # Telethon'u başlat
    start_telethon()
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
