"""Proteção conservadora contra indisponibilidade do YouTube.

Não utiliza cookies, proxies ou mecanismos de contorno de restrições. Em modo
Cloud, um HTTP 429 recebido do YouTube interrompe novas solicitações por
um período curto. O estado é apenas em memória, por processo do servidor.
"""
import logging
import os
import time
from threading import Lock
from urllib.parse import urlparse

_LOG = logging.getLogger(__name__)
_LOCK = Lock()
_BLOCKED_UNTIL = 0.0


class YouTubeRemoteError(RuntimeError):
    """Falha externa reportada ao navegador sem detalhes técnicos internos."""

    http_status = 503

    def __init__(self, message, code="youtube_unavailable"):
        super().__init__(message)
        self.code = code


class YouTubeRateLimited(YouTubeRemoteError):
    """O servidor remoto sinalizou limitação temporária de acesso."""

    def __init__(self):
        super().__init__(
            "O YouTube está limitando as consultas deste servidor. "
            "Tente novamente mais tarde.",
            code="youtube_temporarily_limited",
        )


def is_youtube_target(value):
    """Distingue vídeos e buscas YouTube de URLs de outras plataformas."""
    if str(value or "").startswith("ytsearch"):
        return True
    host = (urlparse(str(value or "")).hostname or "").lower()
    return host in {"youtube.com", "youtu.be"} or host.endswith(".youtube.com")


def _cooldown_seconds():
    try:
        return max(0, min(int(os.environ.get("GROOVECATCH_YOUTUBE_COOLDOWN_SECONDS", "900")), 3600))
    except ValueError:
        return 900


def _cloud_enabled():
    return os.environ.get("GROOVECATCH_CLOUD") == "1"


def remaining_cooldown():
    """Segundos restantes. Útil para o cabeçalho Retry-After da API."""
    if not _cloud_enabled():
        return 0
    with _LOCK:
        return max(0, int(_BLOCKED_UNTIL - time.monotonic() + 0.999))


def record_youtube_429():
    """Marca cooldown apenas em Cloud, quando há sinal explícito de 429."""
    global _BLOCKED_UNTIL
    if not _cloud_enabled():
        return
    seconds = _cooldown_seconds()
    if seconds:
        with _LOCK:
            _BLOCKED_UNTIL = max(_BLOCKED_UNTIL, time.monotonic() + seconds)


def check_youtube_cooldown(value):
    """Bloqueia somente novos acessos ao YouTube durante a pausa."""
    if is_youtube_target(value) and remaining_cooldown():
        raise YouTubeRateLimited()


class YtDlpLogger:
    """Captura evidências HTTP 429/403 para classificar uma eventual falha."""

    def __init__(self, for_youtube=True):
        self.for_youtube = for_youtube
        self.saw_429 = False
        self.saw_403 = False

    def _record(self, message):
        message = str(message or "")
        lowered = message.lower()
        if self.for_youtube and ("http error 429" in lowered or "too many requests" in lowered):
            self.saw_429 = True
        if self.for_youtube and ("http error 403" in lowered or "403: forbidden" in lowered):
            self.saw_403 = True
        return message

    def debug(self, message):
        # Debug do yt-dlp não é necessário no log de produção.
        pass

    def warning(self, message):
        _LOG.warning("yt-dlp: %s", self._record(message))

    def error(self, message):
        _LOG.error("yt-dlp: %s", self._record(message))


def map_youtube_error(exc, logger, value):
    """Mapeia falhas do yt-dlp para mensagens seguras e códigos estáveis.

    Retorna None para outras plataformas ou erros fora da extração.
    """
    if not is_youtube_target(value):
        return None
    detail = str(exc or "").lower()
    if (logger and logger.saw_429) or "http error 429" in detail or "too many requests" in detail:
        record_youtube_429()
        return YouTubeRateLimited()
    if (logger and logger.saw_403) or "http error 403" in detail or "403: forbidden" in detail:
        return YouTubeRemoteError(
            "O YouTube recusou a solicitação deste servidor (HTTP 403). "
            "Não foi possível identificar a mídia neste momento.",
            code="youtube_access_denied",
        )
    if "failed to extract any player response" in detail:
        # Pode haver 429 capturado por outra requisição concorrente.
        if remaining_cooldown():
            return YouTubeRateLimited()
        return YouTubeRemoteError(
            "O YouTube não disponibilizou os dados necessários para identificar este vídeo.",
            code="youtube_extraction_failed",
        )
    return None
