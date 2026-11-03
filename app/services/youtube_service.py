"""Serviço YouTube/yt-dlp com classificação de erros e autenticação opcional local."""
import re
import os
import shutil
from pathlib import Path
from yt_dlp import YoutubeDL

SUPPORTED_FORMATS = {"mp3", "mp4", "wav", "m4a", "webm"}
AUTH_MARKERS = ("sign in to confirm you’re not a bot", "sign in to confirm you're not a bot", "use --cookies-from-browser", "authentication", "http error 403", "403: forbidden")


def sanitize_filename(value):
    """Remove caracteres inválidos no Windows e limita nomes excessivamente longos."""
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", str(value or ""))
    value = re.sub(r'\s+', " ", value).strip().rstrip(". ")
    return (value[:150] or "GrooveCatch_download")


def is_youtube_auth_error(exc):
    """Reconhece somente o bloqueio de autenticação/anti-bot reportado pelo YouTube/yt-dlp."""
    text = str(exc or "").lower()
    return "youtube" in text and any(marker in text for marker in AUTH_MARKERS)


class YouTubeAuthRequired(RuntimeError):
    """Erro semântico usado pela API para não fazer retry cego."""
    code = "youtube_auth_required"

    def __init__(self, technical_detail=""):
        super().__init__("O YouTube solicitou uma sessão autenticada para continuar.")
        self.technical_detail = str(technical_detail or "")


