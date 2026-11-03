"""Fábrica Flask: configura armazenamento e registra as rotas da aplicação."""
import os
from pathlib import Path
from flask import Flask, render_template, jsonify, request, Response
import hmac
import time
from urllib.parse import urlsplit
from threading import BoundedSemaphore
from app.routes.api import bp as api_bp
from app.advertising import bp as ads_bp, ad_for_slot


def create_app(test_config=None):
    """Cria a aplicação e permite sobrescrever configurações durante testes."""
    app = Flask(__name__)
    cloud = os.environ.get("GROOVECATCH_CLOUD") == "1"
    # Em ambiente público, credenciais são obrigatórias e não devem ser versionadas.
    if cloud and (not os.environ.get("GROOVECATCH_ACCESS_PASSWORD") or not os.environ.get("GROOVECATCH_SECRET_KEY")):
        raise RuntimeError("Configure GROOVECATCH_ACCESS_PASSWORD e GROOVECATCH_SECRET_KEY no Render.")
    processing_slots = BoundedSemaphore(1)
    root = Path(__file__).resolve().parent.parent
    app.config.update(
        SECRET_KEY=os.environ.get("GROOVECATCH_SECRET_KEY", "local-development-only-change-me"),
        STORAGE_DIR=os.environ.get("GROOVECATCH_STORAGE", str(root / "storage")),
        DATABASE_PATH=os.environ.get("GROOVECATCH_DB", str(root / "instance" / "groovecatch.sqlite3")),
        ADS_DB_PATH=os.environ.get("GROOVECATCH_ADS_DB", str(root / "instance" / "advertising.sqlite3")),
        SESSION_COOKIE_HTTPONLY=True,
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
        """Protege o piloto por senha e limita uma operação FFmpeg simultânea."""
        if not cloud:
            return None
        if request.path == "/health":
            return None
        credentials = request.authorization
        valid = bool(credentials and
            hmac.compare_digest(credentials.username or "", os.environ.get("GROOVECATCH_ACCESS_USER", "admin")) and
            hmac.compare_digest(credentials.password or "", os.environ["GROOVECATCH_ACCESS_PASSWORD"]))
        if not valid:
            return Response("Acesso restrito ao piloto GrooveCatch.", 401,
                            {"WWW-Authenticate": 'Basic realm="GrooveCatch Pilot"'})
        if request.method == "POST" and request.path.startswith("/api/tools/"):
            if not processing_slots.acquire(blocking=False):
                return jsonify({"error": "Já existe um processamento ativo. Tente novamente em instantes."}), 429
            # O slot só é liberado quando a resposta é concluída pelo Flask.
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

    @app.get("/")
    def index():
        """Entrega a interface principal."""
        return render_template("index.html", cloud_mode=cloud, sponsored_items=sponsored_items(), ad_top=ad_for_slot("topo"), ad_content=ad_for_slot("conteudo"), ad_footer=ad_for_slot("rodape"))

    return app
