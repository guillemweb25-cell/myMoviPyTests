from __future__ import annotations

import asyncio
import json
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
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
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
# El callback de YouTube lo invoca el navegador redirigido por Google, sin token.
PUBLIC_PATHS = {"/api/health", "/docs", "/openapi.json", "/redoc", "/api/youtube/callback"}

# URL publica de la app. El redirect de OAuth apunta a la raiz del frontend, que
# recoge ?code=&state= y lo reenvia al backend (mas facil de configurar en Google
# Cloud que una ruta concreta).
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://mymovi.enguillem.es").rstrip("/")
YOUTUBE_REDIRECT_URI = f"{PUBLIC_BASE_URL}/"
YOUTUBE_CREDS_DIR = ROOT_DIR / "youtube_creds"


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
    channelId: int | None = None
    count: int = Field(default=5, ge=1, le=12)
    minDuration: int = Field(default=15, ge=5, le=120)
    maxDuration: int = Field(default=60, ge=10, le=180)


class ChannelCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    language: str = Field(default="es")
    seoRules: str = Field(default="")


class ChannelUpdateRequest(BaseModel):
    name: str | None = None
    language: str | None = None
    seoRules: str | None = None


class CampaignCreateRequest(BaseModel):
    channelId: int
    name: str = Field(default="", max_length=200)
    sourceUrl: str = Field(..., description="URL del video de YouTube a clipear")
    campaignUrl: str = Field(default="", description="URL de la campana (Whop)")
    cookiesFile: str | None = None


class CampaignUpdateRequest(BaseModel):
    name: str | None = None
    campaignUrl: str | None = None


class ClipSourceFromUrlRequest(BaseModel):
    url: str = Field(..., description="URL del video a descargar")
    channelId: int | None = None
    browser: str | None = None
    cookiesFile: str | None = None
    ffmpeg: str | None = None
    lang: str = Field(default="auto")
    subtitleFormat: str = Field(default="vtt")


def channel_slug(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower())
    return cleaned.strip("-") or "canal"


def channel_output_rel(channel: dict) -> str:
    """Carpeta relativa de output para un canal: output/0002-slug."""
    return f"output/{channel['id']:04d}-{channel_slug(channel['name'])}"


def channel_id_from_path(rel_path: str | None) -> int | None:
    """Deduce el id de canal de una ruta output/0002-slug/..."""
    if not rel_path:
        return None
    parts = Path(rel_path).parts
    if len(parts) >= 2 and parts[0] == "output":
        match = re.match(r"(\d{4})-", parts[1])
        if match:
            channel_id = int(match.group(1))
            if db.get_channel(channel_id):
                return channel_id
    return None


class ClipSettingsRequest(BaseModel):
    focus: str = Field(default="center", pattern="^(left|center|right)$")
    zoom: float = Field(default=1.0, ge=1.0, le=2.5)
    topRatio: float = Field(default=0.7, ge=0.3, le=0.85)
    subtitles: bool = True
    overlayText: str = Field(default="", max_length=300)


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


@app.get("/api/channels")
def list_channels_endpoint() -> list[dict]:
    return db.list_channels()


@app.post("/api/channels")
def create_channel_endpoint(payload: ChannelCreateRequest) -> dict:
    return db.create_channel(payload.name.strip(), payload.language, payload.seoRules, now_iso())


@app.patch("/api/channels/{channel_id}")
def update_channel_endpoint(channel_id: int, payload: ChannelUpdateRequest) -> dict:
    fields: dict = {}
    if payload.name is not None:
        fields["name"] = payload.name.strip()
    if payload.language is not None:
        fields["language"] = payload.language
    if payload.seoRules is not None:
        fields["seo_rules"] = payload.seoRules
    channel = db.update_channel(channel_id, fields)
    if not channel:
        raise HTTPException(status_code=404, detail="Canal no encontrado")
    return channel


@app.delete("/api/channels/{channel_id}")
def delete_channel_endpoint(channel_id: int) -> dict:
    if not db.get_channel(channel_id):
        raise HTTPException(status_code=404, detail="Canal no encontrado")
    db.delete_channel(channel_id)
    return {"deleted": channel_id}


@app.get("/api/youtube/{channel_id}/status")
def youtube_status(channel_id: int) -> dict:
    from .services.youtube_service import YouTubeService

    channel = db.get_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Canal no encontrado")
    service = YouTubeService(channel_id, YOUTUBE_CREDS_DIR)
    return {
        "hasSecret": service.has_secret(),
        "linked": bool(channel["youtubeLinked"]),
        "channelName": channel["youtubeName"],
    }


