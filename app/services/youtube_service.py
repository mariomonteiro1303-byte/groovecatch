
"""Serviço YouTube/yt-dlp com classificação de erros
e autenticação opcional local."""

import re
import os
import shutil
import hashlib
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import download_range_func

from app.services.youtube_policy import (
    YtDlpLogger,
    is_youtube_target,
    check_youtube_cooldown,
    map_youtube_error,
)


# Formatos de mídia suportados pelo GrooveCatch.
SUPPORTED_FORMATS = {"mp3", "mp4", "wav", "m4a", "webm"}


# Mensagens que indicam solicitação de autenticação.
AUTH_MARKERS = (
    "sign in to confirm you’re not a bot",
    "sign in to confirm you're not a bot",
    "use --cookies-from-browser",
    "authentication",
)


def sanitize_filename(value):
    """
    Remove caracteres inválidos em nomes de arquivos
    no Windows e limita nomes excessivamente longos.
    """
    value = re.sub(
        r'[<>:"/\\|?*\x00-\x1f]',
        "",
        str(value or ""),
    )

    value = re.sub(r"\s+", " ", value).strip().rstrip(". ")

    return value[:150] or "GrooveCatch_download"


def is_youtube_auth_error(exc):
    """
    Reconhece mensagens de autenticação reportadas
    pelo YouTube ou pelo yt-dlp.
    """
    text = str(exc or "").lower()

    return (
        "youtube" in text
        and any(marker in text for marker in AUTH_MARKERS)
    )


class YouTubeAuthRequired(RuntimeError):
    """
    Erro específico de autenticação utilizado pela API.
    """

    code = "youtube_auth_required"

    def __init__(self, technical_detail=""):
        super().__init__(
            "O YouTube solicitou uma sessão autenticada "
            "para continuar."
        )

        self.technical_detail = str(technical_detail or "")


