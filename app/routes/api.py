"""Rotas JSON do frontend: resolução, downloads, histórico e diagnósticos."""
from pathlib import Path
from flask import Blueprint, current_app, jsonify, request, send_file
from app.services.diagnostic_service import run_diagnostics
from app.services.connection_service import connection_status
from app.services.input_resolver import InputResolver
from app.services.match_service import MatchService
from app.services.youtube_service import YouTubeService, YouTubeAuthRequired
from app.services.media_service import SUPPORTED_FORMATS
from app.jobs.manager import job_manager
from app.repositories.history import HistoryRepository

bp = Blueprint("api", __name__)


def cloud_cookie_browser(value):
    """Nunca tenta acessar cookies de navegadores no servidor Render."""
    return None if current_app.config.get("CLOUD_MODE") else value


def validate_cloud_url(url):
    """Allowlist reduz o risco de SSRF nos extratores de mídia em nuvem."""
    if not current_app.config.get("CLOUD_MODE"):
        return
    from urllib.parse import urlparse
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    allowed = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "music.youtube.com",
               "open.spotify.com", "spotify.link", "soundcloud.com", "www.soundcloud.com"}
    if parsed.scheme != "https" or host not in allowed or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("Na edição Cloud, utilize links HTTPS de YouTube, Spotify ou SoundCloud.")



@bp.get("/connection")
def connection():
    """Conectividade e latência. Velocidade vem dos downloads reais."""
    return jsonify(connection_status())


@bp.get("/diagnostics")
def diagnostics():
    """Retorna dependências e configuração sem expor segredos."""
    return jsonify(run_diagnostics())


@bp.post("/resolve")
def resolve_input():
    """Classifica entrada como Spotify, URL de mídia ou texto de busca."""
    payload = request.get_json(silent=True) or {}
    value = (payload.get("input") or "").strip()
    if not value:
        return jsonify({"error": "Cole um link ou digite o nome da música."}), 400
    try:
        if value.startswith(("https://", "http://")):
            validate_cloud_url(value)
        cookie_browser = cloud_cookie_browser((payload.get("cookie_browser") or "").strip().lower() or None)
        return jsonify(InputResolver().resolve(value, current_app.config["STORAGE_DIR"], cookie_browser=cookie_browser))
    except YouTubeAuthRequired as exc:
        return jsonify({"error": str(exc), "code": exc.code, "technical_detail": exc.technical_detail,
                        "browsers": ["chrome", "edge", "firefox", "brave"]}), 401
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@bp.post("/spotify/match")
def spotify_match():
    """Resolve uma única faixa Spotify sob demanda. Coleções deixam de bloquear a identificação."""
    payload = request.get_json(silent=True) or {}
    track = payload.get("track") or {}
    cookie_browser = cloud_cookie_browser((payload.get("cookie_browser") or "").strip().lower() or None)
    try:
        candidates = MatchService(current_app.config["STORAGE_DIR"]).candidates(track, limit=1, cookie_browser=cookie_browser)
        return jsonify({"candidates": candidates})
    except YouTubeAuthRequired as exc:
        return jsonify({"error": str(exc), "code": exc.code, "technical_detail": exc.technical_detail, "browsers": ["chrome","edge","firefox","brave"]}), 401
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@bp.post("/collections/downloads")
def start_collection_download():
    """Baixa as faixas Spotify selecionadas e entrega um único ZIP nomeado pela coleção."""
    payload = request.get_json(silent=True) or {}
    tracks = payload.get("tracks") or []
    title = (payload.get("collection_title") or "Coleção Spotify").strip()
    media_format = (payload.get("format") or "mp3").lower()
    cookie_browser = cloud_cookie_browser((payload.get("cookie_browser") or "").strip().lower() or None)
    if not tracks:
        return jsonify({"error": "Selecione pelo menos uma faixa."}), 400
    if len(tracks) > (5 if current_app.config.get("CLOUD_MODE") else 500):
        return jsonify({"error": "O lote excede o limite de 500 faixas."}), 400
    if media_format not in {"mp3", "m4a", "wav"}:
        return jsonify({"error": "Coleções Spotify aceitam MP3, M4A ou WAV."}), 400
    if current_app.config.get("CLOUD_MODE") and job_manager.active_count() >= 2:
        return jsonify({"error": "Fila cheia. Aguarde a conclusão de uma tarefa."}), 429
    job = job_manager.submit_collection(title, tracks, current_app.config["STORAGE_DIR"], current_app.config["DATABASE_PATH"], media_format, cookie_browser)
    return jsonify({"job": job}), 202


