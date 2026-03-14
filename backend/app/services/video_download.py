from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError


def clean_title(title: str) -> str:
    title = re.sub(r"[\U00010000-\U0010ffff]", "", title)
    title = re.sub(r"[^a-zA-Z0-9ñÑáéíóúÁÉÍÓÚüÜ_-]+", "-", title)
    title = re.sub(r"-+", "-", title)
    return title.strip("-").lower()


class VideoDownloadService:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.output_dir = root_dir / "output"

    def get_video_title(
        self,
        url: str,
        browser: str | None = None,
        cookies_file: str | None = None,
    ) -> str:
        opts: dict[str, object] = {"quiet": True}
        if cookies_file:
            opts["cookiefile"] = cookies_file
        elif browser:
            opts["cookiesfrombrowser"] = (browser,)
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return str(info["title"])

    @staticmethod
    def is_cookie_error(message: str) -> bool:
        lowered = message.lower()
        return "could not find" in lowered and "cookies database" in lowered

    def build_output_folder(self, title: str) -> Path:
        today = datetime.now().strftime("%Y-%m-%d")
        folder_name = f"{today}-{clean_title(title)}"
        return self.output_dir / folder_name

    def write_source_metadata(self, out_dir: Path, url: str, title: str, browser: str | None) -> None:
        downloaded_at = datetime.now().isoformat()
        (out_dir / "source_url.txt").write_text(url, encoding="utf-8")
        (out_dir / "source.json").write_text(
            json.dumps(
                {
                    "url": url,
                    "title": title,
                    "downloaded_at": downloaded_at,
                    "browser": browser or "",
                    "cookies_file": "",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def download_mp3(
        self,
        url: str,
        ffmpeg_path: str | None = None,
        browser: str | None = None,
        cookies_file: str | None = None,
    ) -> Path:
        title = self.get_video_title(url, browser, cookies_file)
        out_dir = self.build_output_folder(title)
        out_dir.mkdir(parents=True, exist_ok=True)
        self.write_source_metadata(out_dir, url, title, browser)
        if cookies_file:
            source_json = out_dir / "source.json"
            source_json.write_text(
                json.dumps(
                    {
                        "url": url,
                        "title": title,
                        "downloaded_at": datetime.now().isoformat(),
                        "browser": browser or "",
                        "cookies_file": cookies_file,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

        ydl_opts: dict[str, object] = {
            "outtmpl": str(out_dir / "%(title)s.%(ext)s"),
            "format": "bestaudio/best",
            "noplaylist": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
        }

        if ffmpeg_path:
            ydl_opts["ffmpeg_location"] = ffmpeg_path

        if cookies_file:
            ydl_opts["cookiefile"] = cookies_file
        elif browser:
            ydl_opts["cookiesfrombrowser"] = (browser,)
            print(f"Usando cookies del navegador: {browser}")

        print(f"Descargando MP3: {title}")

        try:
            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except DownloadError as exc:
            message = str(exc)
            if browser and self.is_cookie_error(message):
                print(
                    f"No se han encontrado cookies de {browser} dentro del contenedor. "
                    "Reintentando sin cookies del navegador."
                )
                return self.download_mp3(url=url, ffmpeg_path=ffmpeg_path, browser=None)
            if "Sign in to confirm you're not a bot" in message and not browser:
                print("YouTube pide login. Usa --browser chrome / firefox / brave")
            raise SystemExit(1) from exc

        mp3_files = sorted(out_dir.glob("*.mp3"), key=lambda path: path.stat().st_mtime, reverse=True)
        if not mp3_files:
            raise SystemExit(f"No se ha generado ningun MP3 en {out_dir}")

        print(f"MP3 guardado en: {mp3_files[0]}")
        return mp3_files[0]
