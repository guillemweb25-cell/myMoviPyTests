"""Cliente xAI Grok Imagine — imagen→vídeo (grok-imagine-video).

Portado del `generate_grok_video` de videos_automaticos (probado). Sube la imagen
como data-URI base64, arranca la generación en /v1/videos/generations, sondea
/v1/videos/{id} hasta 'done' y descarga el mp4. ~$0.10/s a 720p.
"""
from __future__ import annotations

import base64
import os
import time
from pathlib import Path

import requests

API_BASE = "https://api.x.ai/v1"


def _api_key() -> str:
    key = os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY")
    if not key:
        raise RuntimeError("GROK_API_KEY no configurada (ponla en .env).")
    return key


def is_configured() -> bool:
    return bool(os.getenv("GROK_API_KEY") or os.getenv("XAI_API_KEY"))


def generate_image(prompt: str, out_path: Path, timeout_s: int = 120) -> Path:
    """Genera una imagen con grok-imagine-image (síncrono, devuelve URL) y la guarda."""
    key = _api_key()
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    r = requests.post(f"{API_BASE}/images/generations", headers=headers,
                      json={"model": "grok-imagine-image", "prompt": " ".join((prompt or "").split())[:1497], "n": 1},
                      timeout=timeout_s)
    if r.status_code != 200:
        raise RuntimeError(f"Grok image gen falló ({r.status_code}): {r.text[:300]}")
    data = r.json().get("data") or []
    if not data or not data[0].get("url"):
        raise RuntimeError(f"Grok image: sin URL: {r.text[:200]}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(requests.get(data[0]["url"], timeout=90).content)
    return out_path


def generate_video(image_path: Path, out_path: Path, prompt: str,
                   duration: int = 8, resolution: str = "720p", timeout_s: int = 600) -> Path:
    """Genera un vídeo a partir de `image_path` + `prompt` con grok-imagine-video y lo
    guarda (mp4) en out_path. Lanza si falla."""
    key = _api_key()
    image_path = Path(image_path)
    ext = image_path.suffix.lower()
    mime = "image/png" if ext == ".png" else ("image/webp" if ext == ".webp" else "image/jpeg")
    data_uri = f"data:{mime};base64,{base64.b64encode(image_path.read_bytes()).decode('ascii')}"

    clean = " ".join((prompt or "").split())[:1497]
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    # 'image' espera struct ImageUrl {"url": ...}. Sin aspect_ratio: hereda el de la imagen.
    payload = {"model": "grok-imagine-video", "prompt": clean,
               "image": {"url": data_uri}, "duration": duration, "resolution": resolution}

    r = requests.post(f"{API_BASE}/videos/generations", headers=headers, json=payload, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"Grok video gen falló ({r.status_code}): {r.text[:300]}")
    request_id = r.json().get("request_id")
    if not request_id:
        raise RuntimeError(f"Grok: sin request_id: {r.text[:200]}")
    print(f"[grok-video] Request: {request_id}", flush=True)

    t0 = time.time()
    while time.time() - t0 < timeout_s:
        time.sleep(5)
        p = requests.get(f"{API_BASE}/videos/{request_id}", headers=headers, timeout=30)
        if p.status_code != 200:
            print(f"[grok-video] poll {p.status_code}: {p.text[:120]}", flush=True)
            continue
        data = p.json()
        status = data.get("status")
        print(f"[grok-video] status: {status}", flush=True)
        if status == "done":
            url = (data.get("video") or {}).get("url")
            if not url:
                raise RuntimeError(f"Grok done pero sin URL: {data}")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            vid = requests.get(url, timeout=180).content
            out_path.write_bytes(vid)
            return out_path
        if status in ("failed", "expired"):
            raise RuntimeError(f"Grok video {status}: {data}")
    raise TimeoutError("Grok video: timeout (10 min)")
