"""Ponto de entrada local do GrooveCatch Web."""
from app import create_app

app = create_app()

if __name__ == "__main__":
    # Servidor de desenvolvimento para uso local; não expor publicamente sem proteção.
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