class YouTubeService:
    """
    Encapsula pesquisa, identificação, pré-visualização
    e transferência de mídias utilizando yt-dlp.
    """

    def _base_options(self, cookie_browser=None, target=None):
        """
        Centraliza as configurações utilizadas pelo yt-dlp.

        O parâmetro target identifica a plataforma de origem,
        evitando que limitações de outros serviços acionem
        indevidamente a pausa temporária do YouTube.
        """

        options = {
            "quiet": True,
            "no_warnings": False,
            "noplaylist": True,
            "ignoreerrors": False,

            # Runtime JavaScript.
            "js_runtimes": {
                "deno": {}
            },

            # Logger específico para a plataforma consultada.
            "logger": YtDlpLogger(
                for_youtube=is_youtube_target(target)
            ),

            # Evita repetições automáticas do extrator.
            "extractor_retries": 0,
        }

        # Cookies de navegador são permitidos somente
        # em instalações locais, quando escolhidos pelo usuário.
        if (
            cookie_browser
            and os.environ.get("GROOVECATCH_CLOUD") != "1"
        ):
            browser = str(cookie_browser).strip().lower()

            supported_browsers = {
                "chrome",
                "edge",
                "firefox",
                "brave",
                "opera",
                "vivaldi",
            }

            if browser not in supported_browsers:
                raise ValueError(
                    "Navegador não suportado para sessão local."
                )

            options["cookiesfrombrowser"] = (browser,)

        return options

    def _raise_friendly(self, exc, target, logger):
        """
        Classifica erros externos antes do tratamento
        de autenticação.

        Permite distinguir erros HTTP 403, HTTP 429
        e falhas de extração.
        """

        mapped = map_youtube_error(exc, logger, target)

        if mapped:
            raise mapped from exc

        if is_youtube_auth_error(exc):
            raise YouTubeAuthRequired(str(exc)) from exc

        raise exc

    def get_info(self, url, cookie_browser=None):
        """
        Obtém os metadados de uma mídia sem iniciar
        seu download.
        """

        # Verifica se existe uma pausa ativa do YouTube.
        check_youtube_cooldown(url)

        options = {
            **self._base_options(
                cookie_browser,
                target=url,
            ),
            "skip_download": True,
        }

        try:
            with YoutubeDL(options) as ydl:
                info = ydl.extract_info(
                    url,
                    download=False,
                )

        except Exception as exc:
            self._raise_friendly(
                exc,
                url,
                options["logger"],
            )

        if not info:
            raise RuntimeError(
                "Não foi possível obter metadados desse link."
            )

        return {
            "title": info.get("title") or "Mídia sem título",
            "url": info.get("webpage_url") or url,
            "duration": info.get("duration"),
            "channel": (
                info.get("channel")
                or info.get("uploader")
                or "Canal desconhecido"
            ),
            "thumbnail": info.get("thumbnail"),
        }

    def search(self, query, limit=6, cookie_browser=None):
        """
        Pesquisa vídeos e retorna candidatos com título,
        endereço, duração, canal e miniatura.
        """

        # Monta a consulta utilizando o mecanismo
        # de pesquisa do yt-dlp.
        target = f"ytsearch{max(1, min(int(limit), 10))}:{query}"

        check_youtube_cooldown(target)

        options = {
            **self._base_options(
                cookie_browser,
                target=target,
            ),
            "extract_flat": True,
            "skip_download": True,
        }

        try:
            with YoutubeDL(options) as ydl:
                result = ydl.extract_info(
                    target,
                    download=False,
                )

        except Exception as exc:
            self._raise_friendly(
                exc,
                target,
                options["logger"],
            )

        candidates = []

        for item in (result or {}).get("entries", []) or []:

            if not item:
                continue

            url = item.get("webpage_url") or item.get("url")

            # Alguns resultados retornam somente o ID do vídeo.
            # Nesse caso, monta uma URL válida do YouTube.
            if url and not str(url).startswith("http"):
                url = f"https://www.youtube.com/watch?v={url}"

            thumbnails = item.get("thumbnails") or []

            thumbnail = item.get("thumbnail") or (
                thumbnails[-1].get("url")
                if thumbnails
                else None
            )

            if url:
                candidates.append({
                    "title": (
                        item.get("title")
                        or "Vídeo sem título"
                    ),
                    "url": url,
                    "duration": item.get("duration"),
                    "channel": (
                        item.get("channel")
                        or item.get("uploader")
                        or "Canal desconhecido"
                    ),
                    "thumbnail": thumbnail,
                })

        return candidates

    def create_preview(
        self,
        url,
        output_dir,
        cookie_browser=None,
        seconds=30,
    ):
        """
        Gera uma prévia curta em MP3 utilizando FFmpeg.

        Reutiliza uma prévia existente quando disponível.
        """

        output_dir = Path(output_dir).resolve() / "previews"

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        # Identificador da prévia para evitar downloads
        # repetidos do mesmo conteúdo.
        key = hashlib.sha256(
            f"{url}|{cookie_browser or ''}".encode("utf-8")
        ).hexdigest()[:24]

        final = output_dir / f"{key}.mp3"

        if final.is_file() and final.stat().st_size > 0:
            return str(final)

        check_youtube_cooldown(url)

        options = {
            **self._base_options(
                cookie_browser,
                target=url,
            ),

            "format": "bestaudio/best",

            "outtmpl": str(
                output_dir / f"{key}.%(ext)s"
            ),

            # Limita a duração da prévia entre 5 e 45 segundos.
            "download_ranges": download_range_func(
                None,
                [(0, max(5, min(int(seconds), 45)))],
            ),

            "force_keyframes_at_cuts": True,

            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "128",
                }
            ],

            "overwrites": True,
        }

        try:
            with YoutubeDL(options) as ydl:
                ydl.download([url])

        except Exception as exc:
            self._raise_friendly(
                exc,
                url,
                options["logger"],
            )

        # Confirma se o arquivo esperado foi criado.
        if final.is_file() and final.stat().st_size > 0:
            return str(final)

        # Procura possíveis arquivos com nomes alternativos.
        matches = [
            path
            for path in output_dir.glob(f"{key}*.mp3")
            if path.is_file() and path.stat().st_size > 0
        ]

        if matches:
            return str(
                max(matches, key=lambda p: p.stat().st_mtime)
            )

        raise RuntimeError(
            "Não foi possível gerar a pré-visualização desta faixa."
        )

    def download_media(
        self,
        url,
        title,
        output_dir,
        media_format="mp3",
        progress_hook=None,
        cookie_browser=None,
    ):
        """
        Processa o download da mídia, aplica a conversão
        solicitada e verifica fisicamente o arquivo final.
        """

        media_format = (media_format or "mp3").lower()

        # Validação do formato solicitado.
        if media_format not in SUPPORTED_FORMATS:
            raise ValueError(
                f"Formato não suportado: {media_format}"
            )

        # Confirma a disponibilidade do FFmpeg.
        if not shutil.which("ffmpeg"):
            raise RuntimeError(
                "FFmpeg não foi encontrado no PATH. "
                "Instale FFmpeg e reinicie o terminal."
            )

        # Suspende novos acessos ao YouTube durante
        # uma limitação temporária.
        check_youtube_cooldown(url)

        output_dir = Path(output_dir).resolve()

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        safe_title = sanitize_filename(title)

        options = {
            **self._base_options(
                cookie_browser,
                target=url,
            ),

            "outtmpl": str(
                output_dir / f"{safe_title}.%(ext)s"
            ),

            "progress_hooks": (
                [progress_hook] if progress_hook else []
            ),

            "windowsfilenames": True,
            "overwrites": False,
            "continuedl": True,

            "format": (
                "bestvideo+bestaudio/best"
                if media_format == "mp4"
                else "bestaudio/best"
            ),
        }

        # Configuração dos formatos de áudio.
        if media_format in {"mp3", "wav", "m4a"}:

            options["postprocessors"] = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": media_format,
                    "preferredquality": (
                        "192" if media_format == "mp3" else "0"
                    ),
                }
            ]

        # Configuração do formato MP4.
        elif media_format == "mp4":

            options["merge_output_format"] = "mp4"

            options["postprocessors"] = [
                {
                    "key": "FFmpegVideoRemuxer",
                    "preferedformat": "mp4",
                }
            ]

        # Configuração do formato WebM.
        elif media_format == "webm":

            options["format"] = (
                "bestvideo[ext=webm]+bestaudio[ext=webm]"
                "/best[ext=webm]/best"
            )

        # Executa o processamento.
        try:
            with YoutubeDL(options) as ydl:
                ydl.download([url])

        except Exception as exc:
            self._raise_friendly(
                exc,
                url,
                options["logger"],
            )

        # Identifica arquivos efetivamente gerados.
        candidates = [
            path
            for path in output_dir.glob(f"{safe_title}.*")
            if (
                path.is_file()
                and path.stat().st_size > 0
                and path.suffix.lower() in {
                    ".mp3",
                    ".mp4",
                    ".wav",
                    ".m4a",
                    ".webm",
                }
            )
        ]

        # Verifica primeiro o arquivo com o nome esperado.
        exact = output_dir / f"{safe_title}.{media_format}"

        if exact.is_file() and exact.stat().st_size > 0:
            return str(exact)

        # Verifica arquivos alternativos no formato solicitado.
        matches = [
            path
            for path in candidates
            if path.suffix.lower() == f".{media_format}"
        ]

        if matches:
            return str(
                max(matches, key=lambda p: p.stat().st_mtime)
            )

        if candidates:
            raise RuntimeError(
                "O download terminou, mas o arquivo final "
                f"não está no formato {media_format.upper()}."
            )

        raise RuntimeError(
            "O processo terminou sem gerar um arquivo final válido."
        )
