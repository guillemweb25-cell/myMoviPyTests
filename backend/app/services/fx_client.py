"""Cliente del worker de FX (Remotion): motion graphics sobre el vertical ya compuesto.

Cae con gracia (None) si el worker no está, si rechaza el payload o si tarda
demasiado: quien llama debe seguir entonces por el camino de siempre
(ffmpeg + subtítulos ASS). Ver doc/08-fx-worker-motion-graphics.md.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import httpx

# Un clip de 30 s tarda ~1-3 min en CPU. Margen amplio pero no infinito: si se
# pasa de aquí, mejor el camino ASS que dejar el job clavado.
_RENDER_TIMEOUT = httpx.Timeout(900.0, connect=10.0)


def _worker_url() -> str:
    return (os.environ.get("FX_WORKER_URL") or "").rstrip("/")


def available() -> bool:
    """True si hay worker configurado y responde con el bundle listo."""
    url = _worker_url()
    if not url:
        return False
    try:
        r = httpx.get(f"{url}/health", timeout=httpx.Timeout(5.0, connect=2.0))
        r.raise_for_status()
        data = r.json()
        return bool(data.get("ok")) and bool(data.get("bundled"))
    except Exception:
        return False


def presets() -> list[str]:
    """Presets que ofrece el worker. Lista vacía = sin worker (la UI los oculta)."""
    url = _worker_url()
    if not url:
        return []
    try:
        r = httpx.get(f"{url}/health", timeout=httpx.Timeout(5.0, connect=2.0))
        r.raise_for_status()
        return list(r.json().get("presets") or [])
    except Exception:
        return []


def words_from_assemblyai(words: list[dict]) -> list[dict]:
    """Pasa las palabras de AssemblyAI (ms) al formato del payload (segundos)."""
    out = []
    for w in words or []:
        text = (w.get("text") or "").strip()
        if not text:
            continue
        out.append({
            "text": text,
            "start": float(w["start"]) / 1000.0,
            "end": float(w["end"]) / 1000.0,
        })
    return out


def render(base_video: Path, payload: dict, out_path: Path,
           watermark: Path | None = None, endcard_frame: Path | None = None,
           retries: int = 1) -> Path | None:
    """Manda el vertical al worker y escribe el MP4 con FX en `out_path`.

    Devuelve `out_path` si salió bien, o None (worker ausente, payload rechazado,
    timeout o error), y entonces quien llama debe usar el camino ASS.
    """
    url = _worker_url()
    if not url or not base_video.exists():
        return None

    for attempt in range(retries + 1):
        handles = []
        try:
            files = [("video", (base_video.name, base_video.open("rb"), "video/mp4"))]
            handles.append(files[0][1][1])
            for field, path in (("watermark", watermark), ("endcard_frame", endcard_frame)):
                if path and path.exists():
                    fh = path.open("rb")
                    handles.append(fh)
                    files.append((field, (path.name, fh, "image/png")))

            r = httpx.post(f"{url}/render", files=files,
                           data={"payload": json.dumps(payload)}, timeout=_RENDER_TIMEOUT)

            # 4xx = el worker no puede con este payload (preset desconocido, capa
            # sin implementar, falta el watermark exigido). Reintentar no cambia
            # nada: se cae al camino ASS directamente.
            if 400 <= r.status_code < 500:
                detail = r.text[:300]
                print(f"[fx] worker rechazó el payload ({r.status_code}): {detail}", flush=True)
                return None

            r.raise_for_status()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(r.content)
            return out_path
        except Exception as exc:
            last = attempt == retries
            print(f"[fx] render falló ({type(exc).__name__}: {exc})"
                  f"{'; se usará el camino ASS' if last else '; reintentando'}", flush=True)
            if last:
                return None
        finally:
            for fh in handles:
                try:
                    fh.close()
                except Exception:
                    pass
    return None
