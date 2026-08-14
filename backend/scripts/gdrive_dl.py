#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Descarga de Google Drive (no fiable con yt-dlp en ficheros grandes: Google mete
una pagina de confirmacion anti-virus). Usa gdown, que gestiona el token de
confirmacion y ficheros de varios GB. El archivo debe ser publico
('cualquiera con el enlace').
"""
from __future__ import annotations

import os
import re
from pathlib import Path


def is_gdrive(url: str) -> bool:
    return "drive.google.com" in url


def extract_file_id(url: str) -> str | None:
    """Saca el id de fichero de los formatos habituales de Drive."""
    for pat in (r"/file/d/([a-zA-Z0-9_-]+)", r"[?&]id=([a-zA-Z0-9_-]+)", r"/d/([a-zA-Z0-9_-]+)"):
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def download_gdrive(url: str, staging_dir: str) -> Path:
    """Descarga el fichero de Drive en `staging_dir` con su nombre remoto. Devuelve
    la ruta al fichero. Lanza si no se pudo (privado / enlace inválido)."""
    import gdown  # dependencia instalada en el backend

    os.makedirs(staging_dir, exist_ok=True)
    file_id = extract_file_id(url)
    src = f"https://drive.google.com/uc?id={file_id}" if file_id else url
    # fuzzy=True acepta enlaces /file/d/.../view y variantes; output terminado en
    # "/" guarda con el nombre remoto dentro de la carpeta.
    out = gdown.download(url=src, output=staging_dir + os.sep, quiet=False, fuzzy=True)
    if not out or not Path(out).exists():
        raise RuntimeError(
            "gdown no pudo descargar el archivo de Drive. Asegúrate de que el enlace "
            "es público ('cualquiera con el enlace puede ver')."
        )
    return Path(out)
