#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, json, os, re
from datetime import datetime
from urllib.parse import urlparse, parse_qs

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError


def clean_title(title: str) -> str:
    # Elimina emojis
    title = re.sub(r"[\U00010000-\U0010ffff]", "", title)
    # Elimina caràcters no desitjats
    title = re.sub(r"[^a-zA-Z0-9ñÑáéíóúÁÉÍÓÚüÜ_-]+", "-", title)
    # Elimina múltiples guions seguits
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


def get_video_id(url: str) -> str:
    u = urlparse(url)
    if u.netloc in {"youtu.be"}:
        return u.path.lstrip("/")
    qs = parse_qs(u.query)
    return qs.get("v", ["video"])[0]


def download_mp3(url: str, ffmpeg_path=None, browser=None, cookies_file=None):

    # ---------- 1) TITOL ----------
    title = get_video_title(url, browser, cookies_file)
    clean = clean_title(title)

    # ---------- 2) DATA D’AVUI ----------
    today = datetime.now().strftime("%Y-%m-%d")

    folder_name = f"{today}-{clean}"

    out_dir = os.path.join("output", folder_name)
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

    # ---------- 3) OPCIONS ----------
    ydl_opts = {
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

    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file
    elif browser:
        ydl_opts["cookiesfrombrowser"] = (browser,)
        print(f"🍪 Usant cookies del navegador: {browser}")

    print(f"➡️ Descargando MP3: {title}")

    # ---------- 4) DESCARREGA ----------
    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except DownloadError as e:
        msg = str(e)
        if "Sign in to confirm you're not a bot" in msg and not browser:
            print("⚠️ YouTube demana login. Usa --browser chrome / firefox / brave")
        raise SystemExit(1)

    print(f"✅ Guardado en: {out_dir}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--ffmpeg", default=None)
    p.add_argument("--browser", default=None)
    p.add_argument("--cookies", default=None)
    a = p.parse_args()
    download_mp3(a.url, a.ffmpeg, a.browser, a.cookies)
