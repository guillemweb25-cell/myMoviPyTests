#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Job del b-roll de un reel: guion → prompts (LLM) → imágenes (ComfyUI) →
slideshow + karaoke + voz → actualiza la generación. Corre como JOB (proceso
independiente) para que NO lo mate un reload del backend a media faena.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app import db  # noqa: E402
from app.services import comfy_client  # noqa: E402
from app.services.reel_engine import broll_prompts  # noqa: E402


def _duration(audio: Path) -> float:
    import re
    proc = subprocess.run(["ffmpeg", "-i", str(audio)], capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", proc.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def main() -> None:
    ap = argparse.ArgumentParser(description="Genera el b-roll de un reel y lo compone")
    ap.add_argument("--reel", required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--no-subtitles", action="store_true")
    args = ap.parse_args()

    root = Path.cwd()
    db.init(root / "backend" / "runs" / "jobs.db")

    reel = db.get_reel(args.reel)
    if not reel:
        raise SystemExit(f"Generación {args.reel} no encontrada.")
    audio = root / reel["audio"]
    if not reel["audio"] or not audio.exists():
        raise SystemExit("La generación no tiene audio.")
    if not comfy_client.is_up():
        raise SystemExit("ComfyUI no responde (¿encendido en el Windows y la GPU libre?).")

    dur = _duration(audio)
    n = max(3, min(10, round(dur / 5)))
    print(f"Guion → {n} prompts de b-roll...", flush=True)
    prompts = broll_prompts(reel.get("script") or "", n)

    broll_dir = audio.parent / (audio.stem + "_broll")
    broll_dir.mkdir(parents=True, exist_ok=True)
    images = []
    for i, p in enumerate(prompts):
        print(f"[{i + 1}/{len(prompts)}] Imagen: {p[:70]}...", flush=True)
        img = comfy_client.generate_image(p, broll_dir / f"img_{i:02d}.jpg")
        images.append(str(img))

    out = audio.with_name(audio.stem + "_video.mp4")
    print("Componiendo slideshow + karaoke...", flush=True)
    cmd = [sys.executable, str(Path(__file__).with_name("reel_compose.py")),
           "--audio", str(audio), "--out", str(out), "--images", ",".join(images)]
    if args.title.strip():
        cmd += ["--title", args.title.strip()]
    if not args.no_subtitles:
        cmd.append("--subtitles")
    rc = subprocess.run(cmd, cwd=str(root)).returncode
    if rc != 0 or not out.exists():
        raise SystemExit(f"Fallo componiendo el reel (rc={rc}).")

    db.update_reel(args.reel, {"video_path": str(out.relative_to(root)), "title": args.title})
    print(f"Reel con b-roll listo: {out}", flush=True)


if __name__ == "__main__":
    main()
