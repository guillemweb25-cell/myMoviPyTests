from __future__ import annotations

import asyncio
import json
import os
import signal
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
running_procs: dict[str, "subprocess.Popen"] = {}  # job_id -> proceso (para poder pararlo)


class RunScriptRequest(BaseModel):
    script: str = Field(..., description="Nombre del script en backend/scripts")
    args: list[str] = Field(default_factory=list)
    rawArgs: str | None = None


class DetectClipsRequest(BaseModel):
    transcriptPath: str = Field(..., description="Ruta al .vtt/.srt dentro del workspace")
    channelId: int | None = None
    parts: int = Field(default=4, ge=0, le=20, description="Partes en que dividir la transcripcion (0 = auto por duracion)")
    clipsPerPart: int = Field(default=5, ge=1, le=10)
    targetDuration: int = Field(default=40, ge=10, le=90)


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
    focus: str = Field(default="center", pattern="^(left|center|right|follow|facecam)$")
    zoom: float = Field(default=1.0, ge=1.0, le=2.5)
    topRatio: float = Field(default=0.7, ge=0.3, le=0.85)
    subtitles: bool = True
    overlayText: str = Field(default="", max_length=300)
    endcardPercent: int = Field(default=0, ge=0, le=99)


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
                start_new_session=True,  # grupo propio: permite matar todo el árbol (hijos incl.)
            )
            with jobs_lock:
                running_procs[job_id] = process

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
    finally:
        with jobs_lock:
            running_procs.pop(job_id, None)


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
    rules = campaign.get("rules") or {}
    # Si el brief no define un texto en pantalla explícito, usa el caption obligatorio
    # (p.ej. "Subscribe to @thetrailblazerspod...") — que sí debe verse siempre.
    on_screen = (rules.get("onScreenText") or "").strip() or (rules.get("captionRequired") or "").strip()
    if not on_screen:
        raise HTTPException(status_code=400, detail="El brief no define texto en pantalla ni caption obligatorio.")
    clips = db.load_clips(campaign["transcriptPath"])
    for clip in clips:
        db.update_clip(clip["id"], {"overlay_text": on_screen})
    return {"updated": len(clips), "onScreenText": on_screen}


