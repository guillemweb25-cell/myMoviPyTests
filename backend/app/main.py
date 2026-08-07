from __future__ import annotations

import asyncio
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import uuid
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from . import db
from .catalog import build_script_entry
from .services import VideoContentRequest
from .services.comfyui import ComfyUiClient

ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT_DIR / "backend" / "scripts"
LOGS_DIR = ROOT_DIR / "backend" / "runs"
UPLOADS_DIR = ROOT_DIR / "output" / "uploads"
DB_PATH = ROOT_DIR / "backend" / "runs" / "jobs.db"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_UPLOAD_EXTENSIONS = {".mp3", ".mp4", ".m4a", ".wav"}
CONVERT_TO_MP3_EXTENSIONS = {".ogg", ".oga", ".opus"}

# Token de acceso. Si MEDIA_OPS_TOKEN no esta definido, la auth queda desactivada
# (modo desarrollo). Rutas publicas que nunca exigen token:
ACCESS_TOKEN = os.getenv("MEDIA_OPS_TOKEN", "").strip()
PUBLIC_PATHS = {"/api/health", "/docs", "/openapi.json", "/redoc"}


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


class DetectClipsRequest(BaseModel):
    transcriptPath: str = Field(..., description="Ruta al .vtt/.srt dentro del workspace")
    count: int = Field(default=5, ge=1, le=12)
    minDuration: int = Field(default=15, ge=5, le=120)
    maxDuration: int = Field(default=60, ge=10, le=180)


class ClipSourceFromUrlRequest(BaseModel):
    url: str = Field(..., description="URL del video a descargar")
    browser: str | None = None
    cookiesFile: str | None = None
    ffmpeg: str | None = None
    lang: str = Field(default="auto")
    subtitleFormat: str = Field(default="vtt")


class RenderClipRequest(BaseModel):
    video: str = Field(..., description="Ruta al video dentro del workspace")
    start: float = Field(..., description="Inicio en segundos")
    end: float = Field(..., description="Fin en segundos")
    subtitles: bool = Field(default=True, description="Quemar subtitulos karaoke")
    topRatio: float = Field(default=0.7, ge=0.3, le=0.85)
    title: str | None = None


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


def safe_upload_name(filename: str | None) -> str:
    candidate = Path(filename or "").name.strip()
    if not candidate:
        candidate = f"audio_{uuid.uuid4().hex[:8]}.mp3"
    return candidate


