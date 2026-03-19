from __future__ import annotations

import os
import shlex
import subprocess
import sys
import threading
import uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .catalog import build_script_entry
from .services import VideoContentRequest

ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT_DIR / "backend" / "scripts"
LOGS_DIR = ROOT_DIR / "backend" / "runs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)


def get_allowed_origins() -> list[str]:
    raw_origins = os.getenv("BACKEND_CORS_ORIGINS", "*")
    if raw_origins.strip() == "*":
        return ["*"]
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]


@dataclass
class Job:
    id: str
    script: str
    args: list[str]
    command: list[str]
    status: str
    created_at: str
    started_at: str | None = None
    ended_at: str | None = None
    return_code: int | None = None
    log_path: str = ""


jobs: dict[str, Job] = {}
jobs_lock = threading.Lock()


class RunScriptRequest(BaseModel):
    script: str = Field(..., description="Nombre del script en backend/scripts")
    args: list[str] = Field(default_factory=list)
    rawArgs: str | None = None


class CreateContentJobRequest(BaseModel):
    url: str = Field(..., description="URL del video origen")
    browser: str | None = Field(default=None, description="chrome | firefox | brave | edge")
    cookiesFile: str | None = Field(default=None, description="Ruta a cookies.txt")
    ffmpeg: str | None = Field(default=None, description="Ruta opcional a ffmpeg")
    lang: str = Field(default="auto", description="auto | es | en | ...")
    subtitleFormat: str = Field(default="vtt", description="vtt | srt")


class CreateBlueJobRequest(BaseModel):
    target: str = Field(..., description="URL o target para OF-Scraper")
    binary: str | None = Field(default=None, description="Binario a ejecutar, por defecto ofscraper")
    profile: str | None = Field(default=None, description="Perfil/config de OF-Scraper")
    configPath: str | None = Field(default=None, description="Ruta opcional a config.json")
    extraArgs: str | None = Field(default=None, description="Argumentos extra en formato CLI")


def normalize_content_url(url: str) -> str:
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower().replace("www.", "")
    path = parsed.path.rstrip("/")

    if host in {"youtu.be"}:
        video_id = path.lstrip("/")
        return f"youtube:{video_id}"

    if "youtube.com" in host:
        query = dict(parse_qsl(parsed.query))
        video_id = query.get("v")
        if video_id:
            return f"youtube:{video_id}"

    if "instagram.com" in host:
        parts = [part for part in path.split("/") if part]
        if len(parts) >= 2 and parts[0] in {"reel", "p", "tv"}:
            return f"instagram:{parts[0]}:{parts[1]}"

    filtered_query = [(key, value) for key, value in parse_qsl(parsed.query) if not key.startswith("utm_")]
    normalized_query = urlencode(sorted(filtered_query))
    normalized = f"{host}{path}"
    if normalized_query:
        normalized = f"{normalized}?{normalized_query}"
    return normalized


def iter_source_url_files() -> Iterable[Path]:
    if not (ROOT_DIR / "output").exists():
        return []
    return (ROOT_DIR / "output").rglob("source_url.txt")


app = FastAPI(title="Intro Python Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def script_path(script_name: str) -> Path:
    candidate = (SCRIPTS_DIR / script_name).resolve()
    if not candidate.exists() or not candidate.is_file() or candidate.suffix != ".py":
        raise HTTPException(status_code=404, detail=f"Script no encontrado: {script_name}")
    if SCRIPTS_DIR.resolve() not in candidate.parents:
        raise HTTPException(status_code=400, detail="Ruta de script no permitida")
    return candidate


def enqueue_job(script_name: str, args: list[str]) -> dict:
    target = script_path(script_name)
    job_id = uuid.uuid4().hex[:12]
    log_path = LOGS_DIR / f"{job_id}.log"

    cmd = [sys.executable, str(target), *args]
    job = Job(
        id=job_id,
        script=script_name,
        args=args,
        command=cmd,
        status="queued",
        created_at=now_iso(),
        log_path=str(log_path),
    )

    with jobs_lock:
        jobs[job_id] = job

    thread = threading.Thread(target=run_job, args=(job_id,), daemon=True)
    thread.start()

    return asdict(job)


def run_job(job_id: str) -> None:
    with jobs_lock:
        job = jobs[job_id]
        job.status = "running"
        job.started_at = now_iso()

    log_file = Path(job.log_path)
    try:
        with log_file.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                job.command,
                cwd=str(ROOT_DIR),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            assert process.stdout is not None
            for line in process.stdout:
                log.write(line)
            return_code = process.wait()

        with jobs_lock:
            job.return_code = return_code
            job.status = "completed" if return_code == 0 else "failed"
            job.ended_at = now_iso()
    except Exception as exc:  # pragma: no cover
        with log_file.open("a", encoding="utf-8") as log:
            log.write(f"\n[backend-error] {exc}\n")
        with jobs_lock:
            job.status = "failed"
            job.return_code = -1
            job.ended_at = now_iso()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "scriptsDir": str(SCRIPTS_DIR)}


