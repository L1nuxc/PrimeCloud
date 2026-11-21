"""Resolve a Deezer recording to a matching full stream."""
import json
import os
import re
from html.parser import HTMLParser
from urllib.parse import urlencode, urljoin, urlsplit
from urllib.request import Request, urlopen

HITMO = "https://ru.hitmoz.org"
def normalize(value):
    return " ".join(re.findall(r"\w+", value.casefold().replace("ё","е")))

class HitmoSearch(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.current = None
        self.field = None
    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "data-musmeta" in attrs:
            try: meta=json.loads(attrs["data-musmeta"])
            except (TypeError, ValueError): meta={}
            if not isinstance(meta,dict): meta={}
            self.current = {k:str(meta.get(k) or "") for k in ("artist","title","url")}
            self.rows.append(self.current)
        if self.current is None: return
        classes=attrs.get("class","").split()
        if "track__download-btn" in classes:
            self.current["url"]=attrs.get("href","")
        for css, field in (("track__title","title"),("track__desc","artist"),("track__fulltime","time")):
            if css in classes:
                self.field=field
                self.current[field]=""
    def handle_data(self, data):
        if self.current is not None and self.field:
            self.current[self.field]+=data
    def handle_endtag(self, tag):
        if tag=="li": self.current=None
        self.field=None

def hitmo(track):
    query=track["artist"]["name"]+" "+track["title"]
    req=Request(HITMO+"/search?"+urlencode({"q":query}),headers={"User-Agent":"PrimeCloud/0.1"})
    with urlopen(req,timeout=6) as resp:
        parser=HitmoSearch()
        parser.feed(resp.read(2_000_000).decode("utf-8","replace"))
        origin=resp.url
    for row in parser.rows:
        if normalize(row["artist"])!=normalize(track["artist"]["name"]): continue
        if normalize(row["title"])!=normalize(track["title"]): continue
        timing=row.get("time","").strip()
        if re.fullmatch(r"\d+:\d{2}",timing):
            minutes,seconds=map(int,timing.split(":"))
            if abs(60*minutes+seconds-track["duration"])>4: continue
        url=urljoin(origin,row["url"])
        parts=urlsplit(url)
        if parts.scheme=="https" and parts.hostname==urlsplit(origin).hostname and parts.path.startswith("/get/music/"):
            return {"source":"Hitmo · версия по данным источника","url":url}

def soundcloud(track):
    token=os.environ.get("SOUNDCLOUD_ACCESS_TOKEN")
    if not token: return
    def request(path):
        req=Request("https://api.soundcloud.com"+path,headers={"Authorization":"OAuth "+token})
        with urlopen(req,timeout=6) as response: return json.load(response)
    query=urlencode({"q":track["artist"]["name"]+" "+track["title"],"access":"playable","limit":10,"linked_partitioning":1})
    result=request("/tracks?"+query)
    for row in result["collection"] if isinstance(result,dict) else result:
        metadata=row.get("publisher_metadata") or {}
        if row.get("access")!="playable" or abs(row.get("duration",0)/1000-track["duration"])>4: continue
        if normalize(row["title"])!=normalize(track["title"]): continue
        if normalize(metadata.get("artist") or row["user"]["username"])!=normalize(track["artist"]["name"]): continue
        streams=request("/tracks/"+str(row["id"])+"/streams")
        for key in ("hls_aac_160_url","http_mp3_128_url","hls_mp3_128_url"):
            stream=streams.get(key)
            if stream and stream.startswith("https://"):
                return {"source":"SoundCloud · "+row["user"]["username"],"url":stream,"permalink":row["permalink_url"]}

def resolve(track):
    from urllib.error import URLError
    for provider in (hitmo,soundcloud):
        try:
            result=provider(track)
            if result: return result
        except (OSError,URLError,ValueError,KeyError):
            continue
