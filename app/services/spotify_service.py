"""Resolvedor de metadados Spotify sem Client ID/Secret para faixas, álbuns e playlists.

A estratégia usa somente páginas públicas do Spotify:
1. normaliza o link compartilhado;
2. consulta o oEmbed oficial para título/capa;
3. consulta /embed/track/<id>, que costuma trazer metadados estruturados no HTML;
4. usa a página pública normal apenas como fallback.

O Spotify é usado somente como referência de metadados e pré-visualização. O arquivo
final continua vindo da fonte de mídia selecionada pelo GrooveCatch.
"""
import html
import json
import re
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


class SpotifyService:
    """Obtém título, artista, duração, capa e prévia pública quando disponíveis."""

    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156 Safari/537.36"
    )

    def _get_text(self, url):
        """Lê uma URL pública seguindo redirecionamentos."""
        request = Request(url, headers={
            "User-Agent": self.USER_AGENT,
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        })
        with urlopen(request, timeout=15) as response:
            return response.read().decode("utf-8", errors="replace"), response.geturl()

    def _canonical_item(self, url):
        """Normaliza links track/album/playlist, inclusive /intl-XX e spotify.link."""
        text_url = (url or "").strip()
        parsed = urlparse(text_url)
        if parsed.netloc.lower().removeprefix("www.") == "spotify.link":
            _, text_url = self._get_text(text_url)
            parsed = urlparse(text_url)

        parts = [part for part in parsed.path.split("/") if part]
        try:
            item_type = next(kind for kind in ("track", "album", "playlist") if kind in parts)
            item_index = parts.index(item_type)
            item_id = parts[item_index + 1]
        except (StopIteration, ValueError, IndexError):
            raise ValueError("Este link Spotify não aponta para uma faixa, álbum ou playlist compatível.")
        if not re.fullmatch(r"[A-Za-z0-9]+", item_id or ""):
            raise ValueError("Não foi possível identificar o ID da faixa Spotify.")
        return f"https://open.spotify.com/{item_type}/{item_id}", item_type, item_id

    def _oembed(self, canonical_url):
        """Consulta o oEmbed público oficial do Spotify."""
        endpoint = "https://open.spotify.com/oembed?url=" + quote(canonical_url, safe="")
        raw, _ = self._get_text(endpoint)
        return json.loads(raw)

    @staticmethod
    def _walk_json(value):
        """Percorre recursivamente JSON desconhecido sem depender do layout do Spotify."""
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from SpotifyService._walk_json(child)
        elif isinstance(value, list):
            for child in value:
                yield from SpotifyService._walk_json(child)

    @staticmethod
    def _artist_names(value):
        """Converte diferentes formas de campo artists em uma lista de nomes."""
        names = []
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    name = item.get("name") or item.get("title")
                else:
                    name = item if isinstance(item, str) else None
                if name and str(name).strip() not in names:
                    names.append(str(name).strip())
        elif isinstance(value, dict):
            name = value.get("name") or value.get("title")
            if name:
                names.append(str(name).strip())
        elif isinstance(value, str) and value.strip():
            names.append(value.strip())
        return names

    def _extract_embed_metadata(self, item_id):
        """Extrai metadados do player público /embed/track sem usar OAuth."""
        embed_url = f"https://open.spotify.com/embed/track/{item_id}"
        try:
            page, _ = self._get_text(embed_url)
        except Exception:
            return {"embed_url": embed_url}

        # O player público normalmente inclui um ou mais blobs JSON. Em vez de
        # depender de um único nome de script, tentamos todos os scripts JSON.
        blobs = []
        for match in re.finditer(
            r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>',
            page, re.I | re.S,
        ):
            raw = html.unescape(match.group(1)).strip()
            try:
                blobs.append(json.loads(raw))
            except (ValueError, TypeError):
                continue

        # Compatibilidade com páginas que ainda usam __NEXT_DATA__.
        next_match = re.search(
            r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
            page, re.I | re.S,
        )
        if next_match:
            try:
                blobs.append(json.loads(html.unescape(next_match.group(1))))
            except (ValueError, TypeError):
                pass

        best = {}
        for blob in blobs:
            for obj in self._walk_json(blob):
                uri = str(obj.get("uri") or obj.get("spotifyUri") or obj.get("canonicalUri") or "")
                obj_id = str(obj.get("id") or obj.get("trackId") or obj.get("entityUniqueId") or "")
                is_target = item_id in uri or obj_id == item_id
                artists = self._artist_names(
                    obj.get("artists") or obj.get("artist") or obj.get("subtitle") or obj.get("creator")
                )
                name = obj.get("name") or obj.get("title") or obj.get("trackName")
                # Alguns objetos internos não repetem o ID. Um objeto com nome + artistas
                # ainda é um bom candidato em uma página de embed de uma única faixa.
                if (is_target or (name and artists)) and name:
                    candidate = {
                        "title": str(name).strip(),
                        "artists": artists,
                        "duration_ms": obj.get("duration_ms") or obj.get("durationMs") or obj.get("duration"),
                        "album": "",
                    }
                    album = obj.get("album")
                    if isinstance(album, dict):
                        candidate["album"] = str(album.get("name") or album.get("title") or "").strip()
                    elif isinstance(album, str):
                        candidate["album"] = album.strip()
                    if artists and (not best or is_target):
                        best = candidate
                        if is_target:
                            break
            if best.get("artists"):
                break

        # Preview público: quando presente, aparece como URL p.scdn.co no HTML.
        preview = ""
        preview_match = re.search(r'https://p\.scdn\.co/mp3-preview/[A-Za-z0-9_%?&=./:-]+', page)
        if preview_match:
            preview = html.unescape(preview_match.group(0)).replace("\\u0026", "&")

        best["preview_url"] = preview
        best["embed_url"] = embed_url
        return best

    def _page_metadata(self, canonical_url):
        """Obtém metatags da página pública como último fallback."""
        try:
            page, _ = self._get_text(canonical_url)
        except Exception:
            return {}

        def meta(name):
            patterns = [
                rf'<meta[^>]+property=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)',
                rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(name)}["\']',
                rf'<meta[^>]+name=["\']{re.escape(name)}["\'][^>]+content=["\']([^"\']+)',
                rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']{re.escape(name)}["\']',
            ]
            for pattern in patterns:
                match = re.search(pattern, page, re.I)
                if match:
                    return html.unescape(match.group(1)).strip()
            return ""

        return {"og_title": meta("og:title"), "description": meta("og:description") or meta("description")}

    @staticmethod
    def _artists_from_description(description):
        """Extrai artista de descrições simples sem confundir Song/Track com artista."""
        if not description:
            return []
        pieces = [piece.strip() for piece in description.split("·") if piece.strip()]
        generic = {"song", "single", "track", "música", "musica"}
        if len(pieces) >= 2 and pieces[1].lower() in generic:
            return [pieces[0]] if len(pieces[0]) <= 120 else []
        if len(pieces) >= 2 and pieces[0].lower() in generic:
            return [pieces[1]] if len(pieces[1]) <= 120 else []
        match = re.search(r"(?:by|por)\s+([^|•]+)", description, re.I)
        return [match.group(1).strip()] if match else []

    def _load_single_track(self, url):
        """Resolve uma faixa e retorna identidade musical para matching no YouTube."""
        canonical_url, item_type, item_id = self._canonical_item(url)
        if item_type != "track":
            raise ValueError("Esperado link de faixa Spotify.")
        errors = []
        oembed, embed, page = {}, {}, {}
        try:
            oembed = self._oembed(canonical_url)
        except Exception as exc:
            errors.append(f"oEmbed: {exc}")
        try:
            embed = self._extract_embed_metadata(item_id)
        except Exception as exc:
            errors.append(f"embed: {exc}")
        try:
            page = self._page_metadata(canonical_url)
        except Exception as exc:
            errors.append(f"página: {exc}")

        title = (embed.get("title") or oembed.get("title") or page.get("og_title") or "").strip()
        title = re.sub(r"\s*[|–-]\s*(song and lyrics by )?Spotify\s*$", "", title, flags=re.I).strip()
        artists = [a for a in (embed.get("artists") or []) if a]
        if not artists:
            artists = self._artists_from_description((page.get("description") or "").strip())

        if not title:
            detail = "; ".join(errors) if errors else "metadados públicos indisponíveis"
            raise RuntimeError(f"Não foi possível obter o título público desta faixa Spotify ({detail}).")

        duration_ms = embed.get("duration_ms")
        try:
            if duration_ms is not None:
                duration_ms = int(float(duration_ms))
                # Alguns blobs usam segundos, não milissegundos.
                if duration_ms and duration_ms < 10000:
                    duration_ms *= 1000
        except (TypeError, ValueError):
            duration_ms = None

        return [{
            "title": title,
            "artists": artists,
            "album": embed.get("album") or "",
            "duration_ms": duration_ms,
            "spotify_id": item_id,
            "search_query": " ".join([title, *artists]).strip(),
            "thumbnail": oembed.get("thumbnail_url"),
            "preview_url": embed.get("preview_url") or "",
            "spotify_embed_url": embed.get("embed_url") or f"https://open.spotify.com/embed/track/{item_id}",
            "spotify_url": canonical_url,
            "resolution_method": "Spotify Embed público + oEmbed",
            "metadata_complete": bool(title and artists),
        }]


    def _extract_collection(self, canonical_url, item_type, item_id):
        """Extrai faixas do player público de álbum/playlist sem OAuth.

        O HTML do embed não é uma API estável. Por isso percorremos os blobs JSON e
        aceitamos somente objetos que tenham identidade musical suficiente.
        """
        embed_url = f"https://open.spotify.com/embed/{item_type}/{item_id}"
        page, _ = self._get_text(embed_url)
        blobs = []
        for match in re.finditer(r'<script[^>]*type=["\']application/json["\'][^>]*>(.*?)</script>', page, re.I | re.S):
            try:
                blobs.append(json.loads(html.unescape(match.group(1)).strip()))
            except Exception:
                pass
        next_match = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', page, re.I | re.S)
        if next_match:
            try: blobs.append(json.loads(html.unescape(next_match.group(1))))
            except Exception: pass

        found = {}
        for blob in blobs:
            for obj in self._walk_json(blob):
                uri = str(obj.get("uri") or obj.get("spotifyUri") or obj.get("canonicalUri") or "")
                tid = str(obj.get("id") or obj.get("trackId") or obj.get("entityUniqueId") or "")
                if "spotify:track:" in uri:
                    tid = uri.rsplit(":", 1)[-1]
                if not re.fullmatch(r"[A-Za-z0-9]{10,}", tid or ""):
                    continue
                title = obj.get("name") or obj.get("title") or obj.get("trackName")
                artists = self._artist_names(obj.get("artists") or obj.get("artist") or obj.get("subtitle") or obj.get("creator"))
                if not title or not artists:
                    continue
                duration = obj.get("duration_ms") or obj.get("durationMs") or obj.get("duration")
                try:
                    duration = int(float(duration)) if duration is not None else None
                    if duration and duration < 10000: duration *= 1000
                except Exception: duration = None
                found.setdefault(tid, {
                    "title": str(title).strip(), "artists": artists, "album": "",
                    "duration_ms": duration, "spotify_id": tid,
                    "search_query": " ".join([str(title).strip(), *artists]).strip(),
                    "thumbnail": "", "preview_url": "",
                    "spotify_embed_url": f"https://open.spotify.com/embed/track/{tid}",
                    "spotify_url": f"https://open.spotify.com/track/{tid}",
                    "resolution_method": f"Spotify Embed público ({item_type})",
                    "metadata_complete": True,
                })
        if not found:
            raise RuntimeError(f"Não foi possível extrair as faixas públicas deste {item_type} Spotify.")
        return list(found.values()), embed_url

    def load(self, url):
        """Resolve o item Spotify sem pesquisar no YouTube. Coleções ficam leves na identificação."""
        canonical_url, item_type, item_id = self._canonical_item(url)
        if item_type == "track":
            tracks = self._load_single_track(canonical_url)
            return {"item_type": item_type, "item_id": item_id, "title": tracks[0].get("title") or "Faixa Spotify", "tracks": tracks}
        tracks, _ = self._extract_collection(canonical_url, item_type, item_id)
        # oEmbed é usado apenas para o nome/capa da coleção. A extração das faixas continua pelo Embed público.
        try:
            meta = self._oembed(canonical_url)
        except Exception:
            meta = {}
        title = (meta.get("title") or f"{item_type.title()} Spotify").strip()
        return {"item_type": item_type, "item_id": item_id, "title": title, "thumbnail": meta.get("thumbnail_url") or "", "tracks": tracks}

    def load_tracks(self, url):
        """Compatibilidade com chamadas antigas."""
        return self.load(url)["tracks"]