def normalize_folder_title(raw_title: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", raw_title.strip())
    cleaned = cleaned.strip("._-")
    if not cleaned:
        raise HTTPException(status_code=400, detail="El titulo de carpeta es obligatorio.")
    return cleaned.lower()


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


def extract_token(request: Request) -> str | None:
    """Toma el token de la cabecera Authorization Bearer, X-API-Key, o del
    query param ``token`` (necesario para <img>/<audio>/<video> y EventSource,
    que no pueden enviar cabeceras)."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    api_key = request.headers.get("x-api-key")
    if api_key:
        return api_key.strip()
    token = request.query_params.get("token")
    return token.strip() if token else None


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    needs_auth = (
        ACCESS_TOKEN
        and path.startswith("/api/")
        and path not in PUBLIC_PATHS
        and request.method != "OPTIONS"
    )
    if needs_auth and extract_token(request) != ACCESS_TOKEN:
        return JSONResponse(status_code=401, content={"detail": "No autorizado"})
    return await call_next(request)


@app.on_event("startup")
def on_startup() -> None:
    db.init(DB_PATH)
    restored = db.load_jobs(Job)
    with jobs_lock:
        jobs.update(restored)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def script_path(script_name: str) -> Path:
    candidate = (SCRIPTS_DIR / script_name).resolve()
    if not candidate.exists() or not candidate.is_file() or candidate.suffix != ".py":
        raise HTTPException(status_code=404, detail=f"Script no encontrado: {script_name}")
    if SCRIPTS_DIR.resolve() not in candidate.parents:
        raise HTTPException(status_code=400, detail="Ruta de script no permitida")
    return candidate


def resolve_within_root(relative_path: str) -> Path:
    target = (ROOT_DIR / relative_path).resolve()
    if ROOT_DIR.resolve() not in target.parents and target != ROOT_DIR.resolve():
        raise HTTPException(status_code=400, detail="Ruta no permitida")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail=f"Fichero no encontrado: {relative_path}")
    return target


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
    db.save_job(job)

    thread = threading.Thread(target=run_job, args=(job_id,), daemon=True)
    thread.start()

    return asdict(job)


def run_job(job_id: str) -> None:
    with jobs_lock:
        job = jobs[job_id]
        job.status = "running"
        job.started_at = now_iso()
    db.save_job(job)

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
        db.save_job(job)
    except Exception as exc:  # pragma: no cover
        with log_file.open("a", encoding="utf-8") as log:
            log.write(f"\n[backend-error] {exc}\n")
        with jobs_lock:
            job.status = "failed"
            job.return_code = -1
            job.ended_at = now_iso()
        db.save_job(job)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "scriptsDir": str(SCRIPTS_DIR), "authRequired": bool(ACCESS_TOKEN)}


@app.get("/api/comfy/status")
def comfy_status() -> dict:
    return asdict(ComfyUiClient().status())


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


@app.post("/api/transcriptions/upload")
async def upload_and_transcribe(
    file: UploadFile = File(...),
    lang: str = "auto",
    subtitleFormat: str = "vtt",
    folderTitle: str = "",
) -> dict:
    filename = safe_upload_name(file.filename)
    extension = Path(filename).suffix.lower()

    if extension not in ALLOWED_UPLOAD_EXTENSIONS and extension not in CONVERT_TO_MP3_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Formato no soportado. Usa mp3, mp4, m4a, wav, ogg u opus.")

    if subtitleFormat not in {"vtt", "srt"}:
        raise HTTPException(status_code=400, detail="subtitleFormat debe ser vtt o srt.")

    folder_name = normalize_folder_title(folderTitle)
    target_folder = UPLOADS_DIR / folder_name
    target_folder.mkdir(parents=True, exist_ok=True)

    target_name = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{extension}"
    destination = target_folder / target_name

    with destination.open("wb") as out_file:
        shutil.copyfileobj(file.file, out_file)
    await file.close()

    transcription_source = destination
    converted_path: str | None = None

    if extension in CONVERT_TO_MP3_EXTENSIONS:
        mp3_destination = destination.with_suffix(".mp3")
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(destination),
                    "-vn",
                    "-acodec",
                    "libmp3lame",
                    str(mp3_destination),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except FileNotFoundError as exc:
            raise HTTPException(status_code=500, detail="ffmpeg no esta instalado en el backend.") from exc
        except subprocess.CalledProcessError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"No se pudo convertir el audio a mp3. Detalle: {exc.stderr[-300:] if exc.stderr else 'sin detalles'}",
            ) from exc

        transcription_source = mp3_destination
        converted_path = str(mp3_destination.relative_to(ROOT_DIR))

    relative_path = str(transcription_source.relative_to(ROOT_DIR))
    job = enqueue_job(
        "transcribe_sutitles.py",
        ["--file", relative_path, "--lang", lang or "auto", "--format", subtitleFormat],
    )
    return {
        "folderPath": str(target_folder.relative_to(ROOT_DIR)),
        "uploadedPath": str(destination.relative_to(ROOT_DIR)),
        "transcriptionSourcePath": relative_path,
        "convertedToMp3Path": converted_path,
        "job": job,
    }


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


@app.get("/api/jobs/{job_id}/stream")
async def stream_job_log(job_id: str):
    """Streaming en vivo del log via Server-Sent Events.

    Emite los datos ya escritos y luego sigue el fichero hasta que el job
    termina, momento en el que manda un evento ``end`` con el estado final.
    """
    with jobs_lock:
        job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job no encontrado")

    log_path = Path(job.log_path)

    async def event_generator():
        position = 0
        while True:
            if log_path.exists():
                with log_path.open("r", encoding="utf-8", errors="ignore") as handle:
                    handle.seek(position)
                    chunk = handle.read()
                    position = handle.tell()
                if chunk:
                    for line in chunk.splitlines():
                        yield f"data: {line}\n\n"

            with jobs_lock:
                current = jobs.get(job_id)
            status = current.status if current else "completed"
            at_end = (not log_path.exists()) or position >= log_path.stat().st_size
            if status in {"completed", "failed"} and at_end:
                yield f"event: end\ndata: {status}\n\n"
                return

            await asyncio.sleep(0.5)

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(
        event_generator(), media_type="text/event-stream", headers=headers
    )


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


@app.post("/api/clips/source-from-url")
def clip_source_from_url(payload: ClipSourceFromUrlRequest) -> dict:
    if not payload.url.strip():
        raise HTTPException(status_code=400, detail="La URL es obligatoria")
    args = ["--url", payload.url.strip(), "--lang", payload.lang, "--format", payload.subtitleFormat]
    if payload.browser:
        args.extend(["--browser", payload.browser])
    if payload.cookiesFile:
        args.extend(["--cookies", payload.cookiesFile])
    if payload.ffmpeg:
        args.extend(["--ffmpeg", payload.ffmpeg])
    return enqueue_job("download_and_transcribe_video.py", args)


@app.get("/api/clips/sources")
def list_clip_sources() -> list[dict]:
    """Lista carpetas de output que tienen un video y una transcripcion .vtt/.srt."""
    output_root = ROOT_DIR / "output"
    if not output_root.exists():
        return []

    sources = []
    for transcript in sorted(output_root.rglob("*.vtt")) + sorted(output_root.rglob("*.srt")):
        if "/clips/" in str(transcript):
            continue
        video = None
        for ext in (".mp4", ".webm", ".mkv", ".mov"):
            candidate = transcript.with_suffix(ext)
            if candidate.exists():
                video = candidate
                break
        if not video:
            siblings = sorted(transcript.parent.glob("*.mp4"))
            video = siblings[0] if siblings else None
        if not video:
            continue
        sources.append(
            {
                "folder": str(transcript.parent.relative_to(ROOT_DIR)),
                "name": video.stem,
                "videoPath": str(video.relative_to(ROOT_DIR)),
                "transcriptPath": str(transcript.relative_to(ROOT_DIR)),
                "modifiedAt": datetime.fromtimestamp(video.stat().st_mtime, tz=timezone.utc).isoformat(),
            }
        )

    sources.sort(key=lambda item: item["modifiedAt"], reverse=True)
    return sources


@app.post("/api/clips/detect")
def detect_clips_endpoint(payload: DetectClipsRequest) -> dict:
    from .services.clip_detector import detect_clips

    transcript = resolve_within_root(payload.transcriptPath)
    if transcript.suffix.lower() not in {".vtt", ".srt"}:
        raise HTTPException(status_code=400, detail="La transcripcion debe ser .vtt o .srt")

    # Busca un video hermano (mismo nombre base) en la misma carpeta.
    video_path: str | None = None
    for ext in (".mp4", ".webm", ".mkv", ".mov"):
        candidate = transcript.with_suffix(ext)
        if candidate.exists():
            video_path = str(candidate.relative_to(ROOT_DIR))
            break
    if not video_path:
        siblings = sorted(transcript.parent.glob("*.mp4"))
        if siblings:
            video_path = str(siblings[0].relative_to(ROOT_DIR))

    try:
        clips = detect_clips(
            transcript,
            count=payload.count,
            min_dur=payload.minDuration,
            max_dur=payload.maxDuration,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Fallo la deteccion de clips: {exc}") from exc

    return {"videoPath": video_path, "clips": [clip.to_dict() for clip in clips]}


@app.post("/api/clips/render")
def render_clip_endpoint(payload: RenderClipRequest) -> dict:
    resolve_within_root(payload.video)
    if payload.end <= payload.start:
        raise HTTPException(status_code=400, detail="end debe ser mayor que start")

    args = [
        "--video", payload.video,
        "--start", f"{payload.start:.3f}",
        "--end", f"{payload.end:.3f}",
        "--top-ratio", f"{payload.topRatio:.2f}",
    ]
    if payload.subtitles:
        args.append("--subtitles")
    return enqueue_job("render_clip.py", args)


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
