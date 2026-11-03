"""Resolvedor universal de mídia baseado em yt-dlp.

O serviço apenas inspeciona/baixa URLs que o yt-dlp consegue processar. Ele não
implementa contorno de DRM, paywall ou autenticação. Sites podem mudar sem aviso.
"""
from urllib.parse import urlparse
from yt_dlp import YoutubeDL
from app.services.youtube_service import YouTubeAuthRequired, is_youtube_auth_error

AUDIO_FORMATS = {"mp3", "m4a", "wav"}
VIDEO_FORMATS = {"mp4", "webm"}
SUPPORTED_FORMATS = AUDIO_FORMATS | VIDEO_FORMATS

PLATFORM_HOSTS = {
    "youtube.com": "YouTube", "youtu.be": "YouTube", "music.youtube.com": "YouTube",
    "instagram.com": "Instagram", "tiktok.com": "TikTok", "vm.tiktok.com": "TikTok",
    "facebook.com": "Facebook", "fb.watch": "Facebook", "x.com": "X / Twitter",
    "twitter.com": "X / Twitter", "soundcloud.com": "SoundCloud", "vimeo.com": "Vimeo",
    "twitch.tv": "Twitch",
}


def detect_platform(url):
    """Retorna um nome amigável para a plataforma sem limitar o extrator genérico."""
    host = (urlparse(url).netloc or "").lower().removeprefix("www.")
    for domain, label in PLATFORM_HOSTS.items():
        if host == domain or host.endswith("." + domain):
            return label
    return host or "Site"


class MediaService:
    """Inspeciona URLs públicas e apresenta somente opções coerentes com a mídia."""

    def _options(self, cookie_browser=None):
        options = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "ignoreerrors": False,
            "skip_download": True,
        }
        if cookie_browser:
            browser = str(cookie_browser).strip().lower()
            if browser not in {"chrome", "edge", "firefox", "brave", "opera", "vivaldi"}:
                raise ValueError("Navegador não suportado para sessão local.")
            options["cookiesfrombrowser"] = (browser,)
        return options

    def inspect(self, url, cookie_browser=None):
        """Obtém metadados e detecta se há streams de áudio e/ou vídeo."""
        try:
            with YoutubeDL(self._options(cookie_browser)) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as exc:
            if is_youtube_auth_error(exc):
                raise YouTubeAuthRequired(str(exc)) from exc
            raise
        if not info:
            raise RuntimeError("Não foi possível identificar mídia utilizável nesse endereço.")

        # Alguns extratores retornam uma coleção mesmo com noplaylist. Para a tela de
        # inspeção usamos o primeiro item real e deixamos playlists para versão futura.
        if info.get("entries"):
            entries = [entry for entry in info.get("entries") or [] if entry]
            if not entries:
                raise RuntimeError("A URL foi reconhecida, mas não contém itens acessíveis.")
            info = entries[0]

        formats = info.get("formats") or []
        has_audio = any(f.get("acodec") not in {None, "none"} for f in formats) or bool(info.get("acodec"))
        has_video = any(f.get("vcodec") not in {None, "none"} for f in formats) or bool(info.get("vcodec"))

        # Em extratores simples, formats pode vir incompleto. Se o item é um vídeo,
        # yt-dlp normalmente informa width/height ou ext de vídeo.
        if info.get("width") or info.get("height") or info.get("ext") in {"mp4", "webm", "mkv", "mov"}:
            has_video = True
        if has_video and not has_audio:
            # O download de vídeo ainda pode possuir áudio muxado em um formato único.
            has_audio = any(f.get("acodec") not in {None, "none"} for f in formats)

        choices = []
        if has_audio:
            choices.extend([
                {"value": "mp3", "label": "MP3 · Áudio", "kind": "audio"},
                {"value": "m4a", "label": "M4A · Áudio", "kind": "audio"},
                {"value": "wav", "label": "WAV · Áudio sem compressão", "kind": "audio"},
            ])
        if has_video:
            choices.extend([
                {"value": "mp4", "label": "MP4 · Vídeo", "kind": "video"},
                {"value": "webm", "label": "WebM · Vídeo", "kind": "video"},
            ])
        if not choices:
            raise RuntimeError("A página foi reconhecida, mas não encontrei streams de áudio ou vídeo disponíveis.")

        return {
            "title": info.get("title") or "Mídia sem título",
            "url": info.get("webpage_url") or url,
            "duration": info.get("duration"),
            "channel": info.get("channel") or info.get("uploader") or info.get("creator") or "Autor não informado",
            "thumbnail": info.get("thumbnail"),
            "platform": detect_platform(url),
            "extractor": info.get("extractor_key") or info.get("extractor"),
            "has_audio": has_audio,
            "has_video": has_video,
            "formats": choices,
        }
