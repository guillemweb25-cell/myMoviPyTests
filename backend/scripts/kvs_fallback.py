#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fallback para sitios KVS (Kernel Video Sharing).

Muchos tubes basados en KVS ofuscan el objeto de configuracion del reproductor
dandole un nombre de variable aleatorio (``var t47706abb3d = {...}``) en lugar
del clasico ``var flashvars = {...}``. El extractor generico de yt-dlp busca
literalmente ``flashvars`` y falla con ``Unable to extract flashvars``.

Este modulo localiza ese objeto sea cual sea su nombre, y reutiliza el
descifrado de URLs del propio yt-dlp (``GenericIE._kvs_get_real_url``) para
construir los enlaces directos a los MP4.
"""
from __future__ import annotations

import http.cookiejar
import json
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

from yt_dlp.extractor.generic import GenericIE
from yt_dlp.utils import js_to_json

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def is_flashvars_error(message: str) -> bool:
    """True si el error de yt-dlp es el fallo tipico de KVS."""
    return "flashvars" in message.lower()


def _fetch_html(url: str, cookies_file: str | None = None) -> str:
    handlers = []
    if cookies_file:
        jar = http.cookiejar.MozillaCookieJar()
        jar.load(cookies_file, ignore_discard=True, ignore_expires=True)
        handlers.append(urllib.request.HTTPCookieProcessor(jar))
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with opener.open(request, timeout=30) as response:
        return response.read().decode("utf-8", "ignore")


def _extract_balanced_object(text: str, brace_pos: int) -> str | None:
    """Devuelve el objeto ``{...}`` con llaves balanceadas desde ``brace_pos``."""
    depth = 0
    in_string: str | None = None
    escaped = False
    for i in range(brace_pos, len(text)):
        char = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == in_string:
                in_string = None
        elif char in "'\"":
            in_string = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[brace_pos : i + 1]
    return None


def _find_flashvars_object(html: str) -> str | None:
    """Encuentra el objeto de configuracion KVS con nombre de variable arbitrario."""
    for match in re.finditer(r"var\s+\w+\s*=\s*\{", html):
        brace_pos = html.index("{", match.start())
        obj = _extract_balanced_object(html, brace_pos)
        if obj and "license_code" in obj and "video_url" in obj:
            return obj
    return None


def looks_like_kvs(html: str) -> bool:
    return "kt_player" in html and "license_code" in html


def extract_kvs(page_url: str, cookies_file: str | None = None) -> tuple[str, list[dict]]:
    """Devuelve ``(title, formats)`` para una pagina KVS.

    ``formats`` es una lista de ``{"url", "format_id", "height"}`` ordenada de
    menor a mayor calidad. Lanza ``ValueError`` si la pagina no es KVS o no se
    puede parsear.
    """
    html = _fetch_html(page_url, cookies_file)
    obj = _find_flashvars_object(html)
    if not obj:
        raise ValueError("No se encontro el objeto flashvars KVS en la pagina")

    data = json.loads(js_to_json(obj))
    license_code = data.get("license_code", "")
    title = str(data.get("video_title") or data.get("video_id") or "video")

    formats: list[dict] = []
    for key, value in data.items():
        if not re.fullmatch(r"video_(?:url|alt_url\d*)", key):
            continue
        if not isinstance(value, str) or "/get_file/" not in value:
            continue
        real_url = urljoin(page_url, GenericIE._kvs_get_real_url(value, license_code))
        label = str(data.get(f"{key}_text", key))
        resolution = re.search(r"(\d+)p", label)
        formats.append(
            {
                "url": real_url,
                "format_id": label,
                "height": int(resolution.group(1)) if resolution else 0,
            }
        )

    if not formats:
        raise ValueError("No se encontraron URLs de video KVS")

    formats.sort(key=lambda item: item["height"])
    return title, formats


def _stream_to_file(direct_url: str, page_url: str, destination: Path) -> None:
    """Descarga por streaming el MP4 directo (con Referer) mostrando progreso."""
    request = urllib.request.Request(
        direct_url, headers={"User-Agent": USER_AGENT, "Referer": page_url}
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        total = int(response.headers.get("Content-Length") or 0)
        downloaded = 0
        last_pct = -1
        with destination.open("wb") as handle:
            while True:
                chunk = response.read(1 << 20)  # 1 MiB
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 // total
                    if pct != last_pct and pct % 5 == 0:
                        print(f"Descargando... {pct}% ({downloaded // (1 << 20)} MiB)")
                        last_pct = pct
    print(f"Descarga completa: {destination.name} ({downloaded // (1 << 20)} MiB)")


def download_direct(
    direct_url: str,
    page_url: str,
    out_dir: str | Path,
    filename_base: str,
    extract_audio: bool = False,
    ffmpeg_path: str | None = None,
) -> Path:
    """Descarga un MP4 directo KVS por streaming. Si ``extract_audio`` esta
    activo, extrae el audio a MP3 con ffmpeg y elimina el MP4 intermedio.
    Devuelve la ruta del fichero resultante."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    mp4_path = out_dir / f"{filename_base}.mp4"
    _stream_to_file(direct_url, page_url, mp4_path)

    if not extract_audio:
        return mp4_path

    ffmpeg_bin = ffmpeg_path or shutil.which("ffmpeg") or "ffmpeg"
    mp3_path = out_dir / f"{filename_base}.mp3"
    print("Extrayendo audio a MP3 con ffmpeg...")
    subprocess.run(
        [ffmpeg_bin, "-y", "-i", str(mp4_path), "-vn", "-acodec", "libmp3lame",
         "-b:a", "192k", str(mp3_path)],
        check=True,
    )
    mp4_path.unlink(missing_ok=True)
    print(f"MP3 generado: {mp3_path.name}")
    return mp3_path
