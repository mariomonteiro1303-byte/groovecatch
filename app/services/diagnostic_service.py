"""Diagnósticos básicos de dependências da instalação local."""
import shutil
import sys


def run_diagnostics():
    """Retorna verificações locais sem solicitar ou expor credenciais."""
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    return {"checks": [
        {"name": "Python", "ok": sys.version_info >= (3, 10), "detail": sys.version.split()[0]},
        {"name": "yt-dlp", "ok": _has_module("yt_dlp"), "detail": "Instalado" if _has_module("yt_dlp") else "Não instalado"},
        {"name": "FFmpeg", "ok": bool(ffmpeg), "detail": ffmpeg or "Não encontrado no PATH"},
        {"name": "FFprobe", "ok": bool(ffprobe), "detail": ffprobe or "Não encontrado no PATH"},
        {"name": "Spotify", "ok": True, "detail": "oEmbed público · sem Client ID/Secret"},
    ]}


def _has_module(name):
    """Confere importação sem executar serviços externos."""
    try:
        __import__(name)
        return True
    except ImportError:
        return False
