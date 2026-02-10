#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, os, re
from datetime import datetime
from urllib.parse import urlparse, parse_qs

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError


def clean_title(title: str) -> str:
    title = re.sub(r"[\U00010000-\U0010ffff]", "", title)
    title = re.sub(r"[^a-zA-Z0-9ñÑáéíóúÁÉÍÓÚüÜ_-]+", "-", title)
    title = re.sub(r"-+", "-", title)
    return title.strip("-").lower()


def get_video_title(url: str, browser=None) -> str:
    opts = {"quiet": True}
    if browser:
        opts["cookiesfrombrowser"] = (browser,)
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return info["title"]


def download_video(url: str, ffmpeg_path=None, browser=None):

    # 1) TÍTULO
    title = get_video_title(url, browser)
    clean = clean_title(title)

    # 2) FECHA
    today = datetime.now().strftime("%Y-%m-%d")
    folder_name = f"{today}-{clean}"
    out_dir = os.path.join("output", folder_name)
    os.makedirs(out_dir, exist_ok=True)

    # 3) OPCIONES YT-DLP (VÍDEO)
    ydl_opts = {
        "outtmpl": os.path.join(out_dir, "%(title)s.%(ext)s"),
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "noplaylist": True,
    }

    if ffmpeg_path:
        ydl_opts["ffmpeg_location"] = ffmpeg_path

    if browser:
        ydl_opts["cookiesfrombrowser"] = (browser,)
        print(f"🍪 Usando cookies del navegador: {browser}")

    print(f"➡️ Descargando vídeo: {title}")

    # 4) DESCARGA
    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except DownloadError as e:
        msg = str(e)
        if "Sign in to confirm you're not a bot" in msg and not browser:
            print("⚠️ YouTube pide login. Usa --browser chrome / firefox / brave")
        raise SystemExit(1)

    print(f"✅ Vídeo guardado en: {out_dir}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--ffmpeg", default=None)
    p.add_argument("--browser", default=None)
    a = p.parse_args()
    download_video(a.url, a.ffmpeg, a.browser)
