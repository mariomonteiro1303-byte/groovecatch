"""Histórico persistente SQLite, independente do processo Flask."""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class HistoryRepository:
    """Armazena downloads concluídos e permite listagem recente."""
    def __init__(self, database_path):
        self.database_path = str(database_path)
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, url TEXT NOT NULL,
                format TEXT NOT NULL, file TEXT NOT NULL, created_at TEXT NOT NULL)""")

    def _connect(self):
        """Abre conexão com timeout para reduzir falhas em acessos concorrentes."""
        db = sqlite3.connect(self.database_path, timeout=15)
        db.row_factory = sqlite3.Row
        return db

    def add(self, item):
        """Insere um registro de sucesso com data UTC ISO-8601."""
        with self._connect() as db:
            db.execute("INSERT INTO history(title,url,format,file,created_at) VALUES(?,?,?,?,?)",
                       (item.get("title", "Mídia"), item.get("url", ""), item.get("format", "mp3"),
                        item.get("file", ""), datetime.now(timezone.utc).isoformat()))

    def list(self, limit=100):
        """Devolve registros recentes, omitindo caminhos internos do servidor."""
        with self._connect() as db:
            rows = db.execute("SELECT title,url,format,file,created_at FROM history ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"title": r["title"], "url": r["url"], "format": r["format"],
                 "filename": Path(r["file"]).name, "file_exists": Path(r["file"]).is_file(),
                 "created_at": r["created_at"]} for r in rows]
