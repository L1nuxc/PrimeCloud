"""PrimeCloud API. Run behind the HTTPS proxy on the loopback interface."""
import hashlib
import hmac
import html
import json
import os
import secrets
import sqlite3
import threading
import time
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, parse_qs
from urllib.request import urlopen, Request
from sources import resolve

ORIGIN = "https://primecloud.pigboss.xyz"
BOT = "PrimeCloud_robot"
DB = os.environ.get("PC_DATABASE", "/var/lib/primecloud/music.sqlite")
TOKEN = os.environ.get("TG_TOKEN", "")
def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def init():
    with closing(sqlite3.connect(DB)) as db:
        db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS challenges(link TEXT PRIMARY KEY, poll TEXT UNIQUE, expires INTEGER, uid INTEGER);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, uid INTEGER, expires INTEGER);
        CREATE TABLE IF NOT EXISTS users(uid INTEGER PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS assertions(hash TEXT PRIMARY KEY, expires INTEGER);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, val INTEGER);
        """)

def utc():
    return int(time.time())

def challenge(db):
    link, poll = secrets.token_urlsafe(24), secrets.token_urlsafe(32)
    db.execute("DELETE FROM challenges WHERE expires<=?", (utc(),))
    db.execute("DELETE FROM sessions WHERE expires<=?", (utc(),))
    db.execute("DELETE FROM assertions WHERE expires<=?", (utc(),))
    db.execute("INSERT INTO challenges VALUES(?,?,?,NULL)", (digest(link), digest(poll), utc()+300))
    return {"poll":poll, "bot":"https://t.me/"+BOT+"?start="+link, "widget":ORIGIN+"/login/"+link}

def confirm(db, link, uid):
    return db.execute("UPDATE challenges SET uid=? WHERE link=? AND uid IS NULL AND expires>?", (uid,digest(link),utc())).rowcount == 1

def exchange(db, poll):
    row = db.execute("DELETE FROM challenges WHERE poll=? AND uid IS NOT NULL AND expires>? RETURNING uid", (digest(poll),utc())).fetchone()
    if row:
        token = secrets.token_urlsafe(32)
        db.execute("INSERT OR IGNORE INTO users VALUES(?)", row)
        db.execute("INSERT INTO sessions VALUES(?,?,?)", (digest(token),row[0],utc()+30*86400))
        return 200, {"token":token}
    pending = db.execute("SELECT 1 FROM challenges WHERE poll=? AND expires>?", (digest(poll),utc())).fetchone()
    return (202, {"pending":True}) if pending else (410, {"error":"Запрос входа истёк"})

def valid_widget(fields):
    if not TOKEN or not fields.get("id","").isascii() or not fields["id"].isdigit(): return False
    timestamp = fields.get("auth_date","")
    if not timestamp.isdigit() or not 0 <= utc()-int(timestamp) <= 300: return False
    message = "\n".join(k+"="+v for k,v in sorted(fields.items()) if k!="hash")
    signature = hmac.new(hashlib.sha256(TOKEN.encode()).digest(), message.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, fields.get("hash",""))

def fetch(url, timeout=10):
    with urlopen(Request(url, headers={"User-Agent":"PrimeCloud/0.1"}), timeout=timeout) as response:
        return json.load(response)

def bot_worker():
    while True:
        try:
            with closing(sqlite3.connect(DB)) as db, db:
                offset = db.execute("SELECT val FROM settings WHERE key='offset'").fetchone()
                params = urlencode({"offset":offset[0] if offset else 0,"timeout":25,"allowed_updates":'["message"]'})
                updates = fetch("https://api.telegram.org/bot"+TOKEN+"/getUpdates?"+params, 35)
                for event in updates["result"]:
                    message = event.get("message",{})
                    sender = message.get("from",{})
                    command = message.get("text","").split()
                    if (message.get("chat",{}).get("type")=="private" and len(command)==2
                        and command[0] in ("/start","/start@"+BOT) and sender.get("id")):
                        confirm(db, command[1], sender["id"])
                    db.execute("INSERT OR REPLACE INTO settings VALUES('offset',?)",(event["update_id"]+1,))
        except Exception as err:
            print("Telegram polling", type(err).__name__, getattr(err,"code",""), flush=True)
            time.sleep(5)

def catalog(path, query):
    kind = query.get("type","track")
    if path == "/api/search" and kind in ("track","album","artist") and query.get("q","").strip():
        url = "/search/"+kind+"?"+urlencode({"q":query["q"][:160],"limit":32})
    elif path in ("/api/album","/api/artist") and query.get("id","").isascii() and query["id"].isdigit():
        kind = "track" if path == "/api/album" else "album"
        url = path[4:]+"/"+query["id"]+("/tracks" if kind=="track" else "/albums")+"?limit=100"
    else: return 400, {"error":"Некорректный запрос каталога"}
    data = fetch("https://api.deezer.com"+url)
    if "error" in data: return 502, {"error":"Каталог Deezer временно недоступен"}
    items = [{"type":kind, "id":x["id"],"title":x.get("title") or x.get("name"),"artist":x.get("artist",{}).get("name",""),
              "explicit":x.get("explicit_lyrics",False),"duration":x.get("duration",0),
              "preview":x.get("preview","")} for x in data["data"]]
    return 200, {"items":items}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass  # Requests may include Telegram assertions.
    def reply(self, status, value, page=False):
        body = value.encode() if page else json.dumps(value,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", ("text/html" if page else "application/json")+"; charset=utf-8")
        self.send_header("Content-Length",str(len(body)))
        self.send_header("Cache-Control","no-store")
        self.send_header("Referrer-Policy","no-referrer")
        self.end_headers()
        self.wfile.write(body)
    def handle_api(self):
        parts = urlsplit(self.path)
        path = parts.path
        q = {k:v[0] for k,v in parse_qs(parts.query,max_num_fields=16).items()}
        with closing(sqlite3.connect(DB)) as db, db:
            if self.command=="POST":
                if path=="/auth/start":
                    if not TOKEN: return 503, {"error":"Вход временно недоступен"}
                    return 200, challenge(db)
                if path=="/auth/poll":
                    return exchange(db,self.headers.get("Authorization","").removeprefix("Bearer "))
                return 404, {}
            if path=="/health": return 200, {"service":"PrimeCloud","status":"ok"}
            if path.startswith("/login/") or path.startswith("/confirm/"):
                link = path.split("/")[-1]
                if not db.execute("SELECT 1 FROM challenges WHERE link=? AND expires>? AND uid IS NULL",(digest(link),utc())).fetchone():
                    return 410, {"error":"Откройте новый запрос входа в PrimeCloud"}
                if path.startswith("/login/"):
                    return 200, ('<!doctype html><meta charset=utf-8><title>PrimeCloud</title><h1>Вход в PrimeCloud</h1>'
                        '<script async src="https://telegram.org/js/telegram-widget.js?22" data-size="large" data-telegram-login="'+BOT+
                        '" data-auth-url="'+ORIGIN+'/confirm/'+html.escape(link,quote=True)+'"></script>'), True
                if not valid_widget(q): return 403, {}
                if not db.execute("INSERT OR IGNORE INTO assertions VALUES(?,?)",(q["hash"],utc()+310)).rowcount: return 409, {}
                if not confirm(db,link,int(q["id"])): return 410, {}
                return 200, '<meta charset=utf-8><title>PrimeCloud</title><p>Вход подтверждён. Вернитесь в плеер.</p>', True
            if not db.execute("SELECT uid FROM sessions WHERE token=? AND expires>?",(digest(self.headers.get("Authorization","").removeprefix("Bearer ")),utc())).fetchone():
                return 401, {"error":"Войдите через Telegram"}
            if path=="/api/me": return 200, {"signed_in":True}
            if path=="/api/listen" and q.get("id","").isascii() and q["id"].isdigit():
                track = fetch("https://api.deezer.com/track/"+q["id"])
                if "error" in track: return 404, {"error":"Трек отсутствует в каталоге"}
                audio = resolve(track)
                return (200, audio) if audio else (404, {"error":"Полная запись недоступна. Можно выбрать фрагмент Deezer."})
            if path in ("/api/search","/api/artist","/api/album"): return catalog(path,q)
            return 404, {}
    def do_GET(self):
        try: result = self.handle_api()
        except (TimeoutError,HTTPError,URLError): result = (502, {"error":"Источник временно недоступен"})
        except (ValueError,KeyError): result = (400, {"error":"Некорректный запрос"})
        self.reply(*result)
    do_POST = do_GET

if __name__=="__main__":
    init()
    if TOKEN: threading.Thread(target=bot_worker,daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1",8791),Handler).serve_forever()
