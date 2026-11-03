"""Fila de downloads em memória com progresso, cancelamento e tentativas novamente."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Lock
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED
import shutil
import os
from app.services.youtube_service import YouTubeService, sanitize_filename, YouTubeAuthRequired
from app.repositories.history import HistoryRepository
from app.services.match_service import MatchService


class JobManager:
    """Coordena jobs concorrentes; o histórico concluído fica persistido em SQLite."""
    def __init__(self, workers=2):
        if os.environ.get("GROOVECATCH_CLOUD") == "1":
            workers = 1
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="groovecatch")
        self.jobs = {}
        self.cancel_flags = {}
        self.lock = Lock()
        self.youtube = YouTubeService()

    def active_count(self):
        """Número de tarefas pendentes ou em andamento no processo atual."""
        with self.lock:
            return sum(job.get("status") in {"queued", "running", "cancel_requested"}
                       for job in self.jobs.values())

    def submit_download(self, url, title, output_dir, database_path, media_format="mp3", metadata=None):
        """Cria job e envia para a fila, preservando título/artistas de origem quando disponíveis."""
        job_id = uuid4().hex
        metadata = metadata or {}
        job = {"id": job_id, "title": title or "Mídia", "url": url, "format": media_format,
               "status": "queued", "progress": 0, "message": "Na fila", "error": None,
               "file": None, "metadata": metadata, "created_at": __import__("datetime").datetime.now().astimezone().isoformat()}
        with self.lock:
            self.jobs[job_id] = job
            self.cancel_flags[job_id] = Event()
        self.executor.submit(self._run_download, job_id, url, title, output_dir, database_path, media_format, metadata)
        return dict(job)


    def submit_collection(self, collection_title, tracks, output_dir, database_path, media_format="mp3", cookie_browser=None):
        """Agenda um lote Spotify e entrega um único ZIP com as faixas concluídas."""
        job_id = uuid4().hex
        job = {"id": job_id, "title": collection_title or "Coleção Spotify", "url": "", "format": "zip",
               "status": "queued", "progress": 0, "message": "Lote na fila", "error": None, "file": None,
               "metadata": {"collection": True}, "created_at": __import__("datetime").datetime.now().astimezone().isoformat()}
        with self.lock:
            self.jobs[job_id] = job
            self.cancel_flags[job_id] = Event()
        self.executor.submit(self._run_collection, job_id, collection_title, tracks, output_dir, database_path, media_format, cookie_browser)
        return dict(job)

    def submit_youtube_playlist(self, title, tracks, output_dir, database_path, media_format="mp3", cookie_browser=None):
        """Agenda downloads diretos de vídeos selecionados, sem pesquisa por correspondência."""
        job_id = uuid4().hex
        job = {"id": job_id, "title": title, "url": "", "format": "zip", "status": "queued",
               "progress": 0, "message": "Playlist na fila", "error": None, "file": None,
               "metadata": {"youtube_playlist": True},
               "created_at": __import__("datetime").datetime.now().astimezone().isoformat()}
        with self.lock:
            self.jobs[job_id] = job
            self.cancel_flags[job_id] = Event()
        self.executor.submit(self._run_youtube_playlist, job_id, title, tracks, output_dir, database_path, media_format, cookie_browser)
        return dict(job)

    def _run_youtube_playlist(self, job_id, title, tracks, output_dir, database_path, media_format, cookie_browser):
        """Baixa cada URL individual, gera ZIP e relatório das falhas."""
        root = Path(output_dir)
        batch = root / "batches" / job_id
        batch.mkdir(parents=True, exist_ok=True)
        flag = self.cancel_flags[job_id]
        completed, failures = [], []
        total = len(tracks)
        try:
            for index, track in enumerate(tracks, 1):
                if flag.is_set():
                    raise InterruptedError("Playlist cancelada.")
                name = track["title"]
                self._update(job_id, status="running", progress=int((index-1)*90/total),
                             message=f"{index}/{total} · Baixando: {name}")
                try:
                    def hook(data, idx=index):
                        if flag.is_set():
                            raise InterruptedError("Playlist cancelada.")
                        if data.get("status") == "downloading":
                            size = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                            fraction = min(1, (data.get("downloaded_bytes") or 0) / size) if size else 0
                            self._update(job_id, progress=min(94, int(((idx-1)+fraction)*90/total)),
                                         message=f"{idx}/{total} · Baixando: {name}")
                    filename = f"{int(track['position']):03d} - {name}"
                    result = Path(self.youtube.download_media(track["url"], filename, batch, media_format, hook, cookie_browser=cookie_browser))
                    if not result.is_file() or not result.stat().st_size:
                        raise RuntimeError("Arquivo não foi gerado.")
                    completed.append(result)
                except (InterruptedError, YouTubeAuthRequired):
                    raise
                except Exception as exc:
                    failures.append(f"{name}: {exc}")
            if not completed:
                raise RuntimeError("Nenhum vídeo concluído. " + (failures[0] if failures else ""))
            self._update(job_id, progress=95, message="Criando arquivo ZIP...")
            archive_path = root / f"{sanitize_filename(title)} - {job_id[:8]}.zip"
            with ZipFile(archive_path, "w", ZIP_DEFLATED) as archive:
                for file in completed:
                    archive.write(file, arcname=file.name)
                if failures:
                    archive.writestr("_falhas.txt", "\n".join(failures))
            HistoryRepository(database_path).add({"title": title, "url": "youtube-playlist", "format": "zip", "file": str(archive_path)})
            self._update(job_id, status="completed", progress=100, file=str(archive_path),
                         message=f"{len(completed)}/{total} arquivo(s) no ZIP; {len(failures)} falha(s).",
                         completed_count=len(completed), failed_count=len(failures))
        except YouTubeAuthRequired as exc:
            self._update(job_id, status="failed", message="Autenticação exigida pelo YouTube", error=str(exc), error_code=exc.code)
        except InterruptedError as exc:
            self._update(job_id, status="cancelled", message=str(exc))
        except Exception as exc:
            self._update(job_id, status="failed", message="Falha na playlist", error=str(exc))
        finally:
            shutil.rmtree(batch, ignore_errors=True)

    def _run_collection(self, job_id, collection_title, tracks, output_dir, database_path, media_format, cookie_browser):
        """Resolve e baixa somente as faixas escolhidas, depois cria Nome da Playlist.zip."""
        root = Path(output_dir); root.mkdir(parents=True, exist_ok=True)
        batch_dir = root / "batches" / job_id
        batch_dir.mkdir(parents=True, exist_ok=True)
        flag = self.cancel_flags[job_id]
        total = max(1, len(tracks)); completed = []; failures = []
        matcher = MatchService(root)
        try:
            for index, track in enumerate(tracks, start=1):
                if flag.is_set(): raise InterruptedError("Lote cancelado pelo usuário.")
                artist = ", ".join(track.get("artists") or [])
                display = f"{artist} - {track.get('title','Faixa')}" if artist else track.get("title", "Faixa")
                self._update(job_id, status="running", progress=int((index-1)*90/total),
                             message=f"{index}/{total} · Procurando correspondência: {display}")
                try:
                    candidates = matcher.candidates(track, limit=1, cookie_browser=cookie_browser)
                    if not candidates:
                        raise RuntimeError("Nenhuma correspondência confiável encontrada.")
                    candidate = candidates[0]
                    numbered = f"{index:02d} - {display}"
                    def hook(data, idx=index):
                        if flag.is_set(): raise InterruptedError("Lote cancelado pelo usuário.")
                        if data.get("status") == "downloading":
                            total_b = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                            done_b = data.get("downloaded_bytes") or 0
                            frac = (done_b/total_b) if total_b else 0
                            self._update(job_id, progress=min(94, int(((idx-1)+frac)*90/total)), message=f"{idx}/{total} · Baixando: {display}")
                    output = self.youtube.download_media(candidate["url"], numbered, batch_dir, media_format, hook, cookie_browser=cookie_browser)
                    path = Path(output)
                    if not path.is_file() or path.stat().st_size <= 0: raise RuntimeError("Arquivo final ausente ou vazio.")
                    completed.append(path)
                    if track.get("spotify_id"):
                        try: matcher.remember(track["spotify_id"], candidate["url"], display)
                        except Exception: pass
                except YouTubeAuthRequired:
                    raise
                except InterruptedError:
                    raise
                except Exception as exc:
                    failures.append(f"{display}: {exc}")
            if not completed:
                raise RuntimeError("Nenhuma faixa pôde ser concluída. " + (failures[0] if failures else ""))
            self._update(job_id, progress=95, message=f"Compactando {len(completed)} arquivo(s)...")
            zip_name = sanitize_filename(collection_title or "Coleção Spotify") + ".zip"
            zip_path = root / zip_name
            # Evita colisão com um ZIP anterior sem apagar o arquivo existente.
            if zip_path.exists():
                zip_path = root / f"{sanitize_filename(collection_title or 'Coleção Spotify')} - {job_id[:6]}.zip"
            with ZipFile(zip_path, "w", ZIP_DEFLATED) as archive:
                for path in completed:
                    archive.write(path, arcname=path.name)
                if failures:
                    archive.writestr("_falhas.txt", "Algumas faixas não foram incluídas:\n\n" + "\n".join(failures))
            if not zip_path.is_file() or zip_path.stat().st_size <= 0: raise RuntimeError("O ZIP final não foi criado corretamente.")
            HistoryRepository(database_path).add({"title": collection_title, "url": "spotify-collection", "format": "zip", "file": str(zip_path)})
            msg = f"{len(completed)} de {len(tracks)} faixa(s) concluída(s). ZIP pronto."
            if failures: msg += f" {len(failures)} falha(s) registrada(s) em _falhas.txt."
            self._update(job_id, status="completed", progress=100, message=msg, file=str(zip_path),
                         completed_count=len(completed), failed_count=len(failures))
        except YouTubeAuthRequired as exc:
            self._update(job_id, status="failed", message="O YouTube solicitou autenticação durante o lote", error=str(exc), error_code=exc.code, technical_detail=exc.technical_detail)
        except InterruptedError as exc:
            self._update(job_id, status="cancelled", message=str(exc), error=None)
        except Exception as exc:
            self._update(job_id, status="failed", message="Falha no lote", error=str(exc))
        finally:
            # O ZIP é a entrega. Temporários da coleção não precisam permanecer.
            shutil.rmtree(batch_dir, ignore_errors=True)

    def _update(self, job_id, **values):
        """Atualiza estado de forma sincronizada para consultas simultâneas."""
        with self.lock:
            if job_id in self.jobs:
                self.jobs[job_id].update(values)

    def _run_download(self, job_id, url, title, output_dir, database_path, media_format, metadata):
        """Lê metadados reais antes do nome final, baixa e verifica o arquivo."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        flag = self.cancel_flags[job_id]
        self._update(job_id, status="running", message="Lendo metadados da mídia")
        try:
            cookie_browser = metadata.get("cookie_browser")
            info = self.youtube.get_info(url, cookie_browser=cookie_browser)
            # Título de origem tem prioridade para URL direta; Spotify mantém título e artista da faixa.
            if metadata.get("spotify_id"):
                # Inclui artista no nome-base para distinguir faixas homônimas.
                artist_text = ", ".join(metadata.get("artists") or [])
                title = f"{metadata.get('spotify_title') or title} - {artist_text}" if artist_text else (metadata.get("spotify_title") or title)
            else:
                title = info.get("title") or title
            safe_title = sanitize_filename(title)
            self._update(job_id, title=title, filename=f"{safe_title}.{media_format}", message="Iniciando download")

            def progress_hook(data):
                """Converte callbacks do yt-dlp em progresso legível na interface."""
                if flag.is_set():
                    raise InterruptedError("Download cancelado pelo usuário.")
                if data.get("status") == "downloading":
                    total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                    done = data.get("downloaded_bytes") or 0
                    percent = int(done * 100 / total) if total else 0
                    self._update(job_id, progress=min(percent, 98), message="Baixando mídia",
                                 speed_bps=data.get("speed") or 0,
                                 eta_seconds=data.get("eta"),
                                 downloaded_bytes=done,
                                 total_bytes=total)
                elif data.get("status") == "finished":
                    self._update(job_id, progress=99, message="Convertendo e validando arquivo final")

            self._update(job_id, message="Baixando mídia")
            output = self.youtube.download_media(url, title, output_dir, media_format, progress_hook, cookie_browser=cookie_browser)
            path = Path(output)
            if flag.is_set():
                self._update(job_id, status="cancelled", message="Download cancelado", progress=0)
                return
            if not path.is_file() or path.stat().st_size <= 0:
                raise RuntimeError("Arquivo final ausente ou vazio; o job não será marcado como concluído.")
            HistoryRepository(database_path).add({"title": title, "url": url, "format": media_format, "file": str(path)})
            # Salva o pareamento Spotify somente após o arquivo ter sido validado.
            if metadata.get("spotify_id"):
                try:
                    MatchService(output_dir).remember(metadata.get("spotify_id"), url, title)
                except Exception:
                    pass  # Falha no cache não invalida um download que foi concluído corretamente.
            self._update(job_id, status="completed", progress=100, message="Download concluído e arquivo validado", file=str(path))
        except YouTubeAuthRequired as exc:
            self._update(job_id, status="failed", message="O YouTube solicitou autenticação", error=str(exc),
                         error_code=exc.code, technical_detail=exc.technical_detail)
        except InterruptedError as exc:
            self._update(job_id, status="cancelled", message=str(exc), error=None)
        except Exception as exc:
            self._update(job_id, status="failed", message="Falha no download", error=str(exc))

    def get(self, job_id):
        """Retorna uma cópia do estado para impedir alterações externas."""
        with self.lock:
            job = self.jobs.get(job_id)
            return dict(job) if job else None

    def cancel(self, job_id):
        """Sinaliza cancelamento cooperativo ao hook de progresso do yt-dlp."""
        with self.lock:
            job = self.jobs.get(job_id)
            flag = self.cancel_flags.get(job_id)
            if not job or job["status"] in {"completed", "failed", "cancelled"}:
                return False
            flag.set()
            if job["status"] == "queued":
                job.update(status="cancelled", message="Download cancelado antes de iniciar")
            return True

    def retry(self, job_id, output_dir, database_path, cookie_browser=None):
        """Cria um novo job com os mesmos parâmetros de uma tentativa que falhou."""
        old = self.get(job_id)
        if not old or old.get("status") not in {"failed", "cancelled"}:
            raise ValueError("Só é possível tentar novamente jobs com falha ou cancelados.")
        metadata = dict(old.get("metadata") or {})
        if cookie_browser:
            metadata["cookie_browser"] = cookie_browser
        elif old.get("error_code") == "youtube_auth_required" and not metadata.get("cookie_browser"):
            raise ValueError("Escolha um navegador autenticado para continuar com este conteúdo do YouTube.")
        return self.submit_download(old["url"], old["title"], output_dir, database_path, old["format"], metadata)


job_manager = JobManager()
