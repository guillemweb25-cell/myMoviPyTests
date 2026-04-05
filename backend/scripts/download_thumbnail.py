#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
import os
import re
from datetime import datetime

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError


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


def download_thumbnail(url: str, browser=None, cookies_file=None):
    title = get_video_title(url, browser, cookies_file)
    clean = clean_title(title)

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

    ydl_opts = {
        "skip_download": True,
        "writethumbnail": True,
        "convert_thumbnails": "png",
        "outtmpl": os.path.join(out_dir, "%(title)s.%(ext)s"),
        "noplaylist": True,
    }

    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file
    elif browser:
        ydl_opts["cookiesfrombrowser"] = (browser,)
        print(f"Usando cookies del navegador: {browser}")

    print(f"Descargando miniatura: {title}")

    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except DownloadError as e:
        msg = str(e)
        if "Sign in to confirm you're not a bot" in msg and not browser:
            print("YouTube pide login. Usa --browser chrome / firefox / brave")
        raise SystemExit(1)

    image_extensions = (".jpg", ".jpeg", ".png", ".webp")
    thumbnail_files = sorted(
        [
            os.path.join(out_dir, name)
            for name in os.listdir(out_dir)
            if name.lower().endswith(image_extensions)
        ],
        key=os.path.getmtime,
        reverse=True,
    )
    if not thumbnail_files:
        raise SystemExit(f"No se ha generado ninguna miniatura en {out_dir}")

    print(f"Miniatura guardada en: {thumbnail_files[0]}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--browser", default=None)
    p.add_argument("--cookies", default=None)
    a = p.parse_args()
    download_thumbnail(a.url, a.browser, a.cookies)
