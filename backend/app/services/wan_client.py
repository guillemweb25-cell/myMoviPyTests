"""Cliente ComfyUI para WAN 2.2 Image-to-Video (GGUF + loras lightning 4 pasos).

Sube la imagen de inicio al `input` de ComfyUI (/upload/image), inyecta prompt +
tamaño + nº de frames en el workflow `wan_i2v.json`, lo lanza, sondea /history y
baja el vídeo resultante (VHS_VideoCombine → webm) por /view. GPU del Windows.
"""
from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path

import requests

WAN_WORKFLOW = Path(__file__).resolve().parents[2] / "workflows" / "wan_ti2v.json"

_NEG_HINTS = ("watermark", "logo", "blurry", "distorted", "text,")


def _comfy_url() -> str:
    return (os.environ.get("COMFY_URL") or "http://192.168.1.46:8188").rstrip("/")


def is_up() -> bool:
    try:
        return requests.get(f"{_comfy_url()}/system_stats", timeout=5).ok
    except Exception:
        return False


def upload_image(path: Path) -> str:
    """Sube una imagen al `input` de ComfyUI. Devuelve el nombre para el LoadImage."""
    url = _comfy_url()
    with open(path, "rb") as fh:
        r = requests.post(f"{url}/upload/image",
                          files={"image": (Path(path).name, fh, "image/png")},
                          data={"overwrite": "true"}, timeout=120)
    r.raise_for_status()
    j = r.json()
    sub = j.get("subfolder", "")
    return f"{sub}/{j['name']}" if sub else j["name"]


def generate_video(start_image: Path, out_path: Path, prompt: str,
                   negative: str = "text, logos, watermarks, blurry, distorted, morphing, flickering",
                   width: int = 480, height: int = 832, length: int = 97,
                   seed: int | None = None, timeout_s: int = 1800) -> Path:
    """Genera un clip WAN i2v a partir de `start_image` y `prompt`. Guarda el vídeo
    (webm) en out_path. `length` = nº de frames (97 ≈ 4s a 24fps). Lanza si falla."""
    url = _comfy_url()
    seed = seed if seed is not None else random.randint(1, 2**31 - 1)
    img_name = upload_image(Path(start_image))

    # Inyecta por TIPO de nodo (funciona con cualquier workflow WAN i2v).
    wf = json.loads(WAN_WORKFLOW.read_text(encoding="utf-8"))
    for node in wf.values():
        ct = node.get("class_type", "")
        ins = node.get("inputs", {})
        if ct == "CLIPTextEncode" and "text" in ins:
            is_neg = any(h in str(ins["text"]).lower() for h in _NEG_HINTS)
            ins["text"] = negative if is_neg else prompt
        elif ct == "WanImageToVideo":
            ins["width"], ins["height"], ins["length"] = width, height, length
        elif ct == "LoadImage":
            ins["image"] = img_name
        if "seed" in ins:
            ins["seed"] = seed
        if "noise_seed" in ins:
            ins["noise_seed"] = seed

    payload = {"prompt": wf, "client_id": f"plant-{random.randint(1000, 9999)}"}
    r = requests.post(f"{url}/prompt", json=payload, timeout=30)
    r.raise_for_status()
    pid = r.json()["prompt_id"]

    deadline = time.time() + timeout_s
    hist = None
    while time.time() < deadline:
        try:
            # Timeout amplio: ComfyUI, con la GPU saturada generando, tarda en
            # responder a /history. Un fallo transitorio NO debe tumbar el job.
            h = requests.get(f"{url}/history/{pid}", timeout=120).json()
            if pid in h and h[pid].get("status", {}).get("completed"):
                hist = h[pid]
                break
        except Exception:  # noqa: BLE001 (timeout/red transitorio → reintenta)
            pass
        time.sleep(3.0)
    if not hist:
        raise RuntimeError("WAN no terminó a tiempo (¿GPU ocupada o modelo cargando?).")

    vid = None
    for node_out in hist.get("outputs", {}).values():
        for key in ("gifs", "videos", "images"):
            if node_out.get(key):
                vid = node_out[key][0]
                break
        if vid:
            break
    if not vid:
        raise RuntimeError("WAN no devolvió vídeo.")

    data = requests.get(f"{url}/view", params={"filename": vid["filename"],
                        "subfolder": vid.get("subfolder", ""), "type": vid.get("type", "output")},
                        timeout=180).content
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_bytes(data)
    return Path(out_path)
