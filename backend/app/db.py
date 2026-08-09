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
CREATE TABLE IF NOT EXISTS clips (
    id              TEXT PRIMARY KEY,
    transcript_path TEXT NOT NULL,
    video_path      TEXT,
    start           REAL NOT NULL,
    end             REAL NOT NULL,
    title           TEXT,
    reason          TEXT,
    score           INTEGER,
    transcript      TEXT,
    created_at      TEXT,
    channel_id      INTEGER,
    focus           TEXT DEFAULT 'center',
    zoom            REAL DEFAULT 1.0,
    top_ratio       REAL DEFAULT 0.7,
    subtitles       INTEGER DEFAULT 1,
    rendered_path   TEXT DEFAULT '',
    youtube_url     TEXT DEFAULT '',
    seo_title       TEXT DEFAULT '',
    seo_description TEXT DEFAULT '',
    seo_tags        TEXT DEFAULT '',
    overlay_text    TEXT DEFAULT '',
    youtube_privacy TEXT DEFAULT '',
    endcard_percent INTEGER DEFAULT 50,
    submitted       INTEGER DEFAULT 0,
    uploaded_at     TEXT DEFAULT '',
    blur_persons    TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_clips_transcript ON clips(transcript_path);
CREATE TABLE IF NOT EXISTS channels (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT NOT NULL,
    language       TEXT DEFAULT 'es',
    seo_rules      TEXT DEFAULT '',
    youtube_linked INTEGER DEFAULT 0,
    youtube_name   TEXT DEFAULT '',
    created_at     TEXT
);
CREATE TABLE IF NOT EXISTS campaigns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id      INTEGER,
    name            TEXT,
    source_url      TEXT,
    campaign_url    TEXT DEFAULT '',
    transcript_path TEXT DEFAULT '',
    video_path      TEXT DEFAULT '',
    status          TEXT DEFAULT 'preparing',
    created_at      TEXT,
    brief_url       TEXT DEFAULT '',
    rules_json      TEXT DEFAULT ''
);
"""

CAMPAIGN_MIGRATIONS = [
    "ALTER TABLE campaigns ADD COLUMN brief_url TEXT DEFAULT ''",
    "ALTER TABLE campaigns ADD COLUMN rules_json TEXT DEFAULT ''",
]


def _connect() -> sqlite3.Connection:
    assert _DB_PATH is not None, "db.init() no fue llamado"
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


CLIP_MIGRATIONS = [
    "ALTER TABLE clips ADD COLUMN channel_id INTEGER",
    "ALTER TABLE clips ADD COLUMN focus TEXT DEFAULT 'center'",
    "ALTER TABLE clips ADD COLUMN zoom REAL DEFAULT 1.0",
    "ALTER TABLE clips ADD COLUMN top_ratio REAL DEFAULT 0.7",
    "ALTER TABLE clips ADD COLUMN subtitles INTEGER DEFAULT 1",
    "ALTER TABLE clips ADD COLUMN rendered_path TEXT DEFAULT ''",
    "ALTER TABLE clips ADD COLUMN youtube_url TEXT DEFAULT ''",
    "ALTER TABLE clips ADD COLUMN seo_title TEXT DEFAULT ''",
    "ALTER TABLE clips ADD COLUMN seo_description TEXT DEFAULT ''",
    "ALTER TABLE clips ADD COLUMN seo_tags TEXT DEFAULT ''",
    "ALTER TABLE clips ADD COLUMN overlay_text TEXT DEFAULT ''",
    "ALTER TABLE clips ADD COLUMN youtube_privacy TEXT DEFAULT ''",
    "ALTER TABLE clips ADD COLUMN endcard_percent INTEGER DEFAULT 0",
    "ALTER TABLE clips ADD COLUMN submitted INTEGER DEFAULT 0",
    "ALTER TABLE clips ADD COLUMN uploaded_at TEXT DEFAULT ''",
    "ALTER TABLE clips ADD COLUMN blur_persons TEXT DEFAULT ''",
]


def init(db_path: Path) -> None:
    """Configura la ruta de la base de datos y crea el esquema si falta."""
    global _DB_PATH
    _DB_PATH = db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _db_lock, _connect() as conn:
        conn.executescript(SCHEMA)
        # Migraciones para BD antiguas: anade columnas nuevas si faltan.
        for statement in CLIP_MIGRATIONS + CAMPAIGN_MIGRATIONS:
            try:
                conn.execute(statement)
            except sqlite3.OperationalError:
                pass  # la columna ya existe


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


def _clip_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "transcriptPath": row["transcript_path"],
        "videoPath": row["video_path"],
        "start": row["start"],
        "end": row["end"],
        "duration": round(row["end"] - row["start"], 2),
        "title": row["title"],
        "reason": row["reason"],
        "score": row["score"],
        "transcript": row["transcript"],
        "channelId": row["channel_id"],
        "focus": row["focus"] or "center",
        "zoom": row["zoom"] if row["zoom"] is not None else 1.0,
        "topRatio": row["top_ratio"] if row["top_ratio"] is not None else 0.7,
        "subtitles": bool(row["subtitles"]),
        "renderedPath": row["rendered_path"] or "",
        "youtubeUrl": row["youtube_url"] or "",
        "seoTitle": row["seo_title"] or "",
        "seoDescription": row["seo_description"] or "",
        "seoTags": row["seo_tags"] or "",
        "overlayText": row["overlay_text"] or "",
        "youtubePrivacy": (row["youtube_privacy"] if "youtube_privacy" in row.keys() else "") or "",
        "endcardPercent": (row["endcard_percent"] if "endcard_percent" in row.keys() else 0) or 0,
        "submitted": bool(row["submitted"]) if "submitted" in row.keys() else False,
        "uploadedAt": (row["uploaded_at"] if "uploaded_at" in row.keys() else "") or "",
        "blurPersons": (row["blur_persons"] if "blur_persons" in row.keys() else "") or "",
    }


def replace_clips(transcript_path: str, video_path: str | None, channel_id: int | None,
                  clips: list[dict], created_at: str) -> None:
    """Reemplaza los clips DETECTADOS (no renderizados ni subidos) de una
    transcripcion. Los que ya tienen render o youtube se conservan."""
    with _db_lock, _connect() as conn:
        conn.execute(
            "DELETE FROM clips WHERE transcript_path = ? AND rendered_path = '' AND youtube_url = ''",
            (transcript_path,),
        )
        conn.executemany(
            """
            INSERT INTO clips (id, transcript_path, video_path, channel_id, start, end,
                               title, reason, score, transcript, created_at, endcard_percent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    clip["id"],
                    transcript_path,
                    video_path,
                    channel_id,
                    clip["start"],
                    clip["end"],
                    clip.get("title", ""),
                    clip.get("reason", ""),
                    clip.get("score", 0),
                    clip.get("transcript", ""),
                    created_at,
                    # Cierre al 50% por defecto: el primer render ya sale como short con
                    # cierre; si no gusta, el usuario elige otro fotograma y re-renderiza.
                    clip.get("endcardPercent", 50),
                )
                for clip in clips
            ],
        )