@bp.post("/youtube/playlist/downloads")
def youtube_playlist_downloads():
    """Recebe seleção validada de vídeos e agenda download ZIP."""
    from app.services.youtube_playlist_service import playlist_id
    payload = request.get_json(silent=True) or {}
    tracks = payload.get("tracks") or []
    media_format = str(payload.get("format") or "mp3").lower()
    if media_format not in {"mp3", "m4a", "wav", "mp4", "webm"}:
        return jsonify({"error": "Formato não suportado para playlist."}), 400
    if not isinstance(tracks, list) or not 1 <= len(tracks) <= (5 if current_app.config.get("CLOUD_MODE") else 500):
        return jsonify({"error": "Selecione entre 1 e 500 vídeos."}), 400
    clean = []
    for track in tracks:
        if not isinstance(track, dict) or not playlist_id("https://www.youtube.com/playlist?list=" + str(payload.get("playlist_id") or "")):
            return jsonify({"error": "Identificador de playlist inválido."}), 400
        url = str(track.get("url") or "")
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(url)
        if (parsed.hostname or "").lower() not in {"youtube.com", "www.youtube.com", "m.youtube.com"} or parsed.path != "/watch":
            return jsonify({"error": "URL de vídeo inválida."}), 400
        vid = parse_qs(parsed.query).get("v", [""])[0]
        if len(vid) != 11 or not vid.replace("-", "").replace("_", "").isalnum():
            return jsonify({"error": "Identificador de vídeo inválido."}), 400
        try:
            position = int(track.get("position"))
        except (TypeError, ValueError):
            return jsonify({"error": "Posição inválida."}), 400
        if not 1 <= position <= 500:
            return jsonify({"error": "Posição inválida."}), 400
        clean.append({"title": str(track.get("title") or "Vídeo")[:180], "url": f"https://www.youtube.com/watch?v={vid}", "position": position})
    title = str(payload.get("collection_title") or "Playlist YouTube")[:150]
    cookie_browser = cloud_cookie_browser((payload.get("cookie_browser") or "").strip().lower() or None)
    if current_app.config.get("CLOUD_MODE") and job_manager.active_count() >= 2:
        return jsonify({"error": "Fila cheia. Aguarde a conclusão de uma tarefa."}), 429
    job = job_manager.submit_youtube_playlist(title, clean, current_app.config["STORAGE_DIR"],
                                              current_app.config["DATABASE_PATH"], media_format, cookie_browser)
    return jsonify({"job": job}), 202


@bp.post("/downloads")
def start_download():
    """Agenda download e deixa o serviço obter título real antes de nomear arquivo."""
    payload = request.get_json(silent=True) or {}
    url = (payload.get("url") or "").strip()
    title = (payload.get("title") or "").strip()
    media_format = (payload.get("format") or "mp3").lower()
    metadata = payload.get("metadata") or {}
    cookie_browser = cloud_cookie_browser((payload.get("cookie_browser") or "").strip().lower() or None)
    if cookie_browser:
        metadata["cookie_browser"] = cookie_browser
    if not url.startswith(("https://", "http://")):
        return jsonify({"error": "O item selecionado não possui uma URL válida."}), 400
    try:
        validate_cloud_url(url)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if media_format not in SUPPORTED_FORMATS:
        return jsonify({"error": f"Formato inválido: {', '.join(sorted(SUPPORTED_FORMATS))}"}), 400
    if current_app.config.get("CLOUD_MODE") and job_manager.active_count() >= 2:
        return jsonify({"error": "Fila cheia. Aguarde a conclusão de uma tarefa."}), 429
    job = job_manager.submit_download(url, title, current_app.config["STORAGE_DIR"],
                                      current_app.config["DATABASE_PATH"], media_format, metadata)
    return jsonify({"job": job}), 202


