"""Ferramentas de metadados e quadros/GIF usando FFmpeg local."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from werkzeug.utils import secure_filename

VIDEO_EXT={"mp4","mkv","webm","mov","avi"}
AUDIO_EXT={"mp3","flac","m4a","ogg"}

def process_advanced(upload, operation, options):
    """Retorna arquivo gerado, diretório temporário e nome de download."""
    if shutil.which("ffmpeg") is None:
        raise ValueError("FFmpeg não encontrado no PATH.")
    if operation not in {"frame","gif","metadata"}:
        raise ValueError("Ferramenta desconhecida.")
    name=secure_filename(upload.filename or "")
    ext=Path(name).suffix.lower().lstrip(".")
    allowed=AUDIO_EXT if operation=="metadata" else VIDEO_EXT
    if ext not in allowed:
        raise ValueError("Formato não suportado para esta ferramenta.")
    temp=Path(tempfile.mkdtemp(prefix="groovecatch_advanced_"))
    try:
        src=temp/f"entrada.{ext}"
        upload.save(src)
        if src.stat().st_size==0 or src.stat().st_size>500*1024*1024:
            raise ValueError("Arquivo vazio ou acima de 500 MB.")
        cmd=["ffmpeg","-hide_banner","-nostdin","-loglevel","error","-y"]
        stem=Path(name).stem
        if operation=="frame":
            try: seconds=float(options.get("start",0))
            except (ValueError,TypeError): raise ValueError("Tempo inválido.")
            if not 0<=seconds<=86400: raise ValueError("Tempo fora do intervalo permitido.")
            fmt=options.get("format","jpg")
            if fmt not in {"jpg","png"}: raise ValueError("Formato de imagem inválido.")
            filename=f"{stem}_quadro.{fmt}"; result=temp/filename
            cmd += ["-ss",str(seconds),"-i",str(src),"-frames:v","1",str(result)]
        elif operation=="gif":
            try: start=float(options.get("start",0));end=float(options.get("end",3))
            except (ValueError,TypeError): raise ValueError("Intervalo inválido.")
            if not 0<=start<end<=86400 or end-start>15:
                raise ValueError("GIF deve ter duração entre 0 e 15 segundos.")
            filename=f"{stem}_animado.gif";result=temp/filename
            # Palettegen/paletteuse melhoram a qualidade da conversão.
            filtergraph="fps=10,scale=480:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse"
            cmd += ["-ss",str(start),"-i",str(src),"-t",str(end-start),"-filter_complex",filtergraph,"-loop","0",str(result)]
        else:
            filename=f"{stem}_metadados.{ext}";result=temp/filename
            cmd += ["-i",str(src),"-map","0","-c","copy"]
            for field in ("title","artist","album","date","genre"):
                val=(options.get(field) or "").strip()
                if val:
                    if len(val)>200: raise ValueError("Metadado excede 200 caracteres.")
                    cmd += ["-metadata",f"{field}={val}"]
            cmd += [str(result)]
        if operation!="metadata": pass
        try: completed=subprocess.run(cmd,capture_output=True,text=True,timeout=600)
        except subprocess.TimeoutExpired: raise ValueError("Tempo de processamento excedido.")
        if completed.returncode!=0 or not result.exists() or not result.stat().st_size:
            raise ValueError("Falha ao processar. Confira se o arquivo contém mídia válida e o intervalo existe.")
        return result,temp,filename
    except Exception:
        shutil.rmtree(temp,ignore_errors=True)
        raise
