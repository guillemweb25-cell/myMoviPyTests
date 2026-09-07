"""Cliente Google Veo (Gemini API) — imagen→vídeo.

Usa el endpoint predictLongRunning de la Gemini API con Veo 3.1. Sube la imagen
como bytes base64, arranca la operación, la sondea y descarga el vídeo.

OJO: pendiente de VERIFICAR con crédito real en la cuenta de Google (parsing
defensivo por si cambian los nombres de campos de la respuesta). Requiere
GOOGLE_API_KEY (o GEMINI_API_KEY) con facturación/Veo habilitado.
"""
from __future__ import annotations

import base64
import os
import time
from pathlib import Path

import requests

API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
MODEL = os.getenv("VEO_MODEL", "veo-3.1-generate-preview")


def _api_key() -> str:
    key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GOOGLE_API_KEY no configurada (ponla en .env).")
    return key


def is_configured() -> bool:
    return bool(os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY"))


def _find_video_uri(obj):
    """Busca recursivamente una URI de vídeo en la respuesta (defensivo)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("uri", "fileUri", "videoUri") and isinstance(v, str) and v.startswith("http"):
                return v
            if k == "bytesBase64Encoded" and isinstance(v, str):
                return ("b64", v)
            found = _find_video_uri(v)
            if found:
                return found
    elif isinstance(obj, list):
        for it in obj:
            found = _find_video_uri(it)
            if found:
                return found
    return None


def generate_video(image_path: Path, out_path: Path, prompt: str,
                   aspect: str = "9:16", negative: str = "", timeout_s: int = 600) -> Path:
    """Genera un vídeo Veo a partir de `image_path` + `prompt` y lo guarda (mp4)."""
    key = _api_key()
    headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
    img_b64 = base64.b64encode(Path(image_path).read_bytes()).decode("ascii")
    mime = "image/png" if str(image_path).lower().endswith(".png") else "image/jpeg"

    instance = {"prompt": prompt, "image": {"bytesBase64Encoded": img_b64, "mimeType": mime}}
    params = {"aspectRatio": aspect}
    if negative:
        params["negativePrompt"] = negative
    body = {"instances": [instance], "parameters": params}

    r = requests.post(f"{API_ROOT}/models/{MODEL}:predictLongRunning", headers=headers, json=body, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"Veo gen falló ({r.status_code}): {r.text[:300]}")
    op_name = r.json().get("name")
    if not op_name:
        raise RuntimeError(f"Veo: sin operation name: {r.text[:200]}")
    print(f"[veo] operation: {op_name}", flush=True)

    t0 = time.time()
    result = None
    while time.time() - t0 < timeout_s:
        time.sleep(8)
        p = requests.get(f"{API_ROOT}/{op_name}", headers=headers, timeout=30)
        if p.status_code != 200:
            print(f"[veo] poll {p.status_code}: {p.text[:120]}", flush=True)
            continue
        data = p.json()
        if data.get("done"):
            if data.get("error"):
                raise RuntimeError(f"Veo error: {data['error']}")
            result = data.get("response", data)
            break
        print("[veo] generando…", flush=True)
    if result is None:
        raise RuntimeError("Veo: timeout.")

    found = _find_video_uri(result)
    if not found:
        raise RuntimeError(f"Veo: no encuentro el vídeo en la respuesta: {str(result)[:300]}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(found, tuple) and found[0] == "b64":
        out_path.write_bytes(base64.b64decode(found[1]))
    else:
        vid = requests.get(found, headers={"x-goog-api-key": key}, timeout=180).content
        out_path.write_bytes(vid)
    return out_path
