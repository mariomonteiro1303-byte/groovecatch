"""Catálogo de rádios com providers substituíveis.

Radio Garden é usado quando seus endpoints públicos não documentados respondem.
Radio Browser é o fallback aberto/documentado para busca e proximidade.
Nenhum provider recebe a localização sem uma ação explícita do usuário no navegador.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass

UA = "GrooveCatch/1.6.3 (+local multimedia app)"


def _json(url: str, timeout: int = 8):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _distance_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2-lat1); dl = math.radians(lon2-lon1)
    a = math.sin(dphi/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


@dataclass
class Station:
    id: str
    name: str
    stream_url: str
    city: str = ""
    state: str = ""
    country: str = ""
    tags: str = ""
    favicon: str = ""
    provider: str = ""
    distance_km: float | None = None

    def as_dict(self):
        return self.__dict__.copy()


class RadioGardenProvider:
    """Adapter isolado para a API interna/não oficial do Radio Garden."""
    base = "https://radio.garden/api"

    def search(self, query: str, limit: int = 24):
        # Endpoint conhecido por clientes comunitários. Se mudar, o serviço cai no fallback.
        data = _json(f"{self.base}/ara/content/search?q={urllib.parse.quote(query)}")
        items = (data.get("data") or {}).get("list") or []
        out = []
        for item in items:
            channel = item.get("channel") or item.get("page") or item
            cid = channel.get("id") or item.get("id")
            title = channel.get("title") or item.get("title")
            if not cid or not title: continue
            out.append(Station(str(cid), title,
                f"{self.base}/ara/content/listen/{cid}/channel.mp3",
                city=item.get("subtitle") or "", provider="Radio Garden").as_dict())
            if len(out) >= limit: break
        return out


class RadioBrowserProvider:
    """Provider aberto. Faz busca por nome, cidade, estado, país e gênero/tag."""
    servers = ("https://de1.api.radio-browser.info", "https://fi1.api.radio-browser.info")

    def _request(self, path):
        last = None
        for server in self.servers:
            try: return _json(server + path)
            except Exception as exc: last = exc
        raise RuntimeError(f"Catálogo de rádios indisponível: {last}")

    @staticmethod
    def _station(x, distance=None):
        return Station(
            id=x.get("stationuuid") or "", name=x.get("name") or "Rádio",
            stream_url=x.get("url_resolved") or x.get("url") or "",
            city=x.get("city") or "", state=x.get("state") or "", country=x.get("country") or "",
            tags=x.get("tags") or "", favicon=x.get("favicon") or "", provider="Radio Browser",
            distance_km=round(distance, 1) if distance is not None else None,
        ).as_dict()

    def _field_search(self, field, query, limit=24):
        qs = urllib.parse.urlencode({field: query, "limit": limit, "hidebroken": "true", "order": "votes", "reverse": "true"})
        return self._request("/json/stations/search?" + qs)

    @staticmethod
    def _normalized(value):
        """Normaliza acentos e pontuação para comparar os campos do catálogo."""
        value = unicodedata.normalize("NFKD", str(value or "").casefold())
        return " ".join(re.findall(r"[a-z0-9]+", "".join(c for c in value if not unicodedata.combining(c))))

    @classmethod
    def _relevance(cls, station, query, field):
        """Descarta respostas que não correspondem ao campo solicitado.

        A API pode retornar resultados aproximados ou genéricos; jamais
        exibimos essas respostas como se fossem rádios da cidade pesquisada.
        """
        q = cls._normalized(query)
        val = cls._normalized(station.get(field))
        if not q or not val:
            return 0
        if q == val:
            return 100
        if q in val:
            return 70
        # Tokens separados permitem 'Fortaleza CE' somente se todos constarem
        # no campo. Buscas compostas entre campos ficam para uma futura etapa.
        if len(q.split()) > 1 and all(t in val.split() for t in q.split()):
            return 55
        return 0

    def search(self, query, limit=24, field="auto"):
        """Busca validada localmente, sem fallback para emissoras irrelevantes."""
        fields = ("name", "city", "state", "country", "tag")
        if field != "auto" and field not in fields:
            raise ValueError("Filtro de rádio inválido.")
        requested = fields if field == "auto" else (field,)
        matches = {}
        succeeded = 0
        errors = []
        for current in requested:
            try:
                # Coleta um pouco mais para não perder resultados após filtrar.
                rows = self._field_search(current, query, min(limit * 3, 100))
                succeeded += 1
            except Exception as exc:
                errors.append(str(exc))
                continue
            for station in rows:
                score = self._relevance(station, query, current)
                sid = station.get("stationuuid") or station.get("url_resolved") or station.get("url")
                if not score or not sid or not (station.get("url_resolved") or station.get("url")):
                    continue
                # Em modo automático, prioriza cidade/estado/país quando houver
                # correspondência geográfica, mas mantém nome e gênero válidos.
                geographic = current in ("city", "state", "country")
                rank = (score + (15 if geographic else 0), int(station.get("votes") or 0))
                if sid not in matches or rank > matches[sid][0]:
                    matches[sid] = (rank, station)
        if not succeeded:
            raise RuntimeError("Não foi possível consultar o catálogo de rádios. " + (errors[0] if errors else ""))
        ranked = sorted(matches.values(), key=lambda row: row[0], reverse=True)
        return [self._station(station) for _, station in ranked[:limit]]

    def nearby(self, lat, lon, limit=24, radius_km=120):
        qs = urllib.parse.urlencode({"geo_lat": lat, "geo_long": lon, "geo_distance": int(radius_km*1000),
                                    "limit": max(limit*3, 50), "hidebroken": "true"})
        rows = self._request("/json/stations/search?" + qs)
        ranked = []
        for x in rows:
            try: d = _distance_km(float(lat), float(lon), float(x["geo_lat"]), float(x["geo_long"]))
            except Exception: continue
            ranked.append((d, x))
        ranked.sort(key=lambda z: z[0])
        return [self._station(x, d) for d, x in ranked[:limit]]


class RadioService:
    def __init__(self):
        self.garden = RadioGardenProvider(); self.browser = RadioBrowserProvider()

    def search(self, query, limit=24, field="auto"):
        # Não utilizamos Radio Garden como fallback para buscas geográficas:
        # seus resultados não fornecem campos estruturados confiáveis para
        # validar cidade/estado/país. A busca principal é o Radio Browser.
        found = self.browser.search(query, limit, field)
        return {"items": found, "provider": "Radio Browser", "filter": field}

    def nearby(self, lat, lon, limit=24):
        # Radio Garden não documenta um contrato estável para geo. O fallback documentado
        # é usado para proximidade e mantém a arquitetura pronta para trocar o provider.
        return {"items": self.browser.nearby(lat, lon, limit), "provider": "Radio Browser"}


def read_icy_now_playing(stream_url: str, timeout: int = 7):
    """Tenta ler StreamTitle de um stream ICY sem gravar o áudio.

    Retorna None quando a emissora não publica metadados. Limita a leitura a
    poucos blocos para não manter uma conexão de rádio aberta no servidor.
    """
    import ipaddress, socket
    parsed = urllib.parse.urlparse(stream_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    # Evita que a rota seja usada para consultar serviços locais/privados.
    try:
        for info in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return None
    except Exception:
        return None
    req = urllib.request.Request(stream_url, headers={"User-Agent": UA, "Icy-MetaData": "1", "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            metaint = r.headers.get("icy-metaint") or r.headers.get("Icy-MetaInt")
            if not metaint: return None
            metaint = int(metaint)
            if metaint <= 0 or metaint > 2_000_000: return None
            for _ in range(3):
                audio = r.read(metaint)
                if len(audio) < metaint: return None
                size = r.read(1)
                if not size: return None
                n = size[0] * 16
                meta = r.read(n) if n else b""
                text = meta.decode("utf-8", "replace").strip("\x00")
                if "StreamTitle='" in text:
                    title = text.split("StreamTitle='", 1)[1].split("';", 1)[0].strip()
                    if title: return title[:300]
    except Exception:
        return None
    return None
