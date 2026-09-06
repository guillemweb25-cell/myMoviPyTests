#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Miniatura vertical del reel (estilo videos_automaticos): imagen (IA o propia) +
gancho de texto arriba/centro/abajo. Se añade ~2.5s al FINAL del reel para poder
elegirla como portada del Short en el móvil. Job (usa GPU solo si genera imagen).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app import db  # noqa: E402

CANVAS_W, CANVAS_H = 1080, 1920
HOLD = 2.5


def _thumb_frame(image: Path, hook: str, position: str, out: Path, ffmpeg: str) -> None:
    """Imagen a cover 1080x1920 + gancho grande en la posición elegida → jpg."""
    lines = textwrap.wrap(hook.strip(), width=16) or [hook.strip()]
    txt = "\n".join(lines)
    txtfile = out.with_suffix(".txt")
    txtfile.write_text(txt, encoding="utf-8")
    if position == "top":
        y = "h*0.09"
    elif position == "bottom":
        y = f"h*0.80-text_h"
    else:
        y = "(h-text_h)/2"
    vf = (f"scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=increase,crop={CANVAS_W}:{CANVAS_H},"
          f"drawtext=textfile='{txtfile}':fontcolor=yellow:fontsize=92:borderw=6:bordercolor=black:"
          f"box=1:boxcolor=black@0.45:boxborderw=26:line_spacing=12:x=(w-text_w)/2:y={y}")
    r = subprocess.run([ffmpeg, "-y", "-i", str(image), "-vf", vf, "-frames:v", "1", "-q:v", "3", str(out)],
                       capture_output=True, text=True)
    txtfile.unlink(missing_ok=True)
    if not out.exists():
        sys.stderr.write(r.stderr[-1000:])
        raise SystemExit("No se pudo generar la miniatura.")


def _append(reel_video: Path, thumb: Path, ffmpeg: str) -> None:
    """Añade la miniatura (HOLD s, silencio) al final del reel. Re-encode con concat
    filter (siempre funciona aunque difieran parámetros)."""
    tmp = reel_video.with_name(reel_video.stem + "_wt.mp4")
    fc = (f"[1:v]scale={CANVAS_W}:{CANVAS_H},setsar=1,fps=30[t];"
          f"[0:a]aformat=sample_rates=44100:channel_layouts=stereo[a0];"
          f"[2:a]aformat=sample_rates=44100:channel_layouts=stereo[a2];"
          f"[0:v][a0][t][a2]concat=n=2:v=1:a=1[v][a]")
    cmd = [ffmpeg, "-y", "-i", str(reel_video), "-loop", "1", "-t", f"{HOLD}", "-i", str(thumb),
           "-f", "lavfi", "-t", f"{HOLD}", "-i", "anullsrc=r=44100:cl=stereo",
           "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-r", "30", "-movflags", "+faststart", "-c:a", "aac", "-b:a", "160k", str(tmp)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if not tmp.exists():
        sys.stderr.write(r.stderr[-1200:])
        raise SystemExit("No se pudo añadir la miniatura al final del reel.")
    tmp.replace(reel_video)


def main() -> None:
    ap = argparse.ArgumentParser(description="Genera la miniatura del reel y la añade al final")
    ap.add_argument("--reel", required=True)
    ap.add_argument("--hook", required=True)
    ap.add_argument("--position", default="bottom", choices=["top", "center", "bottom"])
    ap.add_argument("--image", default="", help="imagen propia; si falta, se genera con ComfyUI")
    ap.add_argument("--ffmpeg", default="ffmpeg")
    args = ap.parse_args()

    root = Path.cwd()
    db.init(root / "backend" / "runs" / "jobs.db")
    reel = db.get_reel(args.reel)
    if not reel or not reel.get("video") or not (root / reel["video"]).exists():
        raise SystemExit("El reel no tiene vídeo compuesto.")
    reel_video = root / reel["video"]

    # Imagen: propia, o generada con ComfyUI (prompt anclado al gancho/guion).
    if args.image and (root / args.image).exists():
        image = root / args.image
    else:
        from app.services import comfy_client  # noqa: E402
        from app.services.reel_engine import broll_prompts_for  # noqa: E402
        if not comfy_client.is_up():
            raise SystemExit("ComfyUI no responde (para generar la imagen de la miniatura).")
        base = args.hook or (reel.get("script") or "")[:120]
        prompt = broll_prompts_for([base])[0]
        print(f"Generando imagen de miniatura: {prompt[:70]}...", flush=True)
        image = reel_video.with_name(reel_video.stem + "_thumbimg.jpg")
        comfy_client.generate_image(prompt, image)

    thumb = reel_video.with_name(reel_video.stem + "_thumb.jpg")
    print("Componiendo miniatura (imagen + gancho)...", flush=True)
    _thumb_frame(image, args.hook, args.position, thumb, args.ffmpeg)
    print("Añadiéndola al final del reel...", flush=True)
    _append(reel_video, thumb, args.ffmpeg)
    print(f"Miniatura añadida: {reel_video}", flush=True)


if __name__ == "__main__":
    main()
