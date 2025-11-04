#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, os, re
from urllib.parse import urlparse, parse_qs
from yt_dlp import YoutubeDL

def get_video_id(url: str) -> str:
    u = urlparse(url)
    if u.netloc in {"youtu.be"}:
        return u.path.lstrip("/")
    qs = parse_qs(u.query)
    return qs.get("v", [re.sub(r"[^A-Za-z0-9_-]", "", u.path.strip("/")) or "video"][0])[0]

def download_mp3(url: str, ffmpeg_path: str | None = None):
    vid = get_video_id(url)
    out_dir = os.path.join("output", vid)
    os.makedirs(out_dir, exist_ok=True)

    ydl_opts = {
        "outtmpl": os.path.join(out_dir, "%(title)s.%(ext)s"),
        "format": "bestaudio/best",
        "noplaylist": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        # Si no tienes ffmpeg en PATH, descomenta y pon la ruta completa:
        # "ffmpeg_location": r"C:\ruta\a\ffmpeg\bin"  # o solo el directorio
    }
    if ffmpeg_path:
        ydl_opts["ffmpeg_location"] = ffmpeg_path

    print(f"➡️ Descargando MP3 para {url}")
    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    print(f"✅ Guardado en {out_dir}")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--ffmpeg", help="Ruta a ffmpeg si no está en PATH", default=None)
    a = p.parse_args()
    download_mp3(a.url, a.ffmpeg)