def load_clips(transcript_path: str) -> list[dict]:
    """Devuelve los clips guardados de una transcripcion, mayor score primero."""
    with _db_lock, _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM clips WHERE transcript_path = ? ORDER BY score DESC",
            (transcript_path,),
        ).fetchall()
    return [_clip_to_dict(row) for row in rows]


def get_clip(clip_id: str) -> dict | None:
    with _db_lock, _connect() as conn:
        row = conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
    return _clip_to_dict(row) if row else None


def update_clip(clip_id: str, fields: dict) -> dict | None:
    allowed = {"focus", "zoom", "top_ratio", "subtitles", "rendered_path", "youtube_url", "channel_id",
               "seo_title", "seo_description", "seo_tags", "overlay_text", "youtube_privacy", "start", "end",
               "endcard_percent", "submitted", "uploaded_at", "blur_persons"}
    updates = {key: value for key, value in fields.items() if key in allowed}
    if updates:
        assignments = ", ".join(f"{key} = ?" for key in updates)
        with _db_lock, _connect() as conn:
            conn.execute(
                f"UPDATE clips SET {assignments} WHERE id = ?",
                (*updates.values(), clip_id),
            )
    return get_clip(clip_id)


def _channel_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "language": row["language"],
        "seoRules": row["seo_rules"],
        "youtubeLinked": bool(row["youtube_linked"]),
        "youtubeName": row["youtube_name"],
        "createdAt": row["created_at"],
    }


def create_channel(name: str, language: str, seo_rules: str, created_at: str) -> dict:
    with _db_lock, _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO channels (name, language, seo_rules, created_at) VALUES (?, ?, ?, ?)",
            (name, language, seo_rules, created_at),
        )
        channel_id = cursor.lastrowid
        row = conn.execute("SELECT * FROM channels WHERE id = ?", (channel_id,)).fetchone()
    return _channel_to_dict(row)


def list_channels() -> list[dict]:
    with _db_lock, _connect() as conn:
        rows = conn.execute("SELECT * FROM channels ORDER BY id").fetchall()
    return [_channel_to_dict(row) for row in rows]


def get_channel(channel_id: int) -> dict | None:
    with _db_lock, _connect() as conn:
        row = conn.execute("SELECT * FROM channels WHERE id = ?", (channel_id,)).fetchone()
    return _channel_to_dict(row) if row else None


