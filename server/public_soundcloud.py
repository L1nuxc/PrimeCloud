"""Find the public SoundCloud recording corresponding to a catalog track."""
import re
from threading import BoundedSemaphore
from urllib.parse import urlsplit

slots = BoundedSemaphore(2)

def words(text):
    return " ".join(re.findall(r"\w+", (text or "").casefold().replace("ё", "е")))

def matches(track, row):
    seconds = row.get("duration")
    if not seconds or not track.get("duration") or abs(seconds - track["duration"]) > 4:
        return False
    artist = words(track["artist"]["name"])
    if artist not in (words(row.get("artist")), words(row.get("uploader"))):
        return False
    title = words(track["title"])
    names = {words(row.get("title")), words(row.get("track"))}
    return title in names or (artist + " " + title) in names

def full_audio(info):
    if info.get("availability") in ("private", "premium_only", "subscriber_only", "needs_auth"):
        return None
    for audio in reversed(info.get("formats") or []):
        url = audio.get("url", "")
        parts = urlsplit(url)
        host = parts.hostname or ""
        if parts.scheme != "https" or not (host.endswith(".sndcdn.com") or host == "playback.media-streaming.soundcloud.cloud"):
            continue
        if "preview" in audio.get("format_id", "").lower() or "/preview/" in parts.path:
            continue
        if audio.get("has_drm") or audio.get("protocol") not in ("https", "m3u8", "m3u8_native"):
            continue
        return url

def find(track):
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError
    if not slots.acquire(timeout=1):
        raise TimeoutError("SoundCloud busy")
    try:
        opts = {"quiet": True, "no_warnings": True, "cachedir": False, "socket_timeout": 5,
                "retries": 0, "extractor_retries": 0, "extract_flat": "in_playlist",
                "playlistend": 5, "skip_download": True}
        with YoutubeDL(opts) as client:
            query = track["artist"]["name"] + " " + track["title"]
            result = client.extract_info("scsearch5:" + query, download=False)
            for row in (result or {}).get("entries", []):
                if not row or not matches(track, row):
                    continue
                page = row.get("webpage_url") or row.get("url") or ""
                if not page.startswith("https://soundcloud.com/"):
                    continue
                info = client.extract_info(page, download=False)
                if not info or not matches(track, info):
                    continue
                url = full_audio(info)
                if url:
                    return {"source": "SoundCloud · " + (info.get("uploader") or track["artist"]["name"]),
                            "permalink": page, "url": url}
    except DownloadError as err:
        raise OSError("SoundCloud unavailable") from err
    finally:
        slots.release()
