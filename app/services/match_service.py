"""Correspondência Spotify -> YouTube com identidade musical obrigatória."""
import json
import re
import unicodedata
from pathlib import Path
from app.services.youtube_service import YouTubeService

STOP = {"official", "audio", "video", "lyrics", "lyric", "ao", "vivo", "live", "topic", "oficial", "hd", "4k"}

class MatchService:
    """Pesquisa vários candidatos internamente, mas devolve apenas correspondências confiáveis."""
    def __init__(self, storage_dir):
        self.youtube = YouTubeService()
        self.cache_path = Path(storage_dir) / "match_cache.json"
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)

    def _load_cache(self):
        try:
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_cache(self, cache):
        temp = self.cache_path.with_suffix(".tmp")
        temp.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(self.cache_path)

    @staticmethod
    def normalize(text):
        """Normaliza texto para comparação tolerante a acentos e pontuação."""
        raw = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
        return [w for w in re.sub(r"[^a-z0-9 ]", " ", raw).split() if w and w not in STOP]

    def _artist_match(self, artists, candidate):
        """Exige evidência forte do artista do Spotify no título/canal do candidato."""
        if not artists:
            return False, 0.0
        hay = set(self.normalize(f"{candidate.get('title','')} {candidate.get('channel','')}"))
        best = 0.0
        for artist in artists:
            tokens = set(self.normalize(artist))
            if not tokens:
                continue
            ratio = len(tokens & hay) / len(tokens)
            best = max(best, ratio)
        return best >= 0.75, best

    def score(self, track, candidate):
        """Pontua título, artista e duração; artista incompatível elimina o resultado."""
        title_tokens = set(self.normalize(track.get("title", "")))
        got = set(self.normalize(candidate.get("title", "")))
        title_score = len(title_tokens & got) / max(1, len(title_tokens))
        artist_ok, artist_score = self._artist_match(track.get("artists") or [], candidate)
        if not artist_ok or title_score < 0.70:
            return None
        score = title_score * 0.58 + artist_score * 0.37
        wanted_ms, duration = track.get("duration_ms"), candidate.get("duration")
        if wanted_ms and duration:
            diff = abs((wanted_ms / 1000) - float(duration))
            if diff <= 5:
                score += 0.05
            elif diff > 25:
                score -= 0.10
        if "topic" in (candidate.get("channel") or "").lower():
            score += 0.02
        return round(max(0.0, min(score, 1.0)), 3)

    def candidates(self, track, limit=1, cookie_browser=None):
        """Retorna somente a melhor correspondência do mesmo artista; nunca mistura homônimos."""
        if not (track.get("artists") or []):
            # Falhar fechado é melhor do que oferecer música de artista diferente.
            return []
        spotify_id = track.get("spotify_id")
        cache = self._load_cache()
        cached = cache.get(spotify_id) if spotify_id else None
        query = " ".join([track.get("title", ""), *(track.get("artists") or [])]).strip()
        candidates, seen = [], set()
        if cached and cached.get("url"):
            try:
                info = self.youtube.get_info(cached["url"], cookie_browser)
                score = self.score(track, info)
                if score is not None:
                    candidates.append({**info, "cached": True, "score": score})
                    seen.add(info["url"])
            except Exception:
                pass
        for suffix in ("official audio", "topic", "audio oficial", "ao vivo", ""):
            for item in self.youtube.search(f"{query} {suffix}".strip(), limit=8, cookie_browser=cookie_browser):
                if item.get("url") in seen:
                    continue
                seen.add(item.get("url"))
                score = self.score(track, item)
                if score is None or score < 0.72:
                    continue
                item.update(score=score, cached=False)
                candidates.append(item)
        candidates.sort(key=lambda c: (c.get("cached", False), c.get("score", 0)), reverse=True)
        return candidates[:max(1, int(limit))]

    def remember(self, spotify_id, url, title):
        if not spotify_id or not url:
            return
        cache = self._load_cache()
        cache[spotify_id] = {"url": url, "title": title}
        self._save_cache(cache)