def update_channel(channel_id: int, fields: dict) -> dict | None:
    allowed = {"name", "language", "seo_rules", "youtube_linked", "youtube_name"}
    updates = {key: value for key, value in fields.items() if key in allowed}
    if updates:
        assignments = ", ".join(f"{key} = ?" for key in updates)
        with _db_lock, _connect() as conn:
            conn.execute(
                f"UPDATE channels SET {assignments} WHERE id = ?",
                (*updates.values(), channel_id),
            )
    return get_channel(channel_id)


def delete_channel(channel_id: int) -> None:
    with _db_lock, _connect() as conn:
        conn.execute("DELETE FROM channels WHERE id = ?", (channel_id,))


def _campaign_to_dict(row: sqlite3.Row) -> dict:
    raw_rules = row["rules_json"] if "rules_json" in row.keys() else ""
    try:
        rules = json.loads(raw_rules) if raw_rules else {}
    except Exception:
        rules = {}
    return {
        "id": row["id"],
        "channelId": row["channel_id"],
        "name": row["name"],
        "sourceUrl": row["source_url"],
        "campaignUrl": row["campaign_url"] or "",
        "transcriptPath": row["transcript_path"] or "",
        "videoPath": row["video_path"] or "",
        "status": row["status"] or "preparing",
        "createdAt": row["created_at"],
        "briefUrl": (row["brief_url"] if "brief_url" in row.keys() else "") or "",
        "rules": rules,
    }


def _clip_stats(conn: sqlite3.Connection, transcript_path: str) -> dict:
    """Contadores de clips de una campaña (por su transcript_path)."""
    if not transcript_path:
        return {"total": 0, "rendered": 0, "uploaded": 0, "submitted": 0}
    row = conn.execute(
        """SELECT COUNT(*) AS total,
                  SUM(CASE WHEN rendered_path != '' THEN 1 ELSE 0 END) AS rendered,
                  SUM(CASE WHEN youtube_url != '' THEN 1 ELSE 0 END) AS uploaded,
                  SUM(CASE WHEN submitted = 1 THEN 1 ELSE 0 END) AS submitted
           FROM clips WHERE transcript_path = ?""",
        (transcript_path,),
    ).fetchone()
    return {
        "total": row["total"] or 0,
        "rendered": row["rendered"] or 0,
        "uploaded": row["uploaded"] or 0,
        "submitted": row["submitted"] or 0,
    }


def create_campaign(channel_id: int, name: str, source_url: str, campaign_url: str, created_at: str) -> dict:
    with _db_lock, _connect() as conn:
        cursor = conn.execute(
            "INSERT INTO campaigns (channel_id, name, source_url, campaign_url, created_at) VALUES (?, ?, ?, ?, ?)",
            (channel_id, name, source_url, campaign_url, created_at),
        )
        row = conn.execute("SELECT * FROM campaigns WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _campaign_to_dict(row)


def list_campaigns(channel_id: int | None = None) -> list[dict]:
    with _db_lock, _connect() as conn:
        if channel_id is not None:
            rows = conn.execute(
                "SELECT * FROM campaigns WHERE channel_id = ? ORDER BY id DESC", (channel_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM campaigns ORDER BY id DESC").fetchall()
        result = []
        for row in rows:
            camp = _campaign_to_dict(row)
            camp["clipStats"] = _clip_stats(conn, camp["transcriptPath"])
            result.append(camp)
    return result


def get_campaign(campaign_id: int) -> dict | None:
    with _db_lock, _connect() as conn:
        row = conn.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
        if not row:
            return None
        camp = _campaign_to_dict(row)
        camp["clipStats"] = _clip_stats(conn, camp["transcriptPath"])
    return camp


def get_campaign_by_transcript(transcript_path: str) -> dict | None:
    with _db_lock, _connect() as conn:
        row = conn.execute(
            "SELECT * FROM campaigns WHERE transcript_path = ? ORDER BY id DESC LIMIT 1",
            (transcript_path,),
        ).fetchone()
    return _campaign_to_dict(row) if row else None


def update_campaign(campaign_id: int, fields: dict) -> dict | None:
    allowed = {"name", "campaign_url", "transcript_path", "video_path", "status", "brief_url", "rules_json"}
    updates = {key: value for key, value in fields.items() if key in allowed}
    if updates:
        assignments = ", ".join(f"{key} = ?" for key in updates)
        with _db_lock, _connect() as conn:
            conn.execute(
                f"UPDATE campaigns SET {assignments} WHERE id = ?",
                (*updates.values(), campaign_id),
            )
    return get_campaign(campaign_id)


def delete_campaign(campaign_id: int) -> None:
    with _db_lock, _connect() as conn:
        conn.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))
