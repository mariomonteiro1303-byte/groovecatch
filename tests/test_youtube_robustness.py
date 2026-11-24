from pathlib import Path

import pytest

from app.jobs.manager import JobManager
from app.repositories.history import HistoryRepository
from app.services import youtube_policy, youtube_service


def test_success_after_429_warning_does_not_start_cooldown(monkeypatch):
    class Extractor:
        def __init__(self, options):
            self.logger = options["logger"]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, url, download):
            self.logger.warning("HTTP Error 429: Too Many Requests")
            return {"title": "Música"}

    monkeypatch.setenv("GROOVECATCH_CLOUD", "1")
    monkeypatch.setattr(youtube_policy, "_BLOCKED_UNTIL", 0.0)
    monkeypatch.setattr(youtube_service, "YoutubeDL", Extractor)

    assert youtube_service.YouTubeService().get_info("https://youtu.be/Uec6DC3-ffU")["title"] == "Música"
    assert youtube_policy.remaining_cooldown() == 0


def test_download_preserves_percentages_and_brackets(monkeypatch, tmp_path):
    # O sufixo em maiúsculas força a busca alternativa em sistemas sensíveis a maiúsculas.
    title = "100% Love [Official Video]"
    output_dir = tmp_path / "100% mídia"
    expected = output_dir / f"{title}.MP3"
    real_extractor = youtube_service.YoutubeDL

    class Extractor:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def download(self, urls):
            with real_extractor({"outtmpl": self.options["outtmpl"], "quiet": True}) as extractor:
                filename = Path(extractor.prepare_filename({"ext": "MP3"}))
            assert filename == expected
            filename.write_bytes(b"audio")

    monkeypatch.setattr(youtube_service.shutil, "which", lambda name: "ffmpeg")
    monkeypatch.setattr(youtube_service, "YoutubeDL", Extractor)

    assert Path(youtube_service.YouTubeService().download_media(
        "https://example.com/media", title, output_dir,
    )) == expected


@pytest.mark.parametrize("fail_second", [False, True])
def test_same_title_downloads_are_isolated(monkeypatch, tmp_path, fail_second):
    class Service:
        def get_info(self, url, **kwargs):
            return {"title": "Mesmo título"}

        def download_media(self, url, title, output_dir, *args, **kwargs):
            output_dir.mkdir(parents=True, exist_ok=True)
            path = output_dir / f"{title}.mp3"
            path.write_bytes(url.encode())
            if fail_second and url.endswith("/second"):
                raise RuntimeError("Falha simulada")
            return str(path)

    manager = JobManager()
    monkeypatch.setattr(manager, "youtube", Service())
    database = tmp_path / "history.sqlite"
    first_url = "https://example.com/first"
    second_url = "https://example.com/second"
    try:
        first = manager.submit_download(first_url, "Primeiro", tmp_path, database)
        second = manager.submit_download(second_url, "Segundo", tmp_path, database)
    finally:
        manager.executor.shutdown()

    first_path = Path(manager.get(first["id"])["file"])
    assert first_path.read_bytes() == first_url.encode()
    assert first_path.parent.name == first["id"]
    second_job = manager.get(second["id"])
    if fail_second:
        assert second_job["status"] == "failed"
        assert not first_path.parent.with_name(second["id"]).exists()
    else:
        second_path = Path(second_job["file"])
        assert second_path.parent.name == second["id"]
        assert second_path.read_bytes() == second_url.encode()
    history = HistoryRepository(database).list()
    assert len(history) == (1 if fail_second else 2)
    assert all(item["file_exists"] for item in history)
