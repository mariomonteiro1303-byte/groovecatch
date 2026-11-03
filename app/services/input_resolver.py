"""Classifica Spotify, URLs de mídia genéricas e pesquisas textuais."""
from urllib.parse import urlparse
from app.services.spotify_service import SpotifyService
from app.services.media_service import MediaService
from app.services.youtube_service import YouTubeService
from app.services.match_service import MatchService
from app.services.youtube_playlist_service import playlist_id, load_playlist


class InputResolver:
    """Um único ponto de entrada para todas as fontes suportadas pelo GrooveCatch."""

    def resolve(self, value, storage_dir, cookie_browser=None):
        value = (value or "").strip()
        if not value:
            raise ValueError("Cole um link ou digite o nome da música.")

        parsed = urlparse(value)
        host = (parsed.netloc or "").lower().removeprefix("www.")
        if host in {"open.spotify.com", "spotify.link"}:
            spotify = SpotifyService().load(value)
            tracks = spotify["tracks"]
            # Faixa individual mantém a experiência validada. Coleções NÃO fazem 51 buscas no YouTube aqui.
            if spotify["item_type"] == "track":
                matcher = MatchService(storage_dir)
                tracks[0]["candidates"] = matcher.candidates(tracks[0], limit=1, cookie_browser=cookie_browser)
            return {"kind": "spotify", "tracks": tracks, "count": len(tracks), "credentials_required": False,
                    "item_type": spotify["item_type"], "collection_title": spotify.get("title") or "Coleção Spotify",
                    "collection_thumbnail": spotify.get("thumbnail") or "", "lazy_matching": spotify["item_type"] != "track"}

        # Links com v= e list= representam uma playlist. O usuário poderá optar pelo vídeo isolado.
        if playlist_id(value):
            return load_playlist(value, cookie_browser=cookie_browser)

        # Qualquer URL HTTP(S) passa pelo yt-dlp. Isso evita manter regras frágeis por rede.
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            media = MediaService().inspect(value, cookie_browser=cookie_browser)
            return {"kind": "media_url", "media": media, "message": f"{media['platform']} identificado."}

        return {"kind": "search", "query": value, "candidates": YouTubeService().search(value, cookie_browser=cookie_browser)}
