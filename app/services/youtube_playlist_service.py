"""Inspeção de playlists YouTube, sem download antecipado dos vídeos."""
from urllib.parse import urlparse, parse_qs
from app.services.youtube_policy import (
    YtDlpLogger, check_youtube_cooldown, map_youtube_error,
)
from yt_dlp import YoutubeDL
from app.services.youtube_service import YouTubeAuthRequired, is_youtube_auth_error

MAX_ITEMS = 500


def youtube_video_id(url):
    """Extrai ID validado de URL de vídeo, mesmo quando contém &list=.

    Links /playlist?list=... não são vídeos. Não aceita domínios semelhantes.
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"}:
        return None
    if host not in {"youtu.be", "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
        return None
    parts = parsed.path.strip("/").split("/")
    if host == "youtu.be":
        identifier = parts[0] if len(parts) == 1 else ""
    elif parts[0] == "watch":
        identifier = parse_qs(parsed.query).get("v", [""])[0]
    elif len(parts) == 2 and parts[0] in {"shorts", "live", "embed"}:
        identifier = parts[1]
    else:
        identifier = ""
    if len(identifier) == 11 and all(char.isalnum() or char in "_-" for char in identifier):
        return identifier
    return None


def playlist_id(url):
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}:
        return None
    identifier = parse_qs(parsed.query).get("list", [None])[0]
    return identifier if identifier and len(identifier) <= 150 and identifier.replace("-", "").replace("_", "").isalnum() else None

def load_playlist(url, cookie_browser=None):
    identifier = playlist_id(url)
    if not identifier:
        raise ValueError("Link de playlist do YouTube inválido.")
    if identifier.upper().startswith("RD"):
        raise ValueError("Mix automático do YouTube não está disponível como playlist. Cole o link de um vídeo individual.")
    canonical = f"https://www.youtube.com/playlist?list={identifier}"
    check_youtube_cooldown(canonical)
    logger = YtDlpLogger()
    options = {"quiet": True, "no_warnings": False, "extract_flat": "in_playlist", "skip_download": True,
               "noplaylist": False, "ignoreerrors": True, "playlistend": MAX_ITEMS + 1,
               "socket_timeout": 20, "retries": 0, "extractor_retries": 0,
               "js_runtimes": {"deno": {}}, "logger": logger}
    if cookie_browser:
        import os
        if os.environ.get("GROOVECATCH_CLOUD") == "1":
            raise ValueError("Cookies de navegador local não estão disponíveis na nuvem.")
        browser = str(cookie_browser).lower()
        if browser not in {"chrome", "edge", "firefox", "brave", "opera", "vivaldi"}:
            raise ValueError("Navegador não suportado.")
        options["cookiesfrombrowser"] = (browser,)
    try:
        with YoutubeDL(options) as ydl:
            data = ydl.extract_info(canonical, download=False)
    except Exception as exc:
        mapped = map_youtube_error(exc, logger, canonical)
        if mapped:
            raise mapped from exc
        if is_youtube_auth_error(exc):
            raise YouTubeAuthRequired(str(exc)) from exc
        raise
    if not data or not data.get("entries"):
        raise ValueError("Playlist vazia, privada ou indisponível.")
    entries = list(data.get("entries") or [])
    if len(entries) > MAX_ITEMS:
        raise ValueError(f"A playlist excede o limite de {MAX_ITEMS} vídeos.")
    items = []
    for index, entry in enumerate(entries, 1):
        if not entry:
            continue
        vid = entry.get("id")
        if not vid or not isinstance(vid, str) or len(vid) != 11:
            continue
        thumbnails = entry.get("thumbnails") or []
        items.append({"title": entry.get("title") or "Vídeo sem título", "url": f"https://www.youtube.com/watch?v={vid}",
                      "duration": entry.get("duration"), "channel": entry.get("channel") or entry.get("uploader") or "",
                      "thumbnail": entry.get("thumbnail") or (thumbnails[-1].get("url") if thumbnails else ""),
                      "position": index})
    if not items:
        raise ValueError("Não há vídeos públicos disponíveis nessa playlist.")
    return {"kind": "youtube_playlist", "collection_title": data.get("title") or "Playlist YouTube",
            "count": len(items), "tracks": items, "playlist_url": canonical,
            "truncated": len(entries) == MAX_ITEMS}
