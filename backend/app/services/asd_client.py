"""Cliente del worker de ASD (active speaker detection).

Sube el vídeo fuente al worker de GPU (Windows/WSL2), cachea la respuesta en
`asd.json` junto al vídeo y cae con gracia (None) si el worker no está disponible,
para que el render nunca dependa de que la GPU esté encendida.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx


def _worker_url() -> str:
    return (os.environ.get("ASD_WORKER_URL") or "").rstrip("/")


def get_speaker_segments(video_abs: Path) -> dict | None:
    """Devuelve el JSON de segmentos por hablante del vídeo, o None si no se puede.

    Cachea en `<carpeta_del_video>/asd.json` (se calcula una vez por vídeo fuente
    y se reutiliza en todos sus clips).
    """
    cache = video_abs.parent / "asd.json"
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            pass  # caché corrupta → recalcula

    url = _worker_url()
    if not url or not video_abs.exists():
        return None

    try:
        with video_abs.open("rb") as fh:
            files = {"file": (video_abs.name, fh, "video/mp4")}
            # connect corto, read largo (el ASD de un podcast tarda minutos).
            resp = httpx.post(f"{url}/asd", files=files, timeout=httpx.Timeout(1800.0, connect=10.0))
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    try:
        cache.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass
    return data