@app.post("/api/youtube/{channel_id}/secret")
async def upload_youtube_secret(channel_id: int, file: UploadFile = File(...)) -> dict:
    from .services.youtube_service import YouTubeService

    if not db.get_channel(channel_id):
        raise HTTPException(status_code=404, detail="Canal no encontrado")
    content = await file.read()
    await file.close()
    service = YouTubeService(channel_id, YOUTUBE_CREDS_DIR)
    try:
        service.save_secret(content)
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"client_secret.json invalido: {exc}") from exc
    return {"hasSecret": True}


@app.post("/api/youtube/{channel_id}/unlink")
def youtube_unlink(channel_id: int) -> dict:
    from .services.youtube_service import YouTubeService

    if not db.get_channel(channel_id):
        raise HTTPException(status_code=404, detail="Canal no encontrado")
    YouTubeService(channel_id, YOUTUBE_CREDS_DIR).unlink()
    db.update_channel(channel_id, {"youtube_linked": 0, "youtube_name": ""})
    return {"linked": False}


@app.get("/api/youtube/{channel_id}/auth-url")
def youtube_auth_url(channel_id: int) -> dict:
    from .services.youtube_service import YouTubeService

    if not db.get_channel(channel_id):
        raise HTTPException(status_code=404, detail="Canal no encontrado")
    service = YouTubeService(channel_id, YOUTUBE_CREDS_DIR)
    try:
        url = service.get_auth_url(YOUTUBE_REDIRECT_URI)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail="Sube primero el client_secret.json del canal.") from exc
    return {"authUrl": url, "redirectUri": YOUTUBE_REDIRECT_URI}


class YoutubeFinishRequest(BaseModel):
    code: str
    state: str


@app.post("/api/youtube/finish")
def youtube_finish(payload: YoutubeFinishRequest) -> dict:
    from .services.youtube_service import YouTubeService

    try:
        channel_id = int(payload.state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="state invalido") from exc
    if not db.get_channel(channel_id):
        raise HTTPException(status_code=404, detail="Canal no encontrado")
    service = YouTubeService(channel_id, YOUTUBE_CREDS_DIR)
    try:
        service.finish_oauth(payload.code, YOUTUBE_REDIRECT_URI)
        info = service.get_channel_info()
        yt_name = info["snippet"]["title"] if info else ""
        db.update_channel(channel_id, {"youtube_linked": 1, "youtube_name": yt_name})
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"No se pudo finalizar OAuth: {exc}") from exc
    return {"linked": True, "channelName": yt_name}


@app.get("/api/campaigns")
def list_campaigns_endpoint(channelId: int | None = None) -> list[dict]:
    return db.list_campaigns(channelId)


@app.get("/api/campaigns/{campaign_id}")
def get_campaign_endpoint(campaign_id: int) -> dict:
    campaign = db.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campana no encontrada")
    return campaign


def find_existing_download(channel: dict, source_url: str) -> tuple[str, str] | None:
    """Si el video ya se descargo en la carpeta del canal, devuelve
    (transcript_rel, video_rel) para reutilizarlo en vez de re-descargar."""
    channel_dir = ROOT_DIR / channel_output_rel(channel)
    if not channel_dir.exists():
        return None
    target = normalize_content_url(source_url)
    for source_file in channel_dir.rglob("source_url.txt"):
        raw = source_file.read_text(encoding="utf-8", errors="ignore").strip()
        if not raw or normalize_content_url(raw) != target:
            continue
        folder = source_file.parent
        vtts = sorted(folder.glob("*.vtt"))
        videos = sorted(folder.glob("*.mp4"))
        if vtts and videos:
            return (
                str(vtts[0].relative_to(ROOT_DIR)),
                str(videos[0].relative_to(ROOT_DIR)),
            )
    return None


@app.post("/api/campaigns")
def create_campaign_endpoint(payload: CampaignCreateRequest) -> dict:
    channel = db.get_channel(payload.channelId)
    if not channel:
        raise HTTPException(status_code=404, detail="Canal no encontrado")
    if not payload.sourceUrl.strip():
        raise HTTPException(status_code=400, detail="La URL del video es obligatoria")

    name = payload.name.strip() or payload.sourceUrl.strip()
    campaign = db.create_campaign(
        payload.channelId, name, payload.sourceUrl.strip(), payload.campaignUrl.strip(), now_iso()
    )

    # Si el video ya se descargo antes, se reutiliza (conserva clips, no re-descarga).
    existing = find_existing_download(channel, payload.sourceUrl.strip())
    if existing:
        transcript_rel, video_rel = existing
        db.update_campaign(campaign["id"], {
            "transcript_path": transcript_rel,
            "video_path": video_rel,
            "status": "ready",
        })
        return {"campaign": db.get_campaign(campaign["id"]), "job": None}

    args = [
        "--url", payload.sourceUrl.strip(),
        "--lang", "auto",
        "--format", "vtt",
        "--outbase", channel_output_rel(channel),
        "--campaign", str(campaign["id"]),
    ]
    if payload.cookiesFile:
        args.extend(["--cookies", payload.cookiesFile])
    job = enqueue_job("download_and_transcribe_video.py", args)
    return {"campaign": campaign, "job": job}


