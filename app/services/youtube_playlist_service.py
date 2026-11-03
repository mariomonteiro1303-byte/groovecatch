"""Inspeção de playlists YouTube, sem download antecipado dos vídeos."""
from urllib.parse import urlparse, parse_qs
from yt_dlp import YoutubeDL
from app.services.youtube_service import YouTubeAuthRequired, is_youtube_auth_error

MAX_ITEMS = 500

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
    options = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist", "skip_download": True,
               "noplaylist": False, "ignoreerrors": True, "playlistend": MAX_ITEMS + 1,
               "socket_timeout": 20, "retries": 2}
    if cookie_browser:
        browser = str(cookie_browser).lower()
        if browser not in {"chrome", "edge", "firefox", "brave", "opera", "vivaldi"}:
            raise ValueError("Navegador não suportado.")
        options["cookiesfrombrowser"] = (browser,)
    canonical = f"https://www.youtube.com/playlist?list={identifier}"
    try:
        with YoutubeDL(options) as ydl:
            data = ydl.extract_info(canonical, download=False)
    except Exception as exc:
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