@app.get("/api/scripts")
def list_scripts() -> list[dict]:
    scripts = sorted(SCRIPTS_DIR.glob("*.py"), key=lambda p: p.name.lower())
    return [build_script_entry(path) for path in scripts]


@app.post("/api/jobs")
def create_job(payload: RunScriptRequest) -> dict:
    args = payload.args
    if payload.rawArgs:
        args = shlex.split(payload.rawArgs)
    return enqueue_job(payload.script, args)


@app.post("/api/content/jobs")
def create_content_job(payload: CreateContentJobRequest) -> dict:
    request = VideoContentRequest(
        url=payload.url,
        browser=payload.browser,
        cookies_file=payload.cookiesFile,
        ffmpeg=payload.ffmpeg,
        lang=payload.lang,
        subtitle_format=payload.subtitleFormat,
    )
    return enqueue_job("process_video_content.py", request.to_cli_args())


@app.post("/api/blue/jobs")
def create_blue_job(payload: CreateBlueJobRequest) -> dict:
    args = ["--target", payload.target]
    if payload.binary:
        args.extend(["--binary", payload.binary])
    if payload.profile:
        args.extend(["--profile", payload.profile])
    if payload.configPath:
        args.extend(["--config", payload.configPath])
    if payload.extraArgs:
        args.extend(["--extra-args", payload.extraArgs])
    return enqueue_job("run_ofscraper.py", args)


@app.get("/api/jobs")
def list_jobs() -> list[dict]:
    with jobs_lock:
        ordered = sorted(jobs.values(), key=lambda j: j.created_at, reverse=True)
        return [asdict(job) for job in ordered]


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job no encontrado")
        return asdict(job)


@app.get("/api/jobs/{job_id}/log")
def get_job_log(job_id: str) -> dict:
    with jobs_lock:
        job = jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job no encontrado")

    log_path = Path(job.log_path)
    if not log_path.exists():
        return {"content": ""}

    content = log_path.read_text(encoding="utf-8", errors="ignore")
    return {"content": content[-40000:]}


@app.get("/api/content/duplicates")
def find_duplicate_content(url: str) -> dict:
    normalized_target = normalize_content_url(url)
    matches: list[dict[str, str]] = []

    for source_file in iter_source_url_files():
        raw_url = source_file.read_text(encoding="utf-8", errors="ignore").strip()
        if not raw_url:
            continue
        if normalize_content_url(raw_url) != normalized_target:
            continue

        folder = source_file.parent
        matches.append(
            {
                "folder": str(folder.relative_to(ROOT_DIR)),
                "source_file": str(source_file.relative_to(ROOT_DIR)),
                "url": raw_url,
            }
        )

    return {
        "exists": len(matches) > 0,
        "normalizedUrl": normalized_target,
        "matches": sorted(matches, key=lambda item: item["folder"], reverse=True),
    }


@app.get("/api/files")
def list_files(path: str = "output") -> dict:
    target = (ROOT_DIR / path).resolve()
    if ROOT_DIR.resolve() not in target.parents and target != ROOT_DIR.resolve():
        raise HTTPException(status_code=400, detail="Ruta no permitida")
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="Carpeta no encontrada")

    items = []
    for child in sorted(
        target.iterdir(),
        key=lambda p: (not p.is_dir(), -p.stat().st_mtime, p.name.lower()),
    ):
        items.append(
            {
                "name": child.name,
                "isDir": child.is_dir(),
                "path": str(child.relative_to(ROOT_DIR)),
                "modifiedAt": datetime.fromtimestamp(child.stat().st_mtime, tz=timezone.utc).isoformat(),
            }
        )

    return {"base": str(target.relative_to(ROOT_DIR)), "items": items}


@app.get("/api/file")
def get_file(path: str):
    target = (ROOT_DIR / path).resolve()
    if ROOT_DIR.resolve() not in target.parents:
        raise HTTPException(status_code=400, detail="Ruta no permitida")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="Fichero no encontrado")
    return FileResponse(target, filename=target.name)
