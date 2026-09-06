"""Cliente ComfyUI headless (texto→imagen) para el b-roll de los reels. Reutiliza
el patrón de videos_automaticos/comfy_service: cargar un workflow API, inyectar
prompt/seed/tamaño, POST /prompt, sondear /history y bajar la imagen por /view.

ComfyUI es nativo en el Windows con la GPU (COMFY_URL, por defecto :8188).
"""
from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path

import requests

WORKFLOW = Path(__file__).resolve().parents[2] / "workflows" / "reel_broll.json"


def _comfy_url() -> str:
    return (os.environ.get("COMFY_URL") or "http://192.168.1.46:8188").rstrip("/")


def is_up() -> bool:
    try:
        return requests.get(f"{_comfy_url()}/system_stats", timeout=5).ok
    except Exception:
        return False


def _prepare(prompt: str, seed: int, width: int, height: int, negative: str | None = None) -> dict:
    wf = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    for node in wf.values():
        ct = node.get("class_type", "")
        ins = node.get("inputs", {})
        if ct == "CLIPTextEncode" and "text" in ins:
            is_neg = "watermark" in str(ins["text"]).lower()  # el negativo lleva 'watermark...'
            if is_neg and negative:
                ins["text"] = negative
            elif not is_neg:
                ins["text"] = prompt
        if "seed" in ins:
            ins["seed"] = seed
        if ct == "EmptyLatentImage":
            ins["width"], ins["height"] = width, height
    return wf


def generate_image(prompt: str, out_path: Path, width: int = 832, height: int = 1216,
                   seed: int | None = None, timeout_s: int = 420, negative: str | None = None) -> Path:
    """Genera una imagen con ComfyUI y la guarda (jpg) en out_path. `negative` sustituye
    el prompt negativo del workflow (útil para forzar ausencias). Lanza si falla."""
    url = _comfy_url()
    seed = seed if seed is not None else random.randint(1, 2**31 - 1)
    payload = {"prompt": _prepare(prompt, seed, width, height, negative), "client_id": f"reel-{random.randint(1000,9999)}"}
    r = requests.post(f"{url}/prompt", json=payload, timeout=30)
    r.raise_for_status()
    prompt_id = r.json()["prompt_id"]

    # Sondea /history hasta que termine.
    deadline = time.time() + timeout_s
    hist = None
    while time.time() < deadline:
        h = requests.get(f"{url}/history/{prompt_id}", timeout=15).json()
        if prompt_id in h and h[prompt_id].get("status", {}).get("completed"):
            hist = h[prompt_id]
            break
        time.sleep(1.0)
    if not hist:
        raise RuntimeError("ComfyUI no terminó a tiempo (¿modelo cargando o GPU ocupada?).")

    outputs = hist.get("outputs", {})
    img = None
    for node_output in outputs.values():
        if node_output.get("images"):
            img = node_output["images"][0]
            break
    if not img:
        raise RuntimeError("ComfyUI no devolvió imagen.")

    data = requests.get(f"{url}/view", params={"filename": img["filename"],
                        "subfolder": img.get("subfolder", ""), "type": img.get("type", "output")}, timeout=60).content
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(data)
    # Comprime a JPG para que ffmpeg vaya ligero.
    try:
        from PIL import Image
        with Image.open(out_path) as im:
            if im.mode in ("RGBA", "P"):
                im = im.convert("RGB")
            im.save(out_path, "JPEG", quality=90, optimize=True)
    except Exception:
        pass
    return out_path
