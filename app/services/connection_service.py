"""Mede conectividade externa sem executar um speedtest pesado."""
import time
import urllib.request


def connection_status():
    """Retorna latência aproximada até um endpoint HTTP externo leve.

    A velocidade real é medida pelos callbacks do yt-dlp durante downloads.
    """
    started = time.perf_counter()
    try:
        request = urllib.request.Request("https://www.google.com/generate_204", headers={"User-Agent": "GrooveCatch/1.6"})
        with urllib.request.urlopen(request, timeout=4) as response:
            response.read(1)
        latency = round((time.perf_counter() - started) * 1000)
        if latency < 80:
            quality = "Excelente"
        elif latency < 160:
            quality = "Boa"
        elif latency < 300:
            quality = "Regular"
        else:
            quality = "Instável"
        return {"online": True, "latency_ms": latency, "quality": quality}
    except Exception:
        return {"online": False, "latency_ms": None, "quality": "Sem conexão externa"}