@bp.get("/jobs/<job_id>")
def get_job(job_id):
    """Consulta status e URL de entrega somente após validação do arquivo."""
    job = job_manager.get(job_id)
    if not job:
        return jsonify({"error": "Job não encontrado. A fila é mantida em memória e pode ser perdida ao reiniciar o servidor."}), 404
    if job.get("status") == "completed" and job.get("file"):
        path = Path(job["file"])
        if path.is_file() and path.stat().st_size > 0:
            job["download_url"] = f"/api/jobs/{job_id}/file"
            job["filename"] = path.name
        else:
            job.update(status="failed", error="Arquivo final não existe mais no armazenamento.", download_url=None)
    return jsonify(job)


@bp.post("/jobs/<job_id>/cancel")
def cancel_job(job_id):
    """Solicita cancelamento cooperativo do download."""
    if not job_manager.cancel(job_id):
        return jsonify({"error": "Job não encontrado ou já finalizado."}), 409
    return jsonify({"ok": True, "status": "cancel_requested"})


@bp.post("/jobs/<job_id>/retry")
def retry_job(job_id):
    """Agenda nova tentativa. Para anti-bot, exige navegador explicitamente escolhido."""
    payload = request.get_json(silent=True) or {}
    cookie_browser = cloud_cookie_browser((payload.get("cookie_browser") or "").strip().lower() or None)
    try:
        job = job_manager.retry(job_id, current_app.config["STORAGE_DIR"], current_app.config["DATABASE_PATH"], cookie_browser=cookie_browser)
        return jsonify({"job": job}), 202
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@bp.get("/jobs/<job_id>/file")
def download_completed_file(job_id):
    """Entrega arquivo validado ao navegador com nome original sanitizado."""
    job = job_manager.get(job_id)
    if not job or job.get("status") != "completed" or not job.get("file"):
        return jsonify({"error": "O arquivo ainda não está pronto."}), 404
    file_path = Path(job["file"])
    if not file_path.is_file() or file_path.stat().st_size <= 0:
        return jsonify({"error": "O arquivo não foi encontrado ou está vazio."}), 404
    return send_file(file_path, as_attachment=True, download_name=file_path.name)


@bp.post("/preview")
def create_preview():
    """Gera uma prévia curta da opção selecionada e devolve uma URL de reprodução local."""
    payload = request.get_json(silent=True) or {}
    url = (payload.get("url") or "").strip()
    cookie_browser = cloud_cookie_browser((payload.get("cookie_browser") or "").strip().lower() or None)
    if not url.startswith(("https://", "http://")):
        return jsonify({"error": "URL inválida para pré-visualização."}), 400
    try:
        validate_cloud_url(url)
        path = YouTubeService().create_preview(url, current_app.config["STORAGE_DIR"], cookie_browser=cookie_browser)
        file_path = Path(path)
        return jsonify({"preview_url": f"/api/preview/file/{file_path.name}"})
    except YouTubeAuthRequired as exc:
        return jsonify({"error": str(exc), "code": exc.code, "technical_detail": exc.technical_detail,
                        "browsers": ["chrome", "edge", "firefox", "brave"]}), 401
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400


@bp.get("/preview/file/<filename>")
def preview_file(filename):
    """Entrega somente arquivos de prévia gerados dentro do diretório controlado da aplicação."""
    safe_name = Path(filename).name
    path = Path(current_app.config["STORAGE_DIR"]) / "previews" / safe_name
    if not path.is_file() or path.suffix.lower() != ".mp3":
        return jsonify({"error": "Prévia não encontrada."}), 404
    return send_file(path, mimetype="audio/mpeg", conditional=True)


@bp.get("/history")
def history():
    """Lista histórico SQLite e informa se cada arquivo continua presente."""
    return jsonify({"items": HistoryRepository(current_app.config["DATABASE_PATH"]).list()})

