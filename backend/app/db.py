"""Persistencia de jobs en SQLite (stdlib, sin dependencias extra).

Mantiene el historial de ejecuciones entre reinicios del backend. Los objetos
``Job`` siguen viviendo en memoria como cache de trabajo; esta capa solo hace
write-through a disco y rehidrata el estado al arrancar.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .main import Job

_db_lock = threading.Lock()
_DB_PATH: Path | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id          TEXT PRIMARY KEY,
    script      TEXT NOT NULL,
    args        TEXT NOT NULL,
    command     TEXT NOT NULL,
    status      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    started_at  TEXT,
    ended_at    TEXT,
    return_code INTEGER,
    log_path    TEXT NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    assert _DB_PATH is not None, "db.init() no fue llamado"
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init(db_path: Path) -> None:
    """Configura la ruta de la base de datos y crea el esquema si falta."""
    global _DB_PATH
    _DB_PATH = db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _db_lock, _connect() as conn:
        conn.executescript(SCHEMA)


def save_job(job: "Job") -> None:
    """Inserta o actualiza un job (idempotente por id)."""
    with _db_lock, _connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs (id, script, args, command, status, created_at,
                              started_at, ended_at, return_code, log_path)
            VALUES (:id, :script, :args, :command, :status, :created_at,
                    :started_at, :ended_at, :return_code, :log_path)
            ON CONFLICT(id) DO UPDATE SET
                status      = excluded.status,
                started_at  = excluded.started_at,
                ended_at    = excluded.ended_at,
                return_code = excluded.return_code
            """,
            {
                "id": job.id,
                "script": job.script,
                "args": json.dumps(job.args),
                "command": json.dumps(job.command),
                "status": job.status,
                "created_at": job.created_at,
                "started_at": job.started_at,
                "ended_at": job.ended_at,
                "return_code": job.return_code,
                "log_path": job.log_path,
            },
        )


def load_jobs(job_factory) -> dict[str, "Job"]:
    """Rehidrata todos los jobs guardados.

    ``job_factory`` es el constructor ``Job`` (se inyecta para evitar el import
    circular con ``main``). Los jobs que quedaron como ``running``/``queued`` al
    cerrar el backend se marcan como ``failed`` porque su proceso ya no existe.
    """
    result: dict[str, "Job"] = {}
    with _db_lock, _connect() as conn:
        rows = conn.execute("SELECT * FROM jobs").fetchall()

    stale_ids: list[str] = []
    for row in rows:
        status = row["status"]
        if status in {"queued", "running"}:
            status = "failed"
            stale_ids.append(row["id"])
        result[row["id"]] = job_factory(
            id=row["id"],
            script=row["script"],
            args=json.loads(row["args"]),
            command=json.loads(row["command"]),
            status=status,
            created_at=row["created_at"],
            started_at=row["started_at"],
            ended_at=row["ended_at"],
            return_code=row["return_code"],
            log_path=row["log_path"],
        )

    if stale_ids:
        with _db_lock, _connect() as conn:
            conn.executemany(
                "UPDATE jobs SET status = 'failed' WHERE id = ?",
                [(job_id,) for job_id in stale_ids],
            )

    return result
