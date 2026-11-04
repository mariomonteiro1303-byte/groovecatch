"""Fábrica Flask: configura armazenamento e registra as rotas da aplicação."""
import os
from pathlib import Path
from flask import Flask, render_template, jsonify, request, Response
import hmac
import time
from urllib.parse import urlsplit
from threading import BoundedSemaphore, Lock
from collections import defaultdict, deque
from app.routes.api import bp as api_bp
from app.advertising import bp as ads_bp, ad_for_slot


def create_app(test_config=None):
    """Cria a aplicação e permite sobrescrever configurações durante testes."""
    app = Flask(__name__)
    cloud = os.environ.get("GROOVECATCH_CLOUD") == "1"
    # Em nuvem, a chave de sessão deve ser fornecida pelo Render.
    if cloud and not os.environ.get("GROOVECATCH_SECRET_KEY"):
        raise RuntimeError("Configure GROOVECATCH_SECRET_KEY no Render.")
    processing_slots = BoundedSemaphore(1)
    # Limitação simples por IP, em memória, por instância (não é uma proteção distribuída).
    request_times = defaultdict(deque)
    rate_lock = Lock
    rate_lock = rate_lock()
    root = Path(__file__).resolve().parent.parent
    app.config.update(
        SECRET_KEY=os.environ.get("GROOVECATCH_SECRET_KEY", "local-development-only-change-me"),
        STORAGE_DIR=os.environ.get("GROOVECATCH_STORAGE", str(root / "storage")),
        DATABASE_PATH=os.environ.get("GROOVECATCH_DB", str(root / "instance" / "groovecatch.sqlite3")),
        ADS_DB_PATH=os.environ.get("GROOVECATCH_ADS_DB", str(root / "instance" / "advertising.sqlite3")),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=cloud,
        SESSION_COOKIE_SAMESITE="Lax",
        MAX_CONTENT_LENGTH=(101 if cloud else 501) * 1024 * 1024,  # Cloud: 100 MB; local: 500 MB
    )
    if test_config:
        app.config.update(test_config)
    Path(app.config["STORAGE_DIR"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["DATABASE_PATH"]).parent.mkdir(parents=True, exist_ok=True)
    app.config["CLOUD_MODE"] = cloud
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(ads_bp)

    @app.before_request
    def cloud_guard():
        """Site público; limita chamadas de API e processamento simultâneo.

        O IP usa remote_addr. Não confia em cabeçalhos X-Forwarded-For
        enviados pelo cliente, para evitar falsificação trivial.
        """
        if not cloud:
            return None
        if request.path == "/health":
            return None
        if request.path.startswith("/api/"):
            now = time.monotonic()
            ip = request.remote_addr or "unknown"
            with rate_lock:
                # Limita o crescimento do mapa em memória.
                if len(request_times) > 2000:
                    for key in list(request_times)[:500]:
                        if not request_times[key] or now - request_times[key][-1] > 120:
                            del request_times[key]
                hits = request_times[ip]
                while hits and now - hits[0] > 60:
                    hits.popleft()
                limit = 15 if request.method == "POST" else 90
                # POST e GET compartilham orçamento conservador.
                if len(hits) >= limit:
                    return jsonify({"error": "Limite temporário de solicitações. Aguarde um minuto."}), 429
                hits.append(now)
        if request.method == "POST" and request.path.startswith("/api/tools/"):
            if not processing_slots.acquire(blocking=False):
                return jsonify({"error": "Já existe um processamento ativo. Tente novamente em instantes."}), 429
            from flask import g
            g.cloud_processing_slot = True
        return None

    @app.teardown_request
    def release_cloud_slot(exc):
        from flask import g
        if getattr(g, "cloud_processing_slot", False):
            processing_slots.release()
            g.cloud_processing_slot = False

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "mode": "cloud" if cloud else "local"})


    @app.errorhandler(413)
    def request_too_large(error):
        """Devolve erro legível ao frontend quando upload ultrapassa o limite."""
        return jsonify({"error": "Arquivo excede o limite de upload configurado para esta edição."}), 413

    def sponsored_items():
        """Anúncios definidos por variáveis de ambiente, sem HTML de terceiros."""
        items = []
        for number in (1, 2, 3):
            prefix = f"GROOVECATCH_SPONSOR_{number}_"
            title = os.environ.get(prefix + "TITLE", "").strip()[:90]
            url = os.environ.get(prefix + "URL", "").strip()
            description = os.environ.get(prefix + "DESCRIPTION", "").strip()[:160]
            try:
                parts = urlsplit(url)
                safe = parts.scheme == "https" and bool(parts.hostname) and not parts.username and not parts.password
            except ValueError:
                safe = False
            if title and safe:
                items.append({"title": title, "url": url, "description": description})
        return items

    @app.context_processor
    def brand_context():
        return {"developer_name": os.environ.get("GROOVECATCH_DEVELOPER_NAME", "Equipe GrooveCatch").strip()[:90],
                "contact_email": os.environ.get("GROOVECATCH_CONTACT_EMAIL", "").strip()[:180]}

    @app.get("/sobre")
    def about():
        return render_template("institutional.html", page="sobre")

    @app.get("/privacidade")
    def privacy():
        return render_template("institutional.html", page="privacidade")

    @app.get("/termos")
    def terms():
        return render_template("institutional.html", page="termos")

    @app.get("/")
    def index():
        """Entrega a interface principal."""
        return render_template("index.html", cloud_mode=cloud, sponsored_items=sponsored_items(), ad_top=ad_for_slot("topo"), ad_content=ad_for_slot("conteudo"), ad_footer=ad_for_slot("rodape"))

    return app
