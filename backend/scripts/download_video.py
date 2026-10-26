#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, json, os, re, shutil, time
from datetime import datetime
from urllib.parse import urlparse, parse_qs

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from kvs_fallback import download_direct, extract_kvs, is_flashvars_error
from wetransfer_dl import is_wetransfer, resolve_wetransfer
from gdrive_dl import download_gdrive, is_gdrive


COOKIES_DIR = "cookies"

# Esperas entre reintentos, en segundos. Largas a proposito: un 429 es un limite
# por tiempo, y reintentar a los 2 segundos solo gasta otro intento. Peor aun,
# machacar mientras te limitan alarga el bloqueo.
RETRY_WAITS = (20, 60, 180)


def _bare_host(host: str) -> str:
    host = (host or "").lower()
    return host[4:] if host.startswith("www.") else host


def find_cookies_for(url: str, cookies_dir: str = COOKIES_DIR) -> str | None:
    """Busca en `cookies/` el fichero de cookies de este sitio.

    Convencion de nombres (la que ya se usaba a mano):
    `<host>_cookies.txt`, p.ej. `www.instagram.com_cookies.txt`. Se ignora el
    `www.` al comparar, asi que ese fichero vale para instagram.com y viceversa.
    """
    host = _bare_host(urlparse(url).hostname or "")
    if not host or not os.path.isdir(cookies_dir):
        return None

    best: tuple[str, str] | None = None
    for name in sorted(os.listdir(cookies_dir)):
        if not name.endswith("_cookies.txt"):
            continue
        domain = _bare_host(name[: -len("_cookies.txt")])
        if not domain:
            continue
        # Vale el dominio exacto o uno del que el host sea subdominio.
        if host == domain or host.endswith("." + domain) or domain.endswith("." + host):
            # Ante varios, gana el mas especifico.
            if best is None or len(domain) > len(best[0]):
                best = (domain, os.path.join(cookies_dir, name))
    return best[1] if best else None


def _is_transient(message: str) -> bool:
    """¿Merece la pena reintentar? 429, cortes de red y 5xx del servidor si; que
    el video no exista o pida login, no: reintentar daria el mismo error."""
    low = message.lower()
    return any(s in low for s in (
        "429", "too many requests", "timed out", "timeout", "connection reset",
        "remote end closed", "temporarily unavailable", "http error 5",
    ))


def with_retry(action, what: str):
    """Ejecuta `action` reintentando solo los fallos que pueden pasarse solos."""
    for attempt, wait in enumerate((*RETRY_WAITS, None), start=1):
        try:
            return action()
        except DownloadError as exc:
            message = str(exc)
            if wait is None or not _is_transient(message):
                raise
            print(f"⏳ {what} falló ({message.strip()[:110]}).", flush=True)
            print(f"   Reintento {attempt}/{len(RETRY_WAITS)} en {wait}s...", flush=True)
            time.sleep(wait)


def clean_title(title: str) -> str:
    title = re.sub(r"[\U00010000-\U0010ffff]", "", title)
    title = re.sub(r"[^a-zA-Z0-9ñÑáéíóúÁÉÍÓÚüÜ_-]+", "-", title)
    title = re.sub(r"-+", "-", title)
    return title.strip("-").lower()


def get_video_title(url: str, browser=None, cookies_file=None) -> str:
    opts = {"quiet": True}
    if cookies_file:
        opts["cookiefile"] = cookies_file
    elif browser:
        opts["cookiesfrombrowser"] = (browser,)
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return info["title"]


