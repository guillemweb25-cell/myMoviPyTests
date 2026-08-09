"""Cliente del worker de personas (YOLOv8): detección + blur.

Detección cacheada por clip+tramo en un JSON junto al clip (incluye las cajas
frame-a-frame de cada persona, que luego se usan para blurear). Cae con gracia
(None/False) si el worker no está disponible.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import httpx


def _worker_url() -> str:
    return (os.environ.get("PERSON_WORKER_URL") or "").rstrip("/")


def detect(source_video: Path, start: float, end: float, cache_json: Path,
           ffmpeg: str = "ffmpeg") -> dict | None:
    """Detecta personas en el tramo [start,end] del vídeo. Cachea el JSON completo
    (con cajas frame-a-frame). Devuelve el dict o None."""
    if cache_json.exists():
        try:
            return json.loads(cache_json.read_text(encoding="utf-8"))
        except Exception:
            pass
    url = _worker_url()
    if not url or not source_video.exists():
        return None

    cache_json.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_json.parent / f"_pdet_{cache_json.stem}.mp4"
    # Segmento solo-vídeo a 25 fps (MISMO fps que el segmento de blur, para que los
    # índices de frame de las cajas coincidan al difuminar).
    subprocess.run([
        ffmpeg, "-y", "-ss", f"{start:.3f}", "-i", str(source_video), "-t", f"{end - start:.3f}",
        "-an", "-r", "25", "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", str(tmp),
    ], capture_output=True)
    if not tmp.exists():
        return None
    try:
        with tmp.open("rb") as fh:
            r = httpx.post(f"{url}/persons", files={"file": (tmp.name, fh, "video/mp4")},
                           timeout=httpx.Timeout(900.0, connect=10.0))
        r.raise_for_status()
        data = r.json()
        cache_json.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        data = None
    finally:
        tmp.unlink(missing_ok=True)
    return data


def blur(segment: Path, detection: dict, person_ids: list[int], out_path: Path) -> bool:
    """Difumina en `segment` las personas `person_ids` (según sus cajas en
    `detection`) y escribe el resultado (sin audio) en `out_path`. True si OK."""
    url = _worker_url()
    if not url or not detection or not segment.exists():
        return False
    idset = set(person_ids)
    frames: dict[str, list] = {}
    for p in detection.get("persons", []):
        if p.get("id") in idset:
            for box in p.get("boxes", []):
                f, x, y, w, h = box
                frames.setdefault(str(int(f)), []).append([x, y, w, h])
    if not frames:
        return False
    try:
        with segment.open("rb") as fh:
            r = httpx.post(f"{url}/blur", files={"file": (segment.name, fh, "video/mp4")},
                           data={"boxes": json.dumps({"frames": frames})},
                           timeout=httpx.Timeout(900.0, connect=10.0))
        r.raise_for_status()
        out_path.write_bytes(r.content)
        return out_path.exists() and out_path.stat().st_size > 0
    except Exception:
        return False