class YouTubeService:
    """Encapsula pesquisa, inspeção e transferência via yt-dlp."""
    def _base_options(self, cookie_browser=None):
        """Monta opções comuns. Cookies só são usados quando o usuário escolhe explicitamente um navegador."""
        options = {"quiet": True, "no_warnings": True, "noplaylist": True, "ignoreerrors": False}
        if cookie_browser and os.environ.get("GROOVECATCH_CLOUD") != "1":
            browser = str(cookie_browser).strip().lower()
            if browser not in {"chrome", "edge", "firefox", "brave", "opera", "vivaldi"}:
                raise ValueError("Navegador não suportado para sessão local.")
            options["cookiesfrombrowser"] = (browser,)
        return options

    def _raise_friendly(self, exc):
        """Converte o bloqueio conhecido em erro tratável e preserva outros erros reais."""
        if is_youtube_auth_error(exc):
            raise YouTubeAuthRequired(str(exc)) from exc
        raise exc

    def get_info(self, url, cookie_browser=None):
        """Lê metadados sem baixar; pode usar sessão local somente após autorização explícita."""
        try:
            with YoutubeDL({**self._base_options(cookie_browser), "skip_download": True}) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as exc:
            self._raise_friendly(exc)
        if not info:
            raise RuntimeError("Não foi possível obter metadados desse link.")
        return {"title": info.get("title") or "Mídia sem título", "url": info.get("webpage_url") or url,
                "duration": info.get("duration"), "channel": info.get("channel") or info.get("uploader") or "Canal desconhecido",
                "thumbnail": info.get("thumbnail")}

    def search(self, query, limit=6, cookie_browser=None):
        """Pesquisa candidatos incluindo thumbnail real retornada pelo YouTube."""
        try:
            with YoutubeDL({**self._base_options(cookie_browser), "extract_flat": True, "skip_download": True}) as ydl:
                result = ydl.extract_info(f"ytsearch{max(1, min(int(limit), 10))}:{query}", download=False)
        except Exception as exc:
            self._raise_friendly(exc)
        candidates = []
        for item in (result or {}).get("entries", []) or []:
            if not item:
                continue
            url = item.get("webpage_url") or item.get("url")
            if url and not str(url).startswith("http"):
                url = f"https://www.youtube.com/watch?v={url}"
            thumbnails = item.get("thumbnails") or []
            thumbnail = item.get("thumbnail") or (thumbnails[-1].get("url") if thumbnails else None)
            if url:
                candidates.append({"title": item.get("title") or "Vídeo sem título", "url": url,
                                   "duration": item.get("duration"), "channel": item.get("channel") or item.get("uploader") or "Canal desconhecido",
                                   "thumbnail": thumbnail})
        return candidates

    def create_preview(self, url, output_dir, cookie_browser=None, seconds=30):
        """Gera uma prévia curta em MP3. Usa download parcial quando o extrator/FFmpeg permitem."""
        import hashlib
        from yt_dlp.utils import download_range_func
        output_dir = Path(output_dir).resolve() / "previews"
        output_dir.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(f"{url}|{cookie_browser or ''}".encode("utf-8")).hexdigest()[:24]
        final = output_dir / f"{key}.mp3"
        if final.is_file() and final.stat().st_size > 0:
            return str(final)
        options = {**self._base_options(cookie_browser),
                   "format": "bestaudio/best",
                   "outtmpl": str(output_dir / f"{key}.%(ext)s"),
                   "download_ranges": download_range_func(None, [(0, max(5, min(int(seconds), 45)))]),
                   "force_keyframes_at_cuts": True,
                   "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "128"}],
                   "overwrites": True}
        try:
            with YoutubeDL(options) as ydl:
                ydl.download([url])
        except Exception as exc:
            self._raise_friendly(exc)
        if final.is_file() and final.stat().st_size > 0:
            return str(final)
        matches = list(output_dir.glob(f"{key}*.mp3"))
        if matches:
            return str(max(matches, key=lambda p: p.stat().st_mtime))
        raise RuntimeError("Não foi possível gerar a pré-visualização desta faixa.")

    def download_media(self, url, title, output_dir, media_format="mp3", progress_hook=None, cookie_browser=None):
        """Baixa mídia e confirma fisicamente o arquivo final."""
        media_format = (media_format or "mp3").lower()
        if media_format not in SUPPORTED_FORMATS:
            raise ValueError(f"Formato não suportado: {media_format}")
        if not shutil.which("ffmpeg"):
            raise RuntimeError("FFmpeg não foi encontrado no PATH. Instale FFmpeg e reinicie o terminal.")
        output_dir = Path(output_dir).resolve(); output_dir.mkdir(parents=True, exist_ok=True)
        safe_title = sanitize_filename(title)
        options = {**self._base_options(cookie_browser), "outtmpl": str(output_dir / f"{safe_title}.%(ext)s"),
                   "progress_hooks": [progress_hook] if progress_hook else [], "windowsfilenames": True,
                   "overwrites": False, "continuedl": True,
                   "format": "bestvideo+bestaudio/best" if media_format == "mp4" else "bestaudio/best"}
        if media_format in {"mp3", "wav", "m4a"}:
            options["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": media_format,
                                           "preferredquality": "192" if media_format == "mp3" else "0"}]
        elif media_format == "mp4":
            options["merge_output_format"] = "mp4"
            options["postprocessors"] = [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}]
        elif media_format == "webm":
            options["format"] = "bestvideo[ext=webm]+bestaudio[ext=webm]/best[ext=webm]/best"
        try:
            with YoutubeDL(options) as ydl:
                ydl.download([url])
        except Exception as exc:
            self._raise_friendly(exc)
        candidates = [p for p in output_dir.glob(f"{safe_title}.*") if p.is_file() and p.stat().st_size > 0
                      and p.suffix.lower() in {".mp3", ".mp4", ".wav", ".m4a", ".webm"}]
        exact = output_dir / f"{safe_title}.{media_format}"
        if exact.is_file() and exact.stat().st_size > 0: return str(exact)
        matches = [p for p in candidates if p.suffix.lower() == f".{media_format}"]
        if matches: return str(max(matches, key=lambda p: p.stat().st_mtime))
        if candidates: raise RuntimeError(f"O download terminou, mas o arquivo final não está no formato {media_format.upper()}.")
        raise RuntimeError("O processo terminou sem gerar um arquivo final válido.")
