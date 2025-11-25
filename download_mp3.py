#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, os, re
from urllib.parse import urlparse, parse_qs

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError


def get_video_id(url: str) -> str:
    u = urlparse(url)
    if u.netloc in {"youtu.be"}:
        return u.path.lstrip("/")
    qs = parse_qs(u.query)
    # ID del vídeo o un fallback
    return qs.get(
        "v",
        [re.sub(r"[^A-Za-z0-9_-]", "", u.path.strip("/")) or "video"]
    )[0]


def download_mp3(
    url: str,
    ffmpeg_path: str | None = None,
    browser: str | None = None,
) -> None:
    vid = get_video_id(url)
    out_dir = os.path.join("output", vid)
    os.makedirs(out_dir, exist_ok=True)

    ydl_opts: dict = {
        "outtmpl": os.path.join(out_dir, "%(title)s.%(ext)s"),
        "format": "bestaudio/best",
        "noplaylist": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    }

    if ffmpeg_path:
        ydl_opts["ffmpeg_location"] = ffmpeg_path

    if browser:
        # ha d’estar obert / instal·lat i amb sessió iniciada a YouTube
        ydl_opts["cookiesfrombrowser"] = (browser,)
        print(f"🍪 Usant cookies del navegador: {browser}")

    print(f"➡️ Descargando MP3 para {url}")

    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except DownloadError as e:
        msg = str(e)
        if "Sign in to confirm you're not a bot" in msg and not browser:
            print("⚠️ YouTube demana login. Torna a provar afegint, per exemple:")
            print("   --browser chrome   o   --browser firefox")
        raise SystemExit(1)

    print(f"✅ Guardado en {out_dir}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True, help="URL del vídeo de YouTube")
    p.add_argument("--ffmpeg", help="Ruta a ffmpeg si no está en PATH", default=None)
    p.add_argument(
        "--browser",
        help="Navegador per treure cookies (chrome, chromium, firefox, brave...)",
        default=None,
    )
    a = p.parse_args()
    download_mp3(a.url, a.ffmpeg, a.browser)
