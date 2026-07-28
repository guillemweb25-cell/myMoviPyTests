#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, json, os, re
from datetime import datetime
from urllib.parse import urlparse, parse_qs

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from kvs_fallback import download_direct, extract_kvs, is_flashvars_error


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


def download_video(url: str, ffmpeg_path=None, browser=None, cookies_file=None):

    # 1) TÍTULO (con fallback KVS si yt-dlp no reconoce el reproductor)
    kvs_formats = None
    try:
        title = get_video_title(url, browser, cookies_file)
    except DownloadError as exc:
        if not is_flashvars_error(str(exc)):
            raise
        print("Sitio KVS detectado; usando extraccion directa (fallback).")
        title, kvs_formats = extract_kvs(url, cookies_file)
    clean = clean_title(title)

    # 2) FECHA
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

    # 3) OPCIONES YT-DLP (VÍDEO)
    ydl_opts = {
        "outtmpl": os.path.join(out_dir, "%(title)s.%(ext)s"),
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        "noplaylist": True,
    }

    if ffmpeg_path:
        ydl_opts["ffmpeg_location"] = ffmpeg_path

    if cookies_file:
        ydl_opts["cookiefile"] = cookies_file
    elif browser:
        ydl_opts["cookiesfrombrowser"] = (browser,)
        print(f"🍪 Usando cookies del navegador: {browser}")

    print(f"➡️ Descargando vídeo: {title}")

    # 4) DESCARGA
    if kvs_formats:
        best = kvs_formats[-1]
        print(f"Descargando vídeo (KVS {best['format_id']})")
        download_direct(best["url"], url, out_dir, clean, ffmpeg_path=ffmpeg_path)
        print(f"✅ Vídeo guardado en: {out_dir}")
        return

    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except DownloadError as e:
        msg = str(e)
        if is_flashvars_error(msg):
            print("Sitio KVS detectado; usando extraccion directa (fallback).")
            _, kvs_formats = extract_kvs(url, cookies_file)
            best = kvs_formats[-1]
            download_direct(best["url"], url, out_dir, clean, ffmpeg_path=ffmpeg_path)
            print(f"✅ Vídeo guardado en: {out_dir}")
            return
        if "Sign in to confirm you're not a bot" in msg and not browser:
            print("⚠️ YouTube pide login. Usa --browser chrome / firefox / brave")
        raise SystemExit(1)

    print(f"✅ Vídeo guardado en: {out_dir}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--url", required=True)
    p.add_argument("--ffmpeg", default=None)
    p.add_argument("--browser", default=None)
    p.add_argument("--cookies", default=None)
    a = p.parse_args()
    download_video(a.url, a.ffmpeg, a.browser, a.cookies)
