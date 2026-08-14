#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Descarga de Google Drive (no fiable con yt-dlp en ficheros grandes: Google mete
una pagina de confirmacion anti-virus). Usa gdown, que gestiona el token de
confirmacion y ficheros de varios GB. Soporta enlaces a UN fichero
(/file/d/<id>) y a una CARPETA (/drive/folders/<id>) — en la carpeta coge el
video mas grande. El recurso debe ser publico ('cualquiera con el enlace').
"""
from __future__ import annotations

import os
import re
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".flv"}


def is_gdrive(url: str) -> bool:
    return "drive.google.com" in url


def _is_folder(url: str) -> bool:
    return "/folders/" in url


def extract_id(url: str) -> str | None:
    """Saca el id (de fichero o carpeta) de los formatos habituales de Drive."""
    for pat in (r"/folders/([a-zA-Z0-9_-]+)", r"/file/d/([a-zA-Z0-9_-]+)",
                r"[?&]id=([a-zA-Z0-9_-]+)", r"/d/([a-zA-Z0-9_-]+)"):
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def download_gdrive(url: str, staging_dir: str) -> Path:
    """Descarga el vídeo de Drive en `staging_dir`. Si el enlace es una carpeta,
    descarga su contenido y devuelve el VÍDEO más grande. Lanza si no hay vídeo o
    el recurso es privado."""
    import gdown  # dependencia instalada en el backend

    os.makedirs(staging_dir, exist_ok=True)
    gid = extract_id(url)
    if not gid:
        raise RuntimeError("No se pudo extraer el id del enlace de Drive.")

    if _is_folder(url):
        print(f"Carpeta de Drive {gid}: descargando su contenido...", flush=True)
        try:
            files = gdown.download_folder(id=gid, output=staging_dir, quiet=False,
                                          use_cookies=False) or []
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "No se pudo abrir la carpeta de Drive (Google devolvió error). Revisa que: "
                "1) el enlace de la CARPETA es correcto y completo; 2) está compartida como "
                "'Cualquiera con el enlace'. Alternativa fiable: abre el vídeo dentro de la "
                "carpeta y pega su enlace directo (/file/d/...), que descarga sin problema. "
                f"[gdown: {str(exc)[:150]}]"
            ) from exc
        vids = [Path(f) for f in files if Path(f).suffix.lower() in VIDEO_EXTS and Path(f).exists()]
        if not vids:  # por si download_folder no devuelve la lista, escanea el dir
            vids = [p for p in Path(staging_dir).rglob("*")
                    if p.is_file() and p.suffix.lower() in VIDEO_EXTS]
        if not vids:
            raise RuntimeError("La carpeta de Drive no contiene ningún vídeo (mp4/mov/...). "
                               "¿Es la carpeta correcta y pública?")
        best = max(vids, key=lambda p: p.stat().st_size)
        print(f"Vídeo elegido de la carpeta: {best.name} ({best.stat().st_size / 1e9:.1f} GB)", flush=True)
        return best

    out = gdown.download(id=gid, output=staging_dir + os.sep, quiet=False)
    if not out or not Path(out).exists():
        raise RuntimeError("gdown no pudo descargar el archivo de Drive. Asegúrate de que "
                           "el enlace es público ('cualquiera con el enlace puede ver').")
    return Path(out)