@app.patch("/api/campaigns/{campaign_id}")
def update_campaign_endpoint(campaign_id: int, payload: CampaignUpdateRequest) -> dict:
    if not db.get_campaign(campaign_id):
        raise HTTPException(status_code=404, detail="Campana no encontrada")
    fields: dict = {}
    if payload.name is not None:
        fields["name"] = payload.name.strip()
    if payload.campaignUrl is not None:
        fields["campaign_url"] = payload.campaignUrl.strip()
    return db.update_campaign(campaign_id, fields)


class CampaignBriefRequest(BaseModel):
    briefUrl: str = Field(default="")
    briefText: str = Field(default="")


@app.post("/api/campaigns/{campaign_id}/brief")
def extract_campaign_brief(campaign_id: int, payload: CampaignBriefRequest) -> dict:
    from .services.brief_extractor import extract_rules, fetch_brief_text

    campaign = db.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campana no encontrada")

    text = payload.briefText.strip()
    if not text and payload.briefUrl.strip():
        try:
            text = fetch_brief_text(payload.briefUrl.strip())
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"No se pudo leer el brief: {exc}") from exc
    if not text:
        raise HTTPException(status_code=400, detail="Pega el brief o un link (Google Docs).")

    try:
        rules = extract_rules(text)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Fallo la extraccion del brief: {exc}") from exc

    db.update_campaign(campaign_id, {
        "brief_url": payload.briefUrl.strip(),
        "rules_json": json.dumps(rules, ensure_ascii=False),
    })
    return {"campaign": db.get_campaign(campaign_id), "rules": rules}


@app.post("/api/campaigns/{campaign_id}/apply-rules")
def apply_campaign_rules(campaign_id: int) -> dict:
    """Aplica el texto en pantalla obligatorio a todos los clips de la campana."""
    campaign = db.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campana no encontrada")
    on_screen = (campaign.get("rules") or {}).get("onScreenText", "").strip()
    if not on_screen:
        raise HTTPException(status_code=400, detail="El brief no define texto en pantalla obligatorio.")
    clips = db.load_clips(campaign["transcriptPath"])
    for clip in clips:
        db.update_clip(clip["id"], {"overlay_text": on_screen})
    return {"updated": len(clips), "onScreenText": on_screen}


@app.delete("/api/campaigns/{campaign_id}")
def delete_campaign_endpoint(campaign_id: int) -> dict:
    if not db.get_campaign(campaign_id):
        raise HTTPException(status_code=404, detail="Campana no encontrada")
    db.delete_campaign(campaign_id)
    return {"deleted": campaign_id}


@app.post("/api/clips/source-from-url")
def clip_source_from_url(payload: ClipSourceFromUrlRequest) -> dict:
    if not payload.url.strip():
        raise HTTPException(status_code=400, detail="La URL es obligatoria")
    args = ["--url", payload.url.strip(), "--lang", payload.lang, "--format", payload.subtitleFormat]
    if payload.channelId is not None:
        channel = db.get_channel(payload.channelId)
        if not channel:
            raise HTTPException(status_code=404, detail="Canal no encontrado")
        args.extend(["--outbase", channel_output_rel(channel)])
    if payload.browser:
        args.extend(["--browser", payload.browser])
    if payload.cookiesFile:
        args.extend(["--cookies", payload.cookiesFile])
    if payload.ffmpeg:
        args.extend(["--ffmpeg", payload.ffmpeg])
    return enqueue_job("download_and_transcribe_video.py", args)


@app.get("/api/clips/sources")
def list_clip_sources(channelId: int | None = None) -> list[dict]:
    """Lista carpetas con video + transcripcion. Si se pasa channelId, solo las
    de la carpeta de ese canal."""
    output_root = ROOT_DIR / "output"
    if channelId is not None:
        channel = db.get_channel(channelId)
        if channel:
            output_root = ROOT_DIR / channel_output_rel(channel)
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

    clip_dicts = []
    for clip in clips:
        data = clip.to_dict()
        data["id"] = uuid.uuid4().hex[:12]
        clip_dicts.append(data)

    db.replace_clips(payload.transcriptPath, video_path, payload.channelId, clip_dicts, now_iso())
    return {"videoPath": video_path, "clips": db.load_clips(payload.transcriptPath)}


