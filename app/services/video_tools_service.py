"""Compressão e corte de vídeos locais usando FFmpeg, sem comandos de shell."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from werkzeug.utils import secure_filename

ALLOWED = {"mp4", "mkv", "webm", "mov", "avi"}
PRESETS = {
    "leve": ("23", "medium"),
    "equilibrada": ("28", "medium"),
    "alta": ("33", "fast"),
}
MAX_UPLOAD = (100 if os.environ.get("GROOVECATCH_CLOUD") == "1" else 500) * 1024 * 1024

def process_video(upload, operation, preset="equilibrada", start=None, end=None):
    if shutil.which("ffmpeg") is None:
        raise ValueError("FFmpeg não encontrado no sistema.")
    if operation not in {"compress", "trim"}:
        raise ValueError("Operação inválida.")
    original = secure_filename(upload.filename or "")
    extension = Path(original).suffix.lower().lstrip(".")
    if extension not in ALLOWED:
        raise ValueError("Selecione um vídeo MP4, MKV, WEBM, MOV ou AVI.")
    if operation == "compress" and preset not in PRESETS:
        raise ValueError("Qualidade inválida.")
    if operation == "trim":
        try:
            start, end = float(start), float(end)
        except (ValueError, TypeError):
            raise ValueError("Informe início e fim em segundos.")
        if not (0 <= start < end <= 86400):
            raise ValueError("O fim deve ser maior que o início.")
    tempdir = Path(tempfile.mkdtemp(prefix="groovecatch_video_"))
    try:
        source = tempdir / f"entrada.{extension}"
        upload.save(source)
        if not source.stat().st_size or source.stat().st_size > MAX_UPLOAD:
            raise ValueError("Arquivo vazio ou acima do limite de 500 MB.")
        label = "comprimido" if operation == "compress" else "corte"
        filename = f"{Path(original).stem}_{label}.mp4"
        result = tempdir / filename
        cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y"]
        if operation == "trim":
            cmd += ["-ss", str(start)]
        cmd += ["-i", str(source)]
        if operation == "trim":
            cmd += ["-t", str(end-start)]
        crf, speed = PRESETS[preset] if operation == "compress" else ("22", "veryfast")
        cmd += ["-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264", "-preset", speed,
                "-crf", crf, "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart", str(result)]
        try:
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=180 if os.environ.get("GROOVECATCH_CLOUD") == "1" else 900)
        except subprocess.TimeoutExpired:
            raise ValueError("Processamento excedeu 15 minutos.")
        if completed.returncode or not result.exists() or not result.stat().st_size:
            raise ValueError("Não foi possível processar o vídeo. Verifique o arquivo de origem.")
        return result, tempdir, filename
    except Exception:
        shutil.rmtree(tempdir, ignore_errors=True)
        raise