def _write_source_metadata(out_dir, url, title, browser, cookies_file):
    with open(os.path.join(out_dir, "source_url.txt"), "w", encoding="utf-8") as handle:
        handle.write(url)
    with open(os.path.join(out_dir, "source.json"), "w", encoding="utf-8") as handle:
        json.dump(
            {
                "url": url,
                "title": title,
                "downloaded_at": datetime.now().isoformat(),
                "browser": browser or "",
                "cookies_file": cookies_file or "",
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )


def download_video(url: str, ffmpeg_path=None, browser=None, cookies_file=None, outbase="output"):

    # Si no se eligio fichero de cookies, se busca uno por el dominio de la URL.
    # Lo elegido a mano manda siempre.
    if not cookies_file:
        auto = find_cookies_for(url)
        if auto:
            cookies_file = auto
            print(f"🍪 Cookies detectadas por dominio: {auto}", flush=True)

    # 0) WeTransfer (yt-dlp no lo soporta): resolver enlace directo y descargar.
    if is_wetransfer(url):
        direct, filename = resolve_wetransfer(url)
        title = os.path.splitext(filename)[0]
        clean = clean_title(title)
        today = datetime.now().strftime("%Y-%m-%d")
        out_dir = os.path.join(outbase, f"{today}-{clean}")
        os.makedirs(out_dir, exist_ok=True)
        _write_source_metadata(out_dir, url, title, browser, cookies_file)
        print(f"➡️ Descargando de WeTransfer: {title}")
        video_path = download_direct(direct, url, out_dir, clean, ffmpeg_path=ffmpeg_path)
        print(f"✅ Vídeo guardado en: {out_dir}")
        return str(video_path), out_dir

    # 0.5) GOOGLE DRIVE (yt-dlp falla en ficheros grandes por la confirmación
    # anti-virus). gdown lo descarga con su nombre remoto; luego lo movemos a la
    # carpeta con el nombre-fecha de siempre (rename = instantáneo, mismo disco).
    if is_gdrive(url):
        staging = os.path.join(outbase, "_gdrive_tmp")
        print(f"➡️ Descargando de Google Drive (puede tardar en ficheros grandes)...")
        downloaded = download_gdrive(url, staging)
        title = downloaded.stem
        clean = clean_title(title) or "gdrive-video"
        today = datetime.now().strftime("%Y-%m-%d")
        out_dir = os.path.join(outbase, f"{today}-{clean}")
        os.makedirs(out_dir, exist_ok=True)
        final = os.path.join(out_dir, f"{clean}{downloaded.suffix or '.mp4'}")
        os.replace(str(downloaded), final)
        shutil.rmtree(staging, ignore_errors=True)  # limpia subcarpeta y otros ficheros
        _write_source_metadata(out_dir, url, title, browser, cookies_file)
        print(f"✅ Vídeo (Drive) guardado en: {out_dir}")
        return final, out_dir

    # 1) TÍTULO (con fallback KVS si yt-dlp no reconoce el reproductor)
    kvs_formats = None
    try:
        title = with_retry(lambda: get_video_title(url, browser, cookies_file),
                           "Obtener el título")
    except DownloadError as exc:
        if not is_flashvars_error(str(exc)):
            raise
        print("Sitio KVS detectado; usando extraccion directa (fallback).")
        title, kvs_formats = extract_kvs(url, cookies_file)
    clean = clean_title(title)

    # 2) FECHA
    today = datetime.now().strftime("%Y-%m-%d")
    folder_name = f"{today}-{clean}"
    out_dir = os.path.join(outbase, folder_name)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "source_url.txt"), "w", encoding="utf-8") as handle:
        handle.write(url)
    with open(os.path.join(out_dir, "source.json"), "w", encoding="utf-8") as handle:
        json.dump(
            {
                "url": url,
                "title": title,
                "downloaded_at": datetime.now().isoformat(),
                "browser": browser or "",
                "cookies_file": cookies_file or "",
            },
            handle,
            ensure_ascii=False,
            indent=2,
        )

    # 3) OPCIONES YT-DLP (VÍDEO)
    # Formato: preferimos H.264 (avc1) + audio m4a de los clientes WEB (que deno
    # firma con nsig). Evita que "bestvideo" coja el formato del cliente android_vr,
    # cuyas URLs dan HTTP 403, o los del cliente tv, marcados como DRM. Cae a best
    # mp4/best para fuentes no-YouTube (Twitch VOD, etc.).
    ydl_opts = {
        "outtmpl": os.path.join(out_dir, "%(title)s.%(ext)s"),
        "format": "bestvideo[vcodec^=avc1][height<=1080]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "extractor_args": {"youtube": {"player_client": ["default"]}},
    }

    if ffmpeg_path:
        ydl_opts["ffmpeg_location"] = ffmpeg_path

    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file
    elif browser:
        ydl_opts["cookiesfrombrowser"] = (browser,)
        print(f"🍪 Usando cookies del navegador: {browser}")

    print(f"➡️ Descargando vídeo: {title}")

    # 4) DESCARGA. Devuelve (ruta_video, carpeta).
    if kvs_formats:
        best = kvs_formats[-1]
        print(f"Descargando vídeo (KVS {best['format_id']})")
        video_path = download_direct(best["url"], url, out_dir, clean, ffmpeg_path=ffmpeg_path)
        print(f"✅ Vídeo guardado en: {out_dir}")
        return str(video_path), out_dir

    def _download():
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

    try:
        with_retry(_download, "Descargar el vídeo")
    except DownloadError as e:
        msg = str(e)
        if is_flashvars_error(msg):
            print("Sitio KVS detectado; usando extraccion directa (fallback).")
            _, kvs_formats = extract_kvs(url, cookies_file)
            best = kvs_formats[-1]
            video_path = download_direct(best["url"], url, out_dir, clean, ffmpeg_path=ffmpeg_path)
            print(f"✅ Vídeo guardado en: {out_dir}")
            return str(video_path), out_dir
        if "Sign in to confirm you're not a bot" in msg and not browser:
            print("⚠️ YouTube pide login. Usa --browser chrome / firefox / brave")
        if "empty media response" in msg.lower() and not cookies_file:
            host = _bare_host(urlparse(url).hostname or "")
            print(f"⚠️ {host} pide sesión iniciada para este contenido. Exporta tus "
                  f"cookies y guárdalas como cookies/{host}_cookies.txt: se cogerán solas.")
        raise SystemExit(1)

    print(f"✅ Vídeo guardado en: {out_dir}")
    return _newest_video(out_dir), out_dir


def _newest_video(out_dir: str):
    import glob
    videos = [
        path
        for ext in ("mp4", "mkv", "webm", "mov")
        for path in glob.glob(os.path.join(out_dir, f"*.{ext}"))
    ]
    if not videos:
        return None
    return max(videos, key=os.path.getmtime)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--ffmpeg", default=None)
    p.add_argument("--browser", default=None)
    p.add_argument("--cookies", default=None)
    a = p.parse_args()
    video_path, _ = download_video(a.url, a.ffmpeg, a.browser, a.cookies)
    # Marca que lee la UI para ofrecer el fichero sin volver al sitio de origen.
    # Relativa a la raiz del proyecto, que es lo que espera /api/file.
    if video_path:
        print(f"VIDEO_PATH: {os.path.relpath(video_path, os.getcwd())}", flush=True)