def _annotate_clip(clip: dict) -> dict:
    rendered_path = clip.get("renderedPath") or ""
    clip["rendered"] = bool(rendered_path) and (ROOT_DIR / rendered_path).exists()
    clip["uploaded"] = bool(clip.get("youtubeUrl"))
    return clip


@app.get("/api/clips/list")
def list_saved_clips(transcriptPath: str) -> dict:
    return {"clips": [_annotate_clip(c) for c in db.load_clips(transcriptPath)]}


@app.patch("/api/clips/{clip_id}/settings")
def update_clip_settings_endpoint(clip_id: str, payload: ClipSettingsRequest) -> dict:
    if not db.get_clip(clip_id):
        raise HTTPException(status_code=404, detail="Clip no encontrado")
    db.update_clip(clip_id, {
        "focus": payload.focus,
        "zoom": payload.zoom,
        "top_ratio": payload.topRatio,
        "subtitles": int(payload.subtitles),
        "overlay_text": payload.overlayText,
    })
    return _annotate_clip(db.get_clip(clip_id))


@app.post("/api/clips/{clip_id}/render")
def render_clip_endpoint(clip_id: str) -> dict:
    clip = db.get_clip(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip no encontrado")
    video_rel = clip["videoPath"]
    if not video_rel:
        raise HTTPException(status_code=400, detail="El clip no tiene video asociado")
    resolve_within_root(video_rel)

    out_rel = str(Path(video_rel).parent / "clips" / f"clip_{clip_id}.mp4")
    args = [
        "--video", video_rel,
        "--start", f"{clip['start']:.3f}",
        "--end", f"{clip['end']:.3f}",
        "--out", out_rel,
        "--top-ratio", f"{clip['topRatio']:.2f}",
        "--focus", clip["focus"],
        "--zoom", f"{clip['zoom']:.2f}",
    ]
    if clip["subtitles"]:
        args.append("--subtitles")
    if clip.get("overlayText"):
        args.extend(["--overlay", clip["overlayText"]])

    db.update_clip(clip_id, {"rendered_path": out_rel})
    job = enqueue_job("render_clip.py", args)
    return {"job": job, "renderedPath": out_rel}


@app.post("/api/clips/{clip_id}/seo")
def generate_clip_seo_endpoint(clip_id: str) -> dict:
    from .services.clip_seo import generate_clip_seo

    clip = db.get_clip(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip no encontrado")
    channel_id = clip.get("channelId") or channel_id_from_path(clip.get("videoPath"))
    channel = db.get_channel(channel_id) if channel_id else None
    if not channel:
        # Sin canal: usa reglas vacias e idioma por defecto.
        channel = {"language": "es", "seoRules": ""}
    campaign = db.get_campaign_by_transcript(clip.get("transcriptPath") or "")
    campaign_rules = (campaign or {}).get("rules") or None
    try:
        seo = generate_clip_seo(clip, channel, ROOT_DIR, campaign_rules=campaign_rules)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Fallo la generacion de SEO: {exc}") from exc
    db.update_clip(clip_id, {
        "seo_title": seo["title"],
        "seo_description": seo["description"],
        "seo_tags": seo["tags"],
    })
    return seo


@app.post("/api/clips/{clip_id}/upload")
def upload_clip_endpoint(clip_id: str) -> dict:
    clip = db.get_clip(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip no encontrado")
    channel_id = clip.get("channelId") or channel_id_from_path(clip.get("videoPath"))
    if not channel_id:
        raise HTTPException(status_code=400, detail="El clip no tiene canal. Detectalo desde un canal.")
    if clip.get("channelId") != channel_id:
        db.update_clip(clip_id, {"channel_id": channel_id})  # auto-repara el canal
    channel = db.get_channel(channel_id)
    if not channel or not channel["youtubeLinked"]:
        raise HTTPException(status_code=400, detail="El canal no esta vinculado a YouTube.")
    rendered = clip.get("renderedPath") or ""
    if not rendered or not (ROOT_DIR / rendered).exists():
        raise HTTPException(status_code=400, detail="Renderiza el clip antes de subirlo.")
    return enqueue_job("upload_clip.py", ["--clip", clip_id])


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
