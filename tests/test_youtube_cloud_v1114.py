"""Regressões: classificação de URLs e tratamento conservador de limitações YouTube.

Os testes não fazem consultas externas nem realizam downloads.
"""
import pytest

from app.services.youtube_playlist_service import youtube_video_id, playlist_id, load_playlist
from app.services.input_resolver import InputResolver
from app.services.media_service import MediaService
from app.services.youtube_policy import (
    YtDlpLogger, YouTubeRateLimited, YouTubeRemoteError,
    check_youtube_cooldown, is_youtube_target, map_youtube_error,
    remaining_cooldown,
)

VIDEO = "Uec6DC3-ffU"


@pytest.mark.parametrize("url", [
    f"https://youtu.be/{VIDEO}?list=RDMM{VIDEO}",
    f"https://www.youtube.com/watch?v={VIDEO}&list=PLteste",
    f"https://www.youtube.com/shorts/{VIDEO}?feature=share",
    f"https://www.youtube.com/live/{VIDEO}",
])
def test_video_id_has_priority_over_playlist(url):
    assert youtube_video_id(url) == VIDEO


def test_playlist_only_url_is_not_a_video():
    assert youtube_video_id("https://www.youtube.com/playlist?list=PL123456") is None
    assert playlist_id("https://www.youtube.com/playlist?list=PL123456") == "PL123456"


def test_similar_domain_is_not_youtube():
    url = f"https://youtu.be.evil.example/{VIDEO}?list=PL123"
    assert youtube_video_id(url) is None
    assert playlist_id(url) is None


def test_video_with_mix_is_sent_to_media_inspector(monkeypatch, tmp_path):
    seen = []

    def fake_inspect(self, url, cookie_browser=None):
        seen.append(url)
        return {"title": "Teste", "platform": "YouTube"}

    monkeypatch.setattr(MediaService, "inspect", fake_inspect)
    result = InputResolver().resolve(f"https://youtu.be/{VIDEO}?list=RDMM{VIDEO}", tmp_path)
    assert result["kind"] == "media_url"
    assert seen == [f"https://www.youtube.com/watch?v={VIDEO}"]


def test_automatic_mix_playlist_shows_specific_error():
    with pytest.raises(ValueError, match="Mix automático"):
        load_playlist(f"https://www.youtube.com/playlist?list=RDMM{VIDEO}")


def test_429_triggers_cloud_cooldown(monkeypatch):
    import app.services.youtube_policy as policy
    monkeypatch.setenv("GROOVECATCH_CLOUD", "1")
    monkeypatch.setenv("GROOVECATCH_YOUTUBE_COOLDOWN_SECONDS", "60")
    monkeypatch.setattr(policy, "_BLOCKED_UNTIL", 0.0)
    logger = YtDlpLogger()
    logger.warning(f"[youtube] {VIDEO}: HTTP Error 429: Too Many Requests")
    mapped = map_youtube_error(RuntimeError("Failed to extract any player response"), logger,
                               f"https://youtu.be/{VIDEO}")
    assert isinstance(mapped, YouTubeRateLimited)
    assert remaining_cooldown() > 0
    with pytest.raises(YouTubeRateLimited):
        check_youtube_cooldown(f"https://www.youtube.com/watch?v={VIDEO}")
    # Não afetar SoundCloud nem outras plataformas.
    check_youtube_cooldown("https://soundcloud.com/test/track")
    other = YtDlpLogger(for_youtube=False)
    other.warning("HTTP Error 429: Too Many Requests")
    assert not other.saw_429


def test_403_is_friendly_without_claiming_login_is_required(monkeypatch):
    import app.services.youtube_policy as policy
    monkeypatch.setenv("GROOVECATCH_CLOUD", "0")
    monkeypatch.setattr(policy, "_BLOCKED_UNTIL", 0.0)
    logger = YtDlpLogger()
    logger.warning("[youtube] HTTP Error 403: Forbidden")
    error = map_youtube_error(RuntimeError("extractor failure"), logger, f"https://youtu.be/{VIDEO}")
    assert isinstance(error, YouTubeRemoteError)
    assert error.code == "youtube_access_denied"
    assert "yt-dlp" not in str(error)
    assert "autentic" not in str(error).lower()


def test_non_youtube_errors_unchanged():
    logger = YtDlpLogger()
    assert not is_youtube_target("https://soundcloud.com/a/b")
    assert map_youtube_error(RuntimeError("HTTP Error 429"), logger,
                             "https://soundcloud.com/a/b") is None


def test_media_inspect_maps_warnings_to_503_error(monkeypatch):
    """Integração real: a inspeção deve classificar um 429 visto pelo logger."""
    import app.services.youtube_policy as policy
    import app.services.media_service as media_module
    monkeypatch.setenv("GROOVECATCH_CLOUD", "1")
    monkeypatch.setattr(policy, "_BLOCKED_UNTIL", 0.0)

    class FakeExtractor:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, url, download=False):
            self.options["logger"].warning("[youtube] HTTP Error 429: Too Many Requests")
            raise RuntimeError("Failed to extract any player response")

    monkeypatch.setattr(media_module, "YoutubeDL", FakeExtractor)
    with pytest.raises(YouTubeRateLimited):
        MediaService().inspect(f"https://www.youtube.com/watch?v={VIDEO}")
    assert remaining_cooldown() > 0


def test_youtube_get_info_maps_forbidden(monkeypatch):
    """A classe YouTubeService aplica o mesmo tratamento seguro."""
    import app.services.youtube_policy as policy
    import app.services.youtube_service as youtube_module
    monkeypatch.setenv("GROOVECATCH_CLOUD", "0")
    monkeypatch.setattr(policy, "_BLOCKED_UNTIL", 0.0)

    class FakeExtractor:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def extract_info(self, url, download=False):
            self.options["logger"].warning("[youtube] HTTP Error 403: Forbidden")
            raise RuntimeError("Failed to extract any player response")

    monkeypatch.setattr(youtube_module, "YoutubeDL", FakeExtractor)
    with pytest.raises(YouTubeRemoteError) as failure:
        youtube_module.YouTubeService().get_info(f"https://youtu.be/{VIDEO}")
    assert failure.value.code == "youtube_access_denied"