def _video_duration(video_abs: Path) -> float:
    """Duración del vídeo en segundos (ffmpeg parsea 'Duration:'). Cacheada en un
    fichero junto al vídeo para no re-sondear en cada carga."""
    cache = video_abs.parent / "duration.txt"
    if cache.exists():
        try:
            return float(cache.read_text(encoding="utf-8").strip())
        except Exception:
            pass
    proc = subprocess.run(["ffmpeg", "-i", str(video_abs)], capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", proc.stderr)
    if not m:
        return 0.0
    dur = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    try:
        cache.write_text(str(dur), encoding="utf-8")
    except Exception:
        pass
    return dur


@app.get("/api/campaigns/{campaign_id}/coverage")
def campaign_coverage(campaign_id: int) -> dict:
    """Cobertura del vídeo fuente: duración total + rangos clipeados (para el mapa
    tipo github de qué se ha clipeado y qué queda)."""
    campaign = db.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campana no encontrada")
    video_rel = campaign.get("videoPath") or ""
    duration = _video_duration(resolve_within_root(video_rel)) if video_rel and (ROOT_DIR / video_rel).exists() else 0.0
    clips = db.load_clips(campaign.get("transcriptPath") or "")
    ranges = [{
        "id": c["id"], "start": float(c["start"]), "end": float(c["end"]),
        "title": c.get("title") or "", "rendered": bool(c.get("renderedPath")), "uploaded": bool(c.get("youtubeUrl")),
    } for c in clips]
    return {"duration": duration, "clips": ranges}


@app.post("/api/campaigns/{campaign_id}/watermark")
async def upload_campaign_watermark(campaign_id: int, file: UploadFile = File(...)) -> dict:
    """Sube el PNG del watermark de la campaña. Se superpone ARRIBA CENTRADO en
    todos los clips al renderizar (requisito 'watermark clearly visible')."""
    campaign = db.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campana no encontrada")
    ref = campaign.get("videoPath") or campaign.get("transcriptPath") or ""
    if not ref:
        raise HTTPException(status_code=400, detail="La campaña aún no tiene carpeta (prepárala primero).")
    folder = resolve_within_root(ref).parent
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / "watermark.png"
    out.write_bytes(await file.read())
    rel = str(out.relative_to(ROOT_DIR))
    db.update_campaign(campaign_id, {"watermark_path": rel})
    return {"watermarkPath": rel}


@app.delete("/api/campaigns/{campaign_id}/watermark")
def delete_campaign_watermark(campaign_id: int) -> dict:
    if not db.get_campaign(campaign_id):
        raise HTTPException(status_code=404, detail="Campana no encontrada")
    db.update_campaign(campaign_id, {"watermark_path": ""})
    return {"watermarkPath": ""}


@app.post("/api/campaigns/{campaign_id}/scene-frame")
def campaign_scene_frame(campaign_id: int, t: float = 30.0) -> dict:
    """Fotograma del vídeo de la campaña (a los `t` s) para marcar el facecam."""
    campaign = db.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campana no encontrada")
    video_rel = campaign.get("videoPath") or ""
    if not video_rel or not (ROOT_DIR / video_rel).exists():
        raise HTTPException(status_code=400, detail="La campaña aún no tiene vídeo descargado.")
    video_abs = resolve_within_root(video_rel)
    out = video_abs.parent / f"campframe_{int(t)}.jpg"
    subprocess.run(["ffmpeg", "-y", "-ss", f"{max(0.0, t):.2f}", "-i", str(video_abs),
                    "-frames:v", "1", "-q:v", "3", "-vf", "scale=960:-1", str(out)], capture_output=True)
    if not out.exists():
        raise HTTPException(status_code=500, detail="No se pudo extraer el fotograma.")
    return {"frame": str(out.relative_to(ROOT_DIR))}


class FacecamRequest(BaseModel):
    x: float
    y: float
    w: float
    h: float
    zoom: float = 1.4


@app.post("/api/campaigns/{campaign_id}/facecam")
def set_campaign_facecam(campaign_id: int, payload: FacecamRequest) -> dict:
    """Guarda el recuadro de la webcam (facecam) de la campaña y el zoom de la
    pantalla. Encuadre 'facecam': arriba la cara, abajo la pantalla."""
    if not db.get_campaign(campaign_id):
        raise HTTPException(status_code=404, detail="Campana no encontrada")
    x = min(max(payload.x, 0.0), 1.0)
    y = min(max(payload.y, 0.0), 1.0)
    w = min(max(payload.w, 0.02), 1.0 - x)
    h = min(max(payload.h, 0.02), 1.0 - y)
    fc = {"x": round(x, 4), "y": round(y, 4), "w": round(w, 4), "h": round(h, 4),
          "zoom": round(min(max(payload.zoom, 1.0), 3.0), 2)}
    db.update_campaign(campaign_id, {"facecam": json.dumps(fc)})
    return {"facecam": fc}


@app.delete("/api/campaigns/{campaign_id}/facecam")
def delete_campaign_facecam(campaign_id: int) -> dict:
    if not db.get_campaign(campaign_id):
        raise HTTPException(status_code=404, detail="Campana no encontrada")
    db.update_campaign(campaign_id, {"facecam": ""})
    return {"facecam": None}


class CampaignCreatorRequest(BaseModel):
    creator: str = ""


@app.post("/api/campaigns/{campaign_id}/creator")
def set_campaign_creator(campaign_id: int, payload: CampaignCreatorRequest) -> dict:
    """Fija el nombre del invitado/creador a nombrar en el título de los clips
    (requisito de compliance tipo 'deja claro que es una entrevista con X')."""
    campaign = db.get_campaign(campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campana no encontrada")
    rules = campaign.get("rules") or {}
    rules["creator"] = payload.creator.strip()
    db.update_campaign(campaign_id, {"rules_json": json.dumps(rules, ensure_ascii=False)})
    return {"campaign": db.get_campaign(campaign_id)}


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
            parts=payload.parts,
            clips_per_part=payload.clipsPerPart,
            target_dur=payload.targetDuration,
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


def _clip_blur_ids(clip: dict) -> list[int]:
    try:
        return [int(i) for i in json.loads(clip.get("blurPersons") or "[]")]
    except Exception:
        return []


def _clip_focus_plan(clip: dict) -> str:
    """Convierte focusSegments (JSON) al formato compacto 't0:t1:pid[:cx],...' del
    render. `cx` (0-1) = punto manual clicado en el frame; si está, manda sobre pid."""
    try:
        segs = json.loads(clip.get("focusSegments") or "[]")
    except Exception:
        return ""
    parts = []
    for s in segs:
        cx = s.get("cx")
        base = f"{s['start']}:{s['end']}:{int(s.get('personId', -1))}"
        parts.append(f"{base}:{float(cx):.4f}" if cx is not None else base)
    return ",".join(parts)


def _clip_facecam(clip: dict) -> dict | None:
    """Facecam de la campaña del clip (rect + zoom), para el encuadre 'facecam'."""
    campaign = db.get_campaign_by_transcript(clip.get("transcriptPath") or "")
    fc = (campaign or {}).get("facecam")
    if isinstance(fc, dict) and fc.get("w", 0) > 0.02 and fc.get("h", 0) > 0.02:
        return fc
    return None


def _clip_watermark(clip: dict) -> str:
    """Ruta ABSOLUTA del watermark de la campaña del clip (si tiene y existe), para
    pasarlo a render_clip. '' si no hay."""
    campaign = db.get_campaign_by_transcript(clip.get("transcriptPath") or "")
    wm = (campaign or {}).get("watermarkPath") or ""
    if not wm:
        return ""
    p = ROOT_DIR / wm
    return str(p) if p.exists() else ""


def _clip_manual_blur(clip: dict) -> list[list[float]]:
    """Regiones manuales fijas [[x,y,w,h],...] normalizadas al frame fuente."""
    try:
        regs = json.loads(clip.get("manualBlur") or "[]")
    except Exception:
        return []
    out = []
    for r in regs:
        try:
            box = [float(r["x"]), float(r["y"]), float(r["w"]), float(r["h"])]
        except (TypeError, KeyError, ValueError):
            continue
        if box[2] > 0.005 and box[3] > 0.005:
            out.append(box)
    return out


def _annotate_clip(clip: dict) -> dict:
    rendered_path = clip.get("renderedPath") or ""
    clip["rendered"] = bool(rendered_path) and (ROOT_DIR / rendered_path).exists()
    clip["uploaded"] = bool(clip.get("youtubeUrl"))
    # ¿Hay detección de personas cacheada para este tramo? (para restaurar el panel
    # al recargar sin volver a detectar).
    clip["hasPersons"] = False
    video_rel = clip.get("videoPath") or ""
    if video_rel:
        tag = f"{clip.get('id')}_{int(float(clip.get('start', 0)))}_{int(float(clip.get('end', 0)))}"
        cdir = (ROOT_DIR / video_rel).parent / "clips"
        clip["hasPersons"] = (cdir / f"pdisplay_{tag}_{PTHUMB_VER}.json").exists() or (cdir / f"persons_{tag}.json").exists()
    return clip


@app.get("/api/clips/list")
def list_saved_clips(transcriptPath: str) -> dict:
    return {"clips": [_annotate_clip(c) for c in db.load_clips(transcriptPath)]}


class ClipTrimRequest(BaseModel):
    start: float = Field(..., ge=0)
    end: float = Field(..., gt=0)


@app.patch("/api/clips/{clip_id}/trim")
def trim_clip_endpoint(clip_id: str, payload: ClipTrimRequest) -> dict:
    if not db.get_clip(clip_id):
        raise HTTPException(status_code=404, detail="Clip no encontrado")
    if payload.end - payload.start < 1:
        raise HTTPException(status_code=400, detail="El clip debe durar al menos 1 segundo.")
    if payload.end - payload.start > 180:
        raise HTTPException(status_code=400, detail="El clip no puede durar mas de 180 segundos.")
    db.update_clip(clip_id, {"start": round(payload.start, 2), "end": round(payload.end, 2)})
    return _annotate_clip(db.get_clip(clip_id))


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
        "endcard_percent": payload.endcardPercent,
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
    channel_id = clip.get("channelId") or channel_id_from_path(video_rel)
    channel = db.get_channel(channel_id) if channel_id else None
    lang = (channel or {}).get("language", "es") or "es"
    # Encuadre facecam: usa el rect de la campaña; --focus va a 'center' (facecam manda).
    facecam = _clip_facecam(clip) if clip.get("focus") == "facecam" else None
    args = [
        "--video", video_rel,
        "--start", f"{clip['start']:.3f}",
        "--end", f"{clip['end']:.3f}",
        "--out", out_rel,
        "--top-ratio", f"{clip['topRatio']:.2f}",
        "--focus", "center" if facecam else clip["focus"],
        "--zoom", f"{clip['zoom']:.2f}",
        "--lang", lang,
    ]
    if facecam:
        args.extend(["--facecam", f"{facecam['x']},{facecam['y']},{facecam['w']},{facecam['h']}",
                     "--screen-zoom", str(facecam.get("zoom", 1.4))])
    if clip["subtitles"]:
        args.append("--subtitles")
    if clip.get("overlayText"):
        args.extend(["--overlay", clip["overlayText"]])
    if clip.get("endcardPercent"):
        args.extend(["--endcard", str(clip["endcardPercent"])])
    blur_ids = _clip_blur_ids(clip)
    focus_person = int(clip.get("focusPerson", -1) or -1)
    focus_plan = _clip_focus_plan(clip)
    if blur_ids or focus_person >= 0 or focus_plan:
        tag = f"{clip_id}_{int(clip['start'])}_{int(clip['end'])}"
        persons_json = (ROOT_DIR / video_rel).parent / "clips" / f"persons_{tag}.json"
        if persons_json.exists():
            args.extend(["--persons-json", str(persons_json)])
            if blur_ids:
                args.extend(["--blur-persons", ",".join(str(i) for i in blur_ids)])
        # El enfoque por tramo puede llevar puntos manuales (cx): no requiere detección.
        if focus_plan:
            args.extend(["--focus-plan", focus_plan])
        elif focus_person >= 0 and persons_json.exists():
            args.extend(["--focus-person", str(focus_person)])
    manual_blur = _clip_manual_blur(clip)
    if manual_blur:
        args.extend(["--manual-blur", json.dumps(manual_blur)])
    watermark = _clip_watermark(clip)
    if watermark:
        args.extend(["--watermark", watermark])

    db.update_clip(clip_id, {"rendered_path": out_rel})
    job = enqueue_job("render_clip.py", args)
    return {"job": job, "renderedPath": out_rel}


class RenderAllRequest(BaseModel):
    transcriptPath: str
    focus: str | None = None


@app.post("/api/clips/render-all")
def render_all_endpoint(payload: RenderAllRequest) -> dict:
    """Encola en el BACKEND el render de todos los clips pendientes de la
    transcripcion (un solo job). Sobrevive a recargas del navegador."""
    clips = db.load_clips(payload.transcriptPath)
    if not clips:
        raise HTTPException(status_code=400, detail="No hay clips para esta transcripcion.")
    args = ["--transcript", payload.transcriptPath]
    if payload.focus in ("left", "center", "right", "follow", "facecam"):
        args += ["--focus", payload.focus]
    job = enqueue_job("render_all.py", args)
    return {"job": job}


@app.post("/api/clips/render-all/stop")
def stop_render_all() -> dict:
    """Para la cola: mata el/los job(s) render_all en marcha y todo su árbol de
    procesos (render_clip + ffmpeg). Los clips a medias quedan sin generar."""
    with jobs_lock:
        targets = [(jid, p) for jid, p in list(running_procs.items())
                   if jid in jobs and jobs[jid].script == "render_all.py"]
    stopped = []
    for jid, proc in targets:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)  # grupo entero
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        with jobs_lock:
            j = jobs.get(jid)
            if j and j.status in ("running", "queued"):
                j.status = "failed"
                j.return_code = -1
                j.ended_at = now_iso()
                db.save_job(j)
            running_procs.pop(jid, None)
        stopped.append(jid)
    return {"stopped": stopped}


@app.post("/api/clips/{clip_id}/frames")
def extract_clip_frames(clip_id: str) -> dict:
    """Extrae 3 fotogramas (25/50/75%) del clip renderizado para elegir la miniatura."""
    clip = db.get_clip(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip no encontrado")
    rendered = clip.get("renderedPath") or ""
    rendered_abs = ROOT_DIR / rendered
    if not rendered or not rendered_abs.exists():
        raise HTTPException(status_code=400, detail="Renderiza el clip antes de elegir la miniatura.")

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(rendered_abs)],
        capture_output=True, text=True,
    )
    try:
        duration = float(probe.stdout.strip())
    except ValueError:
        duration = 0.0

    frames_dir = rendered_abs.parent / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    result = []
    for percent in (25, 50, 75):
        out = frames_dir / f"clip_{clip_id}_f{percent}.jpg"
        t = max(0.0, duration * percent / 100)
        subprocess.run(
            ["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(rendered_abs), "-frames:v", "1", "-q:v", "3", str(out)],
            capture_output=True,
        )
        if out.exists():
            result.append({"percent": percent, "path": str(out.relative_to(ROOT_DIR))})
    return {"frames": result}


# Versión del recorte de thumbnail. Súbela si cambias _head_crop_vf: invalida los
# thumbnails y el pdisplay cacheados (se regeneran sin re-lanzar YOLO).
PTHUMB_VER = "v2"


def _head_crop_vf(x: float, y: float, w: float, h: float, scale: int) -> str:
    """Filtro ffmpeg que recorta CABEZA+HOMBROS (parte superior de la caja de la
    persona), no la caja entera. Las cajas de YOLO suelen ser de cuerpo entero
    (altas); con `object-fit: cover` en una miniatura cuadrada se vería el torso.
    Recortando la parte de arriba la miniatura muestra la cara y es reconocible."""
    cw = max(w, 0.02)
    ch = max(min(h, max(w, 0.15) * 1.15), 0.02)  # alto ~ ancho (retrato de cabeza)
    return (f"crop='min(iw-2,iw*{cw:.4f})':'min(ih-2,ih*{ch:.4f})'"
            f":'iw*{max(x, 0):.4f}':'ih*{max(y, 0):.4f}',scale={scale}:-1")


@app.post("/api/clips/{clip_id}/persons")
def detect_clip_persons(clip_id: str, force: bool = False) -> dict:
    """Detecta personas en el tramo del clip (worker YOLO) y devuelve cada una con
    su miniatura (para el panel de blur/enfoque). Cachea la detección.
    Con force=true borra la caché y vuelve a detectar (botón "Re-detectar")."""
    from .services import person_client

    clip = db.get_clip(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip no encontrado")
    video_rel = clip.get("videoPath") or ""
    if not video_rel:
        raise HTTPException(status_code=400, detail="El clip no tiene vídeo asociado.")
    video_abs = resolve_within_root(video_rel)
    start, end = float(clip["start"]), float(clip["end"])

    clips_dir = video_abs.parent / "clips"
    tag = f"{clip_id}_{int(start)}_{int(end)}"
    cache_json = clips_dir / f"persons_{tag}.json"
    display_json = clips_dir / f"pdisplay_{tag}_{PTHUMB_VER}.json"
    if force:
        cache_json.unlink(missing_ok=True)
        display_json.unlink(missing_ok=True)
    # Caché de la RESPUESTA (personas + tramos con thumbnails): permite restaurar
    # el panel al recargar sin re-generar thumbnails ni re-detectar.
    elif display_json.exists():
        try:
            return json.loads(display_json.read_text(encoding="utf-8"))
        except Exception:
            pass
    detection = person_client.detect(video_abs, start, end, cache_json)
    if not detection:
        raise HTTPException(status_code=502, detail="Worker de personas no disponible (¿encendido el Windows?).")

    thumbs_dir = clips_dir / f"pthumbs_{tag}"
    thumbs_dir.mkdir(parents=True, exist_ok=True)
    persons = []
    for p in detection.get("persons", []):
        x, y, w, h = p["repr_bbox_norm"]
        t = start + float(p.get("repr_time", 0))
        out = thumbs_dir / f"person_{p['id']}_{PTHUMB_VER}.jpg"
        vf = _head_crop_vf(x, y, w, h, 360)
        if not out.exists():  # idempotente: no regenerar si ya está (restauración barata)
            subprocess.run(["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(video_abs),
                            "-vf", vf, "-frames:v", "1", "-q:v", "3", str(out)], capture_output=True)
        persons.append({
            "id": p["id"],
            "thumb": str(out.relative_to(ROOT_DIR)) if out.exists() else "",
            "frames": p.get("frames", 0),
        })

    segments = _scene_segments(video_abs, start, end)
    fps = float(detection.get("fps", 25.0)) or 25.0
    seg_out = []
    for si, (t0, t1) in enumerate(segments):
        seg_persons = []
        auto_id, auto_area = -1, -1.0
        for p in detection.get("persons", []):
            boxes = [b for b in p.get("boxes", []) if t0 <= b[0] / fps < t1]
            if not boxes:
                continue
            best = max(boxes, key=lambda b: b[3] * b[4])  # frame donde sale más grande
            area = best[3] * best[4]
            # thumbnail de ESA persona en ESE plano (no la global).
            x, y, w, h = best[1], best[2], best[3], best[4]
            st = thumbs_dir / f"seg{si}_person_{p['id']}_{PTHUMB_VER}.jpg"
            tt = start + best[0] / fps
            vf = _head_crop_vf(x, y, w, h, 160)
            if not st.exists():  # idempotente
                subprocess.run(["ffmpeg", "-y", "-ss", f"{tt:.2f}", "-i", str(video_abs),
                                "-vf", vf, "-frames:v", "1", "-q:v", "3", str(st)], capture_output=True)
            seg_persons.append({"id": p["id"], "thumb": str(st.relative_to(ROOT_DIR)) if st.exists() else ""})
            if area > auto_area:
                auto_area, auto_id = area, p["id"]
        seg_out.append({"start": round(t0, 2), "end": round(t1, 2),
                        "autoPersonId": auto_id, "persons": seg_persons})
    result = {"persons": persons, "segments": seg_out}
    try:
        display_json.write_text(json.dumps(result), encoding="utf-8")
    except Exception:
        pass
    return result


def _scene_segments(video_abs: Path, start: float, end: float, min_len: float = 1.2) -> list[tuple[float, float]]:
    """Divide el tramo [start,end] en 'movimientos' por cortes de cámara (ffmpeg scene).
    Devuelve segmentos en tiempo LOCAL del clip. Fusiona los muy cortos."""
    dur = round(end - start, 3)
    proc = subprocess.run(
        ["ffmpeg", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(video_abs),
         "-vf", "select='gt(scene,0.35)',showinfo", "-an", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    cuts = sorted({round(float(m), 2) for m in re.findall(r"pts_time:([0-9.]+)", proc.stderr)
                   if 0.3 < float(m) < dur - 0.3})
    bounds = [0.0] + cuts + [dur]
    raw = [(bounds[i], bounds[i + 1]) for i in range(len(bounds) - 1)]
    merged: list[list[float]] = []
    for s, e in raw:
        if merged and (e - s) < min_len:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    return [(round(s, 2), round(e, 2)) for s, e in merged] or [(0.0, dur)]


def _segment_persons(detection: dict, t0: float, t1: float, fps: float):
    """Personas presentes en un tramo + la 'auto' (la de mayor área media = la que la
    cámara enmarca más prominente, normalmente quien habla)."""
    avg_area = {}
    for p in detection.get("persons", []):
        areas = [b[3] * b[4] for b in p.get("boxes", []) if t0 <= b[0] / fps < t1]
        if areas:
            avg_area[p["id"]] = sum(areas) / len(areas)
    if not avg_area:
        return [], -1
    auto = max(avg_area, key=avg_area.get)
    return sorted(avg_area.keys()), auto


class BlurPersonsRequest(BaseModel):
    personIds: list[int] = []


@app.post("/api/clips/{clip_id}/blur-persons")
def set_clip_blur_persons(clip_id: str, payload: BlurPersonsRequest) -> dict:
    """Guarda qué personas (ids del panel) hay que blurear en este clip."""
    if not db.get_clip(clip_id):
        raise HTTPException(status_code=404, detail="Clip no encontrado")
    db.update_clip(clip_id, {"blur_persons": json.dumps(payload.personIds)})
    return {"blurPersons": payload.personIds}


@app.post("/api/clips/{clip_id}/scene-frame")
def clip_scene_frame(clip_id: str, t: float | None = None) -> dict:
    """Extrae un fotograma del vídeo FUENTE para dibujar encima (región manual de
    blur o punto de enfoque). `t` = segundos DESDE el inicio del clip (por defecto,
    la mitad). Las coordenadas del frontend van normalizadas a ESTE frame."""
    clip = db.get_clip(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip no encontrado")
    video_rel = clip.get("videoPath") or ""
    if not video_rel:
        raise HTTPException(status_code=400, detail="El clip no tiene vídeo asociado.")
    video_abs = resolve_within_root(video_rel)
    start, end = float(clip["start"]), float(clip["end"])
    if t is None:
        at = start + (end - start) / 2.0
    else:
        at = min(max(start + float(t), start), max(start, end - 0.1))

    clips_dir = video_abs.parent / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    out = clips_dir / f"scene_{clip_id}_{int(start)}_{int(end)}_{int(at)}.jpg"
    subprocess.run(["ffmpeg", "-y", "-ss", f"{at:.2f}", "-i", str(video_abs),
                    "-frames:v", "1", "-q:v", "3", "-vf", "scale=720:-1", str(out)],
                   capture_output=True)
    if not out.exists():
        raise HTTPException(status_code=500, detail="No se pudo extraer el fotograma.")
    return {"frame": str(out.relative_to(ROOT_DIR))}


class ManualBlurRegion(BaseModel):
    x: float
    y: float
    w: float
    h: float


class ManualBlurRequest(BaseModel):
    regions: list[ManualBlurRegion] = []


@app.post("/api/clips/{clip_id}/manual-blur")
def set_clip_manual_blur(clip_id: str, payload: ManualBlurRequest) -> dict:
    """Guarda las regiones manuales fijas (normalizadas [0,1]) a difuminar en todo
    el clip. Se recortan a [0,1] y se descartan las diminutas."""
    if not db.get_clip(clip_id):
        raise HTTPException(status_code=404, detail="Clip no encontrado")
    regions = []
    for r in payload.regions:
        x = min(max(r.x, 0.0), 1.0)
        y = min(max(r.y, 0.0), 1.0)
        w = min(max(r.w, 0.0), 1.0 - x)
        h = min(max(r.h, 0.0), 1.0 - y)
        if w > 0.005 and h > 0.005:
            regions.append({"x": round(x, 4), "y": round(y, 4), "w": round(w, 4), "h": round(h, 4)})
    db.update_clip(clip_id, {"manual_blur": json.dumps(regions)})
    return {"manualBlur": regions}


class FocusPersonRequest(BaseModel):
    personId: int = -1


@app.post("/api/clips/{clip_id}/focus-person")
def set_clip_focus_person(clip_id: str, payload: FocusPersonRequest) -> dict:
    """Guarda sobre qué persona centra el recorte de arriba (-1 = automático/normal)."""
    if not db.get_clip(clip_id):
        raise HTTPException(status_code=404, detail="Clip no encontrado")
    db.update_clip(clip_id, {"focus_person": payload.personId})
    return {"focusPerson": payload.personId}


class FocusSegment(BaseModel):
    start: float
    end: float
    personId: int = -1
    cx: float | None = None  # punto manual clicado en el frame (0-1); manda sobre personId


class FocusPlanRequest(BaseModel):
    segments: list[FocusSegment] = []


@app.post("/api/clips/{clip_id}/focus-plan")
def set_clip_focus_plan(clip_id: str, payload: FocusPlanRequest) -> dict:
    """Guarda el enfoque POR TRAMO: por cada movimiento, qué persona centrar (o un
    punto manual `cx` clicado en el frame, útil en planos generales)."""
    if not db.get_clip(clip_id):
        raise HTTPException(status_code=404, detail="Clip no encontrado")
    plan = []
    for s in payload.segments:
        item = {"start": s.start, "end": s.end, "personId": s.personId}
        if s.cx is not None:
            item["cx"] = round(min(max(s.cx, 0.0), 1.0), 4)
        plan.append(item)
    db.update_clip(clip_id, {"focus_segments": json.dumps(plan)})
    return {"focusSegments": plan}


# ---------------------------------------------------------------------------
# Avatar Reel (contenido propio con IA): guion + voz clonada. El avatar (HeyGen)
# y el b-roll generado (ComfyUI/LTX) llegan en fases posteriores.
# ---------------------------------------------------------------------------
@app.get("/api/reels/voices")
def reel_voices() -> dict:
    from .services import tts_client
    return {"voices": tts_client.list_voices(), "ttsUrl": os.environ.get("LOCAL_TTS_URL") or "http://192.168.1.46:8022"}


class ReelScriptRequest(BaseModel):
    trigger: str
    angle: str = ""
    seconds: int = 40
    toneExamples: str = ""


@app.post("/api/reels/script")
def reel_script(payload: ReelScriptRequest) -> dict:
    from .services.reel_engine import generate_script
    if not payload.trigger.strip():
        raise HTTPException(status_code=400, detail="Pon un disparador (tema, noticia, idea).")
    try:
        script = generate_script(payload.trigger, payload.angle, payload.seconds, payload.toneExamples)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Fallo generando el guion: {exc}") from exc
    return {"script": script}


class ReelVoiceRequest(BaseModel):
    script: str
    voiceId: str
    language: str | None = None
    trigger: str = ""
    reelId: str = ""


@app.post("/api/reels/voice")
def reel_voice(payload: ReelVoiceRequest) -> dict:
    from .services import tts_client
    if not payload.script.strip():
        raise HTTPException(status_code=400, detail="No hay guion que locutar.")
    if not payload.voiceId.strip():
        raise HTTPException(status_code=400, detail="Elige una voz.")
    out_dir = ROOT_DIR / "output" / "reels"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"reel_{uuid.uuid4().hex[:10]}.mp3"
    try:
        tts_client.synthesize(payload.script, payload.voiceId, out, payload.language)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Fallo generando la voz (¿TTS encendido en el Windows?): {exc}") from exc
    audio_rel = str(out.relative_to(ROOT_DIR))
    # Guarda/actualiza la generación (Mis Generaciones) para no perderla al recargar.
    reel_id = payload.reelId or uuid.uuid4().hex[:12]
    if db.get_reel(reel_id):
        db.update_reel(reel_id, {"script": payload.script, "voice_id": payload.voiceId,
                                 "audio_path": audio_rel, "trigger": payload.trigger, "video_path": ""})
    else:
        db.save_reel({"id": reel_id, "trigger": payload.trigger, "script": payload.script,
                      "voiceId": payload.voiceId, "audio": audio_rel, "createdAt": now_iso()})
    return {"audio": audio_rel, "reelId": reel_id}


@app.get("/api/reels")
def reels_list() -> dict:
    return {"reels": db.list_reels()}


class ReelBrollRequest(BaseModel):
    reelId: str
    subtitles: bool = True
    title: str = ""


@app.post("/api/reels/broll")
def reel_broll(payload: ReelBrollRequest) -> dict:
    """Encola un JOB que genera el b-roll con ComfyUI (prompts del guion → imágenes)
    y compone el reel (slideshow + karaoke + voz). Como job, sobrevive a recargas.
    Usa la GPU del Windows (ComfyUI). El frontend refresca la generación al terminar."""
    from .services import comfy_client
    reel = db.get_reel(payload.reelId)
    if not reel or not reel.get("audio"):
        raise HTTPException(status_code=400, detail="La generación no tiene audio.")
    if not comfy_client.is_up():
        raise HTTPException(status_code=502, detail="ComfyUI no responde (¿encendido en el Windows y la GPU libre?).")
    args = ["--reel", payload.reelId]
    if payload.title.strip():
        args += ["--title", payload.title.strip()]
    if not payload.subtitles:
        args.append("--no-subtitles")
    job = enqueue_job("reel_broll.py", args)
    return {"job": job}


class ReelMatchRequest(BaseModel):
    url: str
    voiceId: str
    lang: str = "auto"
    moments: int = 6
    seconds: int = 45


@app.post("/api/reels/match")
def reel_match(payload: ReelMatchRequest) -> dict:
    """Encola un JOB que crea un reel explicativo a partir del resumen de un partido
    (enlace de YouTube): descarga → transcribe → momentos clave → guion → voz →
    fotogramas reales recortados a vertical → composición. Crea ya la generación
    para verla en 'Mis generaciones' mientras se procesa."""
    if not payload.url.strip():
        raise HTTPException(status_code=400, detail="Falta el enlace del partido.")
    if not payload.voiceId.strip():
        raise HTTPException(status_code=400, detail="Elige una voz para la narración.")
    reel_id = uuid.uuid4().hex[:12]
    db.save_reel({"id": reel_id, "trigger": payload.url.strip(), "script": "",
                  "voiceId": payload.voiceId, "audio": "", "createdAt": now_iso()})
    args = ["--reel", reel_id, "--url", payload.url.strip(), "--voice", payload.voiceId,
            "--lang", payload.lang or "auto", "--moments", str(max(3, min(12, payload.moments))),
            "--seconds", str(max(20, min(90, payload.seconds)))]
    job = enqueue_job("reel_match.py", args)
    return {"job": job, "reelId": reel_id}


@app.post("/api/reels/{reel_id}/render")
def reel_render(reel_id: str) -> dict:
    """Re-monta el vídeo de un reel de partido reusando el guion+voz ya generados y el
    vídeo del partido descargado (solo fotogramas + composición). No rehace descarga/
    transcripción/guion/voz. Job asíncrono; el frontend refresca al terminar."""
    reel = db.get_reel(reel_id)
    if not reel:
        raise HTTPException(status_code=404, detail="Generación no encontrada.")
    if not reel.get("audio") or not (ROOT_DIR / reel["audio"]).exists():
        raise HTTPException(status_code=400, detail="El reel no tiene voz generada todavía.")
    if not reel.get("sourceVideo") or not (ROOT_DIR / reel["sourceVideo"]).exists():
        raise HTTPException(status_code=400, detail="No hay vídeo del partido guardado; usa «Crear reel del partido».")
    job = enqueue_job("reel_match.py", ["--reel", reel_id, "--render-only"])
    return {"job": job}


@app.delete("/api/reels/{reel_id}")
def reels_delete(reel_id: str) -> dict:
    reel = db.get_reel(reel_id)
    if reel:
        for rel in (reel.get("audio"), reel.get("video")):
            if rel:
                try:
                    (ROOT_DIR / rel).unlink(missing_ok=True)
                except Exception:
                    pass
        db.delete_reel(reel_id)
    return {"deleted": reel_id}


@app.post("/api/reels/{reel_id}/hook")
def reel_hook(reel_id: str) -> dict:
    from .services.reel_engine import hook_text, content_text
    reel = db.get_reel(reel_id)
    if not reel:
        raise HTTPException(status_code=404, detail="Generación no encontrada.")
    try:
        text = content_text(reel, ROOT_DIR)  # transcribe si el guion está vacío (recuperados)
        if text and not (reel.get("script") or "").strip():
            db.update_reel(reel_id, {"script": text})  # backfill para futuras operaciones
        return {"hook": hook_text(text)}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Fallo generando el gancho: {exc}") from exc


class ReelSeoRequest(BaseModel):
    channelId: int | None = None


def _reel_seo_context(reel_id: str, channel_id: int | None):
    """(texto del reel, reglas SEO del canal) para generar título/descripción. Transcribe
    el audio si el guion está vacío (reels recuperados) y lo persiste."""
    reel = db.get_reel(reel_id)
    if not reel:
        raise HTTPException(status_code=404, detail="Generación no encontrada.")
    from .services.reel_engine import content_text
    text = content_text(reel, ROOT_DIR)
    if text and not (reel.get("script") or "").strip():
        db.update_reel(reel_id, {"script": text})
    ch_id = channel_id if channel_id is not None else reel.get("channelId")
    rules = None
    if ch_id:
        ch = db.get_channel(int(ch_id))
        rules = (ch or {}).get("seoRules") or None
    return reel, text, rules


@app.post("/api/reels/{reel_id}/seo/title")
def reel_seo_title(reel_id: str, payload: ReelSeoRequest) -> dict:
    """Genera un título SEO (alto CTR) con IA desde el contenido del reel y lo guarda."""
    _, text, rules = _reel_seo_context(reel_id, payload.channelId)
    from .services.seo_engine import SEOEngine
    from .services.clip_seo import strip_wrapping_quotes, strip_markdown
    try:
        title = strip_wrapping_quotes(strip_markdown(SEOEngine().generate_video_title(text, custom_rules=rules)))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Fallo generando el título: {exc}") from exc
    db.update_reel(reel_id, {"title": title})
    return {"title": title}


@app.post("/api/reels/{reel_id}/seo/description")
def reel_seo_description(reel_id: str, payload: ReelSeoRequest) -> dict:
    """Genera una descripción SEO con IA desde el contenido del reel y la guarda. La
    descripción NO incluye título; al final se añade el enlace del VÍDEO ORIGINAL
    (la URL de YouTube del resumen/fuente, guardada en el disparador) si existe."""
    reel, text, rules = _reel_seo_context(reel_id, payload.channelId)
    from .services.seo_engine import SEOEngine
    from .services.clip_seo import strip_markdown
    import re as _re
    # Instruye al modelo para que NO escriba ningún título/encabezado (más fiable que
    # limpiarlo a posteriori); se suma a las reglas del canal si las hay.
    no_title = ("NO escribas ningún título, encabezado ni etiquetas como 'Título:', "
                "'Descripción:', 'Descripción del vídeo:' ni almohadillas '#'. Empieza "
                "directamente por el cuerpo de la descripción.")
    rules_combined = f"{rules}\n\n{no_title}" if rules else no_title
    try:
        desc = strip_markdown(SEOEngine().generate_description(text, custom_rules=rules_combined))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Fallo generando la descripción: {exc}") from exc
    # Respaldo: si aún así cuela un encabezado "Título ...:" / "Descripción ...:" o
    # una línea markdown al principio, la quitamos.
    desc = _re.sub(r"^\s*(v[ií]deo\s+)?(t[ií]tulo|title)\b[^\n]*:\s*(?:\n+|)", "", desc, flags=_re.IGNORECASE)
    desc = _re.sub(r"^\s*(descripci[oó]n|description)\b[^\n]*:\s*(?:\n+|)", "", desc, flags=_re.IGNORECASE)
    desc = _re.sub(r"^\s*#{1,6}\s*.*(?:\n+|$)", "", desc)  # encabezado markdown
    title = (reel.get("title") or "").strip()
    if title:  # si la 1ª línea repite el título del vídeo, quítala
        first, _, rest = desc.lstrip().partition("\n")
        if first.strip().strip("*_\"'").lower() == title.lower():
            desc = rest
    desc = desc.strip()
    # Enlace del vídeo ORIGINAL: la URL de la fuente (disparador de los reels de partido).
    trigger = (reel.get("trigger") or "").strip()
    original = trigger if _re.match(r"https?://", trigger) else ""
    if original:
        desc = f"{desc}\n\n🎬 Vídeo original: {original}"
    db.update_reel(reel_id, {"seo_description": desc})
    return {"description": desc}


@app.post("/api/reels/{reel_id}/thumbnail-image")
async def reel_thumbnail_image(reel_id: str, file: UploadFile = File(...)) -> dict:
    """Sube una imagen propia para la miniatura del reel."""
    reel = db.get_reel(reel_id)
    if not reel or not reel.get("audio"):
        raise HTTPException(status_code=404, detail="Generación no encontrada.")
    folder = (ROOT_DIR / reel["audio"]).parent
    out = folder / f"{reel_id}_thumbimg_own.jpg"
    out.write_bytes(await file.read())
    return {"image": str(out.relative_to(ROOT_DIR))}


class ReelThumbnailRequest(BaseModel):
    hook: str = ""
    position: str = "bottom"
    image: str = ""
    regenImage: bool = False


@app.post("/api/reels/{reel_id}/thumbnail/preview")
def reel_thumbnail_preview(reel_id: str, payload: ReelThumbnailRequest) -> dict:
    """Genera la miniatura (imagen IA/propia + gancho) SIN añadirla al vídeo, para
    previsualizarla. Devuelve el path del thumb (disponible al terminar el job)."""
    reel = db.get_reel(reel_id)
    if not reel or not reel.get("video") or not (ROOT_DIR / reel["video"]).exists():
        raise HTTPException(status_code=400, detail="El reel no tiene vídeo compuesto.")
    video_abs = ROOT_DIR / reel["video"]
    thumb_rel = str(video_abs.with_name(video_abs.stem + "_thumb.jpg").relative_to(ROOT_DIR))
    pos = payload.position if payload.position in ("top", "center", "bottom") else "bottom"
    db.update_reel(reel_id, {"hook": payload.hook.strip(), "thumb_position": pos})  # persiste el gancho
    args = ["--reel", reel_id, "--mode", "preview", "--hook", payload.hook.strip(), "--position", pos]
    if payload.image.strip():
        args += ["--image", payload.image.strip()]
    if payload.regenImage:
        args.append("--regen-image")
    job = enqueue_job("reel_thumbnail.py", args)
    return {"job": job, "thumbPath": thumb_rel}


@app.post("/api/reels/{reel_id}/thumbnail/apply")
def reel_thumbnail_apply(reel_id: str) -> dict:
    """Añade la miniatura ya previsualizada al FINAL del reel."""
    reel = db.get_reel(reel_id)
    if not reel or not reel.get("video") or not (ROOT_DIR / reel["video"]).exists():
        raise HTTPException(status_code=400, detail="El reel no tiene vídeo compuesto.")
    job = enqueue_job("reel_thumbnail.py", ["--reel", reel_id, "--mode", "append"])
    return {"job": job}


class ReelUploadRequest(BaseModel):
    channelId: int
    privacy: str = "public"


@app.post("/api/reels/{reel_id}/upload")
def reel_upload(reel_id: str, payload: ReelUploadRequest) -> dict:
    """Sube el reel al canal elegido (job). Genera SEO desde el guion."""
    reel = db.get_reel(reel_id)
    if not reel or not reel.get("video") or not (ROOT_DIR / reel["video"]).exists():
        raise HTTPException(status_code=400, detail="El reel no tiene vídeo compuesto.")
    if not db.get_channel(payload.channelId):
        raise HTTPException(status_code=404, detail="Canal no encontrado.")
    privacy = payload.privacy if payload.privacy in ("private", "unlisted", "public") else "public"
    job = enqueue_job("reel_upload.py", ["--reel", reel_id, "--channel", str(payload.channelId), "--privacy", privacy])
    return {"job": job}


class ReelComposeRequest(BaseModel):
    audio: str
    title: str = ""
    subtitles: bool = True
    language: str = "es"
    reelId: str = ""


@app.post("/api/reels/compose")
def reel_compose(payload: ReelComposeRequest) -> dict:
    """Compone el vídeo vertical del reel (fondo + karaoke + audio). Sin GPU:
    ffmpeg (CPU) + AssemblyAI (nube). El avatar y el b-roll llegan en fases 2b/3."""
    audio_abs = resolve_within_root(payload.audio)
    if not audio_abs.exists():
        raise HTTPException(status_code=400, detail="No existe el audio del reel.")
    out = audio_abs.with_name(audio_abs.stem + "_video.mp4")
    script = str((Path(__file__).resolve().parents[1]) / "scripts" / "reel_compose.py")
    args = [sys.executable, script, "--audio", str(audio_abs), "--out", str(out),
            "--lang", payload.language]
    if payload.title.strip():
        args += ["--title", payload.title.strip()]
    if payload.subtitles:
        args.append("--subtitles")
    proc = subprocess.run(args, cwd=str(ROOT_DIR), capture_output=True, text=True)
    if proc.returncode != 0 or not out.exists():
        raise HTTPException(status_code=500, detail=f"Fallo componiendo el reel: {proc.stderr[-300:]}")
    video_rel = str(out.relative_to(ROOT_DIR))
    if payload.reelId and db.get_reel(payload.reelId):
        db.update_reel(payload.reelId, {"video_path": video_rel, "title": payload.title})
    return {"video": video_rel}


# ===== Vídeos de macetas (WAN plant time-lapse) =====

@app.post("/api/plants/ideas")
def plant_ideas_endpoint() -> dict:
    from .services.plant_engine import plant_ideas
    try:
        return {"ideas": plant_ideas()}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Fallo generando ideas: {exc}") from exc


def _validate_plant_provider(provider: str):
    """Valida provider y claves/servicios. Devuelve el provider normalizado."""
    from .services import comfy_client, grok_video, veo_video
    provider = provider if provider in ("grok", "veo", "wan") else "grok"
    # grok/veo hacen la 1ª imagen con grok-imagine-image → siempre hace falta GROK key.
    if provider in ("grok", "veo") and not grok_video.is_configured():
        raise HTTPException(status_code=400, detail="Falta GROK_API_KEY en .env (la imagen inicial usa Grok).")
    if provider == "veo" and not veo_video.is_configured():
        raise HTTPException(status_code=400, detail="Falta GOOGLE_API_KEY en .env para usar Veo.")
    if provider == "wan" and not comfy_client.is_up():
        raise HTTPException(status_code=502, detail="ComfyUI no responde (necesario para WAN).")
    return provider


class PlantCreateRequest(BaseModel):
    plant: str
    aspect: str = "9:16"
    provider: str = "grok"          # grok | veo | wan
    duration: int = 15              # segundos (grok/veo; máx 15)


@app.post("/api/plants")
def plant_create(payload: PlantCreateRequest) -> dict:
    """Crea UN vídeo de maceta (job): plan → primera imagen → clip(s) → montaje."""
    if not payload.plant.strip():
        raise HTTPException(status_code=400, detail="Escribe una planta.")
    provider = _validate_plant_provider(payload.provider)
    aspect = payload.aspect if payload.aspect in ("9:16", "16:9") else "9:16"
    plant_id = uuid.uuid4().hex[:12]
    db.save_plant({"id": plant_id, "plant": payload.plant.strip(), "aspect": aspect, "createdAt": now_iso()})
    args = ["--plant", plant_id, "--provider", provider, "--duration", str(max(4, min(15, payload.duration)))]
    job = enqueue_job("plant_video.py", args)
    return {"job": job, "plantId": plant_id}


class PlantBatchRequest(BaseModel):
    plants: list[str]               # una planta por elemento
    aspect: str = "9:16"
    provider: str = "grok"
    duration: int = 15


@app.post("/api/plants/batch")
def plant_batch(payload: PlantBatchRequest) -> dict:
    """Encola una TANDA de vídeos de maceta: crea un registro por planta y un único
    job que los genera EN CADENA (uno tras otro). Ideal para tandas nocturnas."""
    names = [p.strip() for p in payload.plants if p.strip()]
    if not names:
        raise HTTPException(status_code=400, detail="La lista de plantas está vacía.")
    if len(names) > 50:
        raise HTTPException(status_code=400, detail="Máximo 50 por tanda.")
    provider = _validate_plant_provider(payload.provider)
    aspect = payload.aspect if payload.aspect in ("9:16", "16:9") else "9:16"
    ids = []
    for name in names:
        pid = uuid.uuid4().hex[:12]
        db.save_plant({"id": pid, "plant": name, "aspect": aspect, "createdAt": now_iso()})
        ids.append(pid)
    args = ["--plants", ",".join(ids), "--provider", provider, "--duration", str(max(4, min(15, payload.duration)))]
    job = enqueue_job("plant_batch.py", args)
    return {"job": job, "plantIds": ids, "count": len(ids)}


@app.get("/api/plants")
def plants_list() -> dict:
    return {"plants": db.list_plants()}


@app.delete("/api/plants/{plant_id}")
def plant_delete(plant_id: str) -> dict:
    rec = db.get_plant(plant_id)
    if rec:
        import shutil
        folder = ROOT_DIR / "output" / "plants" / plant_id
        try:
            if folder.exists():
                shutil.rmtree(folder)
        except Exception:
            pass
        db.delete_plant(plant_id)
    return {"deleted": plant_id}


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


class UploadClipRequest(BaseModel):
    privacy: str = Field(default="private", pattern="^(private|unlisted|public)$")


class ClipVisibilityRequest(BaseModel):
    privacy: str = Field(..., pattern="^(private|unlisted|public)$")


@app.post("/api/clips/{clip_id}/upload")
def upload_clip_endpoint(clip_id: str, payload: UploadClipRequest | None = None) -> dict:
    payload = payload or UploadClipRequest()
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
    return enqueue_job("upload_clip.py", ["--clip", clip_id, "--privacy", payload.privacy])


@app.post("/api/clips/{clip_id}/visibility")
def set_clip_visibility(clip_id: str, payload: ClipVisibilityRequest) -> dict:
    from .services.youtube_service import YouTubeService

    clip = db.get_clip(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip no encontrado")
    url = clip.get("youtubeUrl") or ""
    match = re.search(r"[?&]v=([A-Za-z0-9_-]+)", url)
    if not match:
        raise HTTPException(status_code=400, detail="El clip no esta subido a YouTube.")
    channel_id = clip.get("channelId") or channel_id_from_path(clip.get("videoPath"))
    channel = db.get_channel(channel_id) if channel_id else None
    if not channel:
        raise HTTPException(status_code=400, detail="No se encontro el canal del clip.")
    service = YouTubeService(channel_id, YOUTUBE_CREDS_DIR)
    try:
        service.set_video_privacy(match.group(1), payload.privacy)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"No se pudo cambiar la visibilidad: {exc}") from exc
    db.update_clip(clip_id, {"youtube_privacy": payload.privacy})
    return {"privacy": payload.privacy}


class ClipSubmittedRequest(BaseModel):
    submitted: bool = True


@app.post("/api/clips/{clip_id}/submitted")
def set_clip_submitted(clip_id: str, payload: ClipSubmittedRequest) -> dict:
    """Marca/desmarca el clip como enviado (submiteado) a la campana de Whop."""
    clip = db.get_clip(clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip no encontrado")
    db.update_clip(clip_id, {"submitted": 1 if payload.submitted else 0})
    return {"submitted": payload.submitted}


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
