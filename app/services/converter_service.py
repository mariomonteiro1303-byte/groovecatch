"""Conversão local e limitada de arquivos de áudio usando FFmpeg."""
import os
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from werkzeug.utils import secure_filename

ALLOWED_INPUTS = {"mp3", "wav", "flac", "m4a", "aac", "ogg", "opus"}
ALLOWED_OUTPUTS = {"mp3", "wav", "flac"}

def convert_audio(upload, target):
    """Converte um arquivo enviado; devolve caminho de saída e diretório temporário.

    O chamador deve apagar o diretório após transmitir o resultado.
    """
    if shutil.which("ffmpeg") is None:
        raise ValueError("FFmpeg não encontrado. Verifique a instalação no diagnóstico.")
    name = secure_filename(upload.filename or "")
    ext = Path(name).suffix.lower().lstrip(".")
    if ext not in ALLOWED_INPUTS or target not in ALLOWED_OUTPUTS:
        raise ValueError("Formato de áudio não suportado.")
    tempdir = Path(tempfile.mkdtemp(prefix="groovecatch_convert_"))
    try:
        source = tempdir / ("entrada." + ext)
        output = tempdir / ("saida." + target)
        upload.save(source)
        if source.stat().st_size == 0:
            raise ValueError("O arquivo está vazio.")
        cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y",
               "-i", str(source), "-vn"]
        if target == "mp3":
            cmd += ["-codec:a", "libmp3lame", "-q:a", "2"]
        elif target == "flac":
            cmd += ["-codec:a", "flac"]
        else:
            cmd += ["-codec:a", "pcm_s16le"]
        cmd.append(str(output))
        try:
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
        except subprocess.TimeoutExpired:
            raise ValueError("A conversão excedeu o limite de 3 minutos.")
        if completed.returncode or not output.exists() or output.stat().st_size == 0:
            raise ValueError("Não foi possível converter o áudio. Confira se o arquivo é válido.")
        return output, tempdir, Path(name).stem + "." + target
    except Exception:
        shutil.rmtree(tempdir, ignore_errors=True)
        raise
