"""Diagnósticos básicos de dependências da instalação local."""
import shutil
import sys
from importlib import metadata


def run_diagnostics():
    """Retorna verificações locais sem solicitar ou expor credenciais."""
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    return {"checks": [
        {"name": "Python", "ok": sys.version_info >= (3, 10), "detail": sys.version.split()[0]},
        {"name": "yt-dlp", "ok": _has_module("yt_dlp"), "detail": _package_version("yt-dlp")},
        {"name": "yt-dlp-ejs", "ok": _has_module("yt_dlp_ejs"), "detail": _package_version("yt-dlp-ejs")},
        {"name": "Deno", "ok": bool(shutil.which("deno")), "detail": shutil.which("deno") or "Não encontrado no PATH"},
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


def _package_version(package):
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return "Não instalado"
