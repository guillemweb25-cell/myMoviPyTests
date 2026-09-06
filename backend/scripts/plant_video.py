#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JOB: vídeo de crecimiento de planta en time-lapse (estilo plant_growth) con WAN 2.2.

Plan (LLM) → primera imagen (maceta vacía, ComfyUI/SDXL) → 3 clips WAN i2v
encadenados por el ÚLTIMO FOTOGRAMA (clip N empieza donde acabó N-1) → montaje
vertical continuo. Usa la GPU del Windows (ComfyUI). Sin música (ASMR/diegético).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app import db  # noqa: E402
from app.services import comfy_client, wan_client  # noqa: E402
from app.services.plant_engine import plant_plan  # noqa: E402


def _last_frame(video: Path, out: Path, ffmpeg: str = "ffmpeg") -> bool:
    """Extrae el último fotograma del vídeo (para encadenar el siguiente clip)."""
    subprocess.run([ffmpeg, "-y", "-sseof", "-0.2", "-i", str(video), "-update", "1",
                    "-frames:v", "1", "-q:v", "2", str(out)], capture_output=True, text=True)
    return out.exists()


def _normalize(clip: Path, out: Path, w: int, h: int, ffmpeg: str = "ffmpeg") -> None:
    """Clip WAN (webm) → mp4 normalizado a WxH (cover), 30 fps, mudo."""
    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps=30"
    subprocess.run([ffmpeg, "-y", "-i", str(clip), "-vf", vf, "-an",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-r", "30", str(out)], capture_output=True, text=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Vídeo de maceta (time-lapse) con WAN i2v")
    ap.add_argument("--plant", required=True, help="id del registro en la BD")
    ap.add_argument("--length", type=int, default=97, help="frames por clip (~4s a 24fps)")
    ap.add_argument("--ffmpeg", default="ffmpeg")
    args = ap.parse_args()

    root = Path.cwd()
    db.init(root / "backend" / "runs" / "jobs.db")
    rec = db.get_plant(args.plant)
    if not rec:
        raise SystemExit(f"Registro {args.plant} no encontrado.")

    if not comfy_client.is_up():
        raise SystemExit("ComfyUI no responde (¿encendido en el Windows y la GPU libre?).")

    aspect = rec.get("aspect") or "9:16"
    wan_w, wan_h = (480, 832) if aspect == "9:16" else (832, 480)
    out_w, out_h = (1080, 1920) if aspect == "9:16" else (1920, 1080)

    out_dir = root / "output" / "plants" / args.plant
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) Plan (escena bloqueada + prompt de imagen + 3 prompts de animación).
    print("1/5 Generando el plan (escena + prompts)...", flush=True)
    plan = plant_plan(rec.get("plant") or "lemon", aspect)
    db.update_plant(args.plant, {"image_prompt": plan["image_prompt"], "clips": plan["clips"]})
    clips_prompts = plan["clips"]

    # 2) Primera imagen: maceta con SOLO tierra, sin nada plantado. SDXL tiende a meter
    # una planta ya crecida, así que se refuerza en positivo y con un negativo fuerte.
    print("2/5 Generando la primera imagen (maceta vacía)...", flush=True)
    img_prompt = (f"photorealistic, {plan.get('locked_scene', '')}, the pot is filled to the brim "
                  "with fresh dark brown bare soil, smooth flat empty soil surface, close-up of bare "
                  "topsoil, nothing planted at all, vertical, soft daylight, sharp focus, ultra detailed, no text")
    empty_neg = ("(plant:1.6), (sprout:1.6), (seedling:1.6), (leaves:1.6), (foliage:1.6), (green:1.4), "
                 "(stem:1.5), (branch:1.4), (tree:1.5), (sapling:1.5), (flower:1.5), (bud:1.4), (grass:1.4), "
                 "(weeds:1.4), (moss:1.4), (vegetation:1.5), (succulent:1.5), (aloe:1.5), (cactus:1.4), "
                 "(greenery:1.5), growing plant, green shoots, watermark, text, logo, low quality, blurry")
    first = out_dir / "frame_start.jpg"
    comfy_client.generate_image(img_prompt, first, width=wan_w, height=wan_h, negative=empty_neg)

    # 3) 3 clips WAN encadenados por el último fotograma.
    start_img = first
    norm_clips = []
    for i, prompt in enumerate(clips_prompts):
        print(f"3/5 Clip {i + 1}/3 con WAN (puede tardar)...", flush=True)
        raw = out_dir / f"clip_{i}_raw.mp4"
        wan_client.generate_video(start_img, raw, prompt, width=wan_w, height=wan_h, length=args.length)
        norm = out_dir / f"clip_{i}.mp4"
        _normalize(raw, norm, out_w, out_h, args.ffmpeg)
        if not norm.exists():
            raise SystemExit(f"Falló normalizando el clip {i + 1}.")
        norm_clips.append(norm)
        # Encadena: último fotograma → inicio del siguiente.
        nxt = out_dir / f"frame_{i}.jpg"
        if _last_frame(norm, nxt, args.ffmpeg):
            start_img = nxt

    # 4) Montaje continuo (concat demuxer, mismos parámetros → copy).
    print("4/5 Uniendo los clips...", flush=True)
    listfile = out_dir / "concat.txt"
    listfile.write_text("\n".join(f"file '{c.resolve()}'" for c in norm_clips), encoding="utf-8")
    out = out_dir / "video.mp4"
    rc = subprocess.run([args.ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
                         "-c", "copy", "-movflags", "+faststart", str(out)],
                        capture_output=True, text=True)
    if rc.returncode != 0 or not out.exists():
        sys.stderr.write(rc.stderr[-1200:])
        raise SystemExit("Falló uniendo los clips.")
    listfile.unlink(missing_ok=True)

    # 5) Persistir.
    db.update_plant(args.plant, {"image_path": str(first.relative_to(root)),
                                 "video_path": str(out.relative_to(root))})
    print(f"5/5 ✅ Vídeo de maceta listo: {out}", flush=True)


if __name__ == "__main__":
    main()