@bp.get("/radios/search")
def radio_search():
    """Pesquisa rádios. Radio Garden é tentado primeiro; fallback é transparente."""
    from app.services.radio_service import RadioService
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"error": "Digite pelo menos 2 caracteres para pesquisar rádios."}), 400
    field = (request.args.get("field") or "auto").strip().lower()
    if field not in ("auto", "name", "city", "state", "country", "tag"):
        return jsonify({"error": "Filtro de busca inválido."}), 400
    try:
        return jsonify(RadioService().search(q, limit=24, field=field))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502


@bp.get("/radios/nearby")
def radio_nearby():
    """Sugere rádios próximas usando coordenadas enviadas após consentimento no navegador."""
    from app.services.radio_service import RadioService
    try:
        lat = float(request.args["lat"]); lon = float(request.args["lon"])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180): raise ValueError
    except Exception:
        return jsonify({"error": "Localização inválida."}), 400
    try:
        return jsonify(RadioService().nearby(lat, lon, limit=24))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502

@bp.post("/radios/now-playing")
def radio_now_playing():
    """Tenta ler metadados ICY publicados pelo stream atual."""
    from app.services.radio_service import read_icy_now_playing
    payload = request.get_json(silent=True) or {}
    stream_url = (payload.get("stream_url") or "").strip()
    if not stream_url:
        return jsonify({"title": None, "available": False})
    if current_app.config.get("CLOUD_MODE"):
        return jsonify({"title": None, "available": False, "error": "Leitura remota de streams desativada no piloto Cloud."})
    title = read_icy_now_playing(stream_url)
    return jsonify({"title": title, "available": bool(title)})


@bp.post("/tools/convert-audio")
def convert_audio_route():
    """Recebe áudio local, converte e devolve um arquivo para salvar pelo navegador."""
    import shutil
    from flask import after_this_request
    from app.services.converter_service import convert_audio
    uploaded = request.files.get("file")
    target = (request.form.get("format") or "").lower()
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "Selecione um arquivo de áudio."}), 400
    try:
        output, tempdir, download_name = convert_audio(uploaded, target)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    @after_this_request
    def cleanup(response):
        response.call_on_close(lambda: shutil.rmtree(tempdir, ignore_errors=True))
        return response
    return send_file(output, as_attachment=True, download_name=download_name)


@bp.post("/tools/process")
def process_media_tool():
    """Executa corte, extração, normalização ou lote; envia resultado ao navegador."""
    import shutil
    from flask import after_this_request
    from app.services.media_tools_service import process_files
    files = request.files.getlist("files")
    try:
        output, tempdir, filename = process_files(
            files, request.form.get("operation", ""),
            request.form.get("format", "mp3"),
            request.form.get("start"), request.form.get("end"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    @after_this_request
    def cleanup(response):
        response.call_on_close(lambda: shutil.rmtree(tempdir, ignore_errors=True))
        return response
    return send_file(output, as_attachment=True, download_name=filename)


@bp.post("/tools/video")
def video_tools():
    """Processa vídeo local e entrega MP4 ao navegador."""
    import shutil
    from flask import after_this_request
    from app.services.video_tools_service import process_video
    upload = request.files.get("file")
    if upload is None:
        return jsonify({"error": "Selecione um vídeo."}), 400
    try:
        output, tempdir, filename = process_video(
            upload,
            request.form.get("operation", ""),
            request.form.get("preset", "equilibrada"),
            request.form.get("start"), request.form.get("end"))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    @after_this_request
    def cleanup(response):
        response.call_on_close(lambda: shutil.rmtree(tempdir, ignore_errors=True))
        return response
    return send_file(output, as_attachment=True, download_name=filename)


@bp.post("/tools/advanced")
def advanced_media_tools():
    """Ferramentas locais: metadados, quadro de vídeo e GIF."""
    import shutil
    from flask import after_this_request
    from app.services.advanced_tools_service import process_advanced
    upload=request.files.get("file")
    if upload is None:
        return jsonify({"error":"Selecione um arquivo."}),400
    try:
        output,tempdir,filename=process_advanced(upload,request.form.get("operation",""),request.form)
    except ValueError as exc:
        return jsonify({"error":str(exc)}),400
    @after_this_request
    def cleanup(response):
        response.call_on_close(lambda:shutil.rmtree(tempdir,ignore_errors=True))
        return response
    return send_file(output,as_attachment=True,download_name=filename)
