"""Ferramentas de mídia locais, com formatos controlados e limpeza temporária."""
import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from werkzeug.utils import secure_filename

AUDIO = {"mp3", "wav", "flac", "m4a", "aac", "ogg", "opus"}
VIDEO = {"mp4", "mkv", "webm", "mov", "avi"}
OUTPUT = {"mp3", "wav", "flac"}
MAX_FILES = 3 if os.environ.get("GROOVECATCH_CLOUD") == "1" else 20

def process_files(uploads, operation, target="mp3", start=None, end=None):
    """Processa uploads em diretório isolado; devolve caminho, pasta e nome do download."""
    if shutil.which("ffmpeg") is None:
        raise ValueError("FFmpeg não encontrado.")
    if operation not in {"trim", "extract", "normalize", "batch"}:
        raise ValueError("Operação inválida.")
    if target not in OUTPUT:
        raise ValueError("Formato de saída inválido.")
    if not uploads or len(uploads) > MAX_FILES:
        raise ValueError("Selecione entre 1 e 20 arquivos.")
    if operation != "batch" and len(uploads) != 1:
        raise ValueError("Esta ferramenta aceita somente um arquivo.")
    if operation == "trim":
        try:
            start, end = float(start), float(end)
        except (TypeError, ValueError):
            raise ValueError("Informe início e fim em segundos.")
        if not (0 <= start < end <= 86400):
            raise ValueError("Intervalo inválido: o fim deve ser maior que o início.")
    folder = Path(tempfile.mkdtemp(prefix="groovecatch_tools_"))
    outputs = []
    failures = []
    try:
        for index, upload in enumerate(uploads, 1):
            original = secure_filename(upload.filename or "")
            ext = Path(original).suffix.lower().lstrip(".")
            allowed = VIDEO if operation == "extract" else AUDIO
            if ext not in allowed:
                failures.append(f"{original or 'Arquivo'}: formato não suportado")
                continue
            source = folder / f"input_{index}.{ext}"
            upload.save(source)
            if not source.stat().st_size:
                failures.append(f"{original}: arquivo vazio")
                continue
            suffix = {"trim": "_corte", "extract": "_audio", "normalize": "_normalizado", "batch": ""}[operation]
            filename = f"{index:02d} - {Path(original).stem}{suffix}.{target}" if operation == "batch" else f"{Path(original).stem}{suffix}.{target}"
            result = folder / filename
            cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error", "-y"]
            if operation == "trim":
                cmd += ["-ss", str(start), "-i", str(source), "-t", str(end-start)]
            else:
                cmd += ["-i", str(source)]
            cmd += ["-vn"]
            if operation == "normalize":
                cmd += ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"]
            cmd += {"mp3":["-c:a","libmp3lame","-q:a","2"], "wav":["-c:a","pcm_s16le"], "flac":["-c:a","flac"]}[target]
            cmd.append(str(result))
            try:
                run = subprocess.run(cmd, capture_output=True, text=True, timeout=120 if os.environ.get("GROOVECATCH_CLOUD") == "1" else 240, check=False)
                if run.returncode or not result.exists() or result.stat().st_size == 0:
                    raise ValueError("Falha na conversão")
                outputs.append(result)
            except (subprocess.TimeoutExpired, ValueError):
                failures.append(f"{original}: falha no processamento")
        if not outputs:
            raise ValueError("Nenhum arquivo foi processado. " + "; ".join(failures[:3]))
        if operation == "batch":
            archive = folder / "GrooveCatch_Convertidos.zip"
            with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
                for item in outputs:
                    z.write(item, item.name)
                if failures:
                    z.writestr("_falhas.txt", "\\n".join(failures).replace("\\n", "\n"))
            return archive, folder, archive.name
        return outputs[0], folder, outputs[0].name
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise
