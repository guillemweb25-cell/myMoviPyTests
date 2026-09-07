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
    ap = argparse.ArgumentParser(description="Vídeo de maceta (time-lapse)")
    ap.add_argument("--plant", required=True, help="id del registro en la BD")
    ap.add_argument("--provider", default="grok", choices=["grok", "wan"],
                    help="grok=1 clip continuo (xAI, de pago); wan=3 clips locales (GPU)")
    ap.add_argument("--duration", type=int, default=8, help="segundos del clip (solo grok)")
    ap.add_argument("--length", type=int, default=97, help="frames por clip (solo wan)")
    ap.add_argument("--ffmpeg", default="ffmpeg")
    args = ap.parse_args()

    root = Path.cwd()
    db.init(root / "backend" / "runs" / "jobs.db")
    rec = db.get_plant(args.plant)
    if not rec:
        raise SystemExit(f"Registro {args.plant} no encontrado.")

    # WAN necesita ComfyUI (imagen SDXL + vídeo). Grok NO usa ComfyUI: hace también
    # la primera imagen (grok-imagine-image), que sí sale con la maceta vacía.
    if args.provider == "wan" and not comfy_client.is_up():
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

    # 2) Primera imagen: maceta con SOLO tierra, sin nada plantado.
    print("2/5 Generando la primera imagen (maceta vacía)...", flush=True)
    ar = "vertical portrait 9:16" if aspect == "9:16" else "horizontal 16:9"
    img_prompt = (f"photorealistic, {plan.get('locked_scene', '')}, the pot is filled to the brim with "
                  f"fresh dark brown bare soil, smooth flat empty soil surface, absolutely nothing "
                  f"growing, no plant, no sprout, {ar}, soft daylight, sharp focus, ultra detailed, no text")
    first = out_dir / "frame_start.jpg"
    if args.provider == "grok":
        from app.services import grok_video as _gv  # noqa: E402
        _gv.generate_image(img_prompt, first)   # grok-imagine-image (sí sale vacía)
    else:
        empty_neg = ("(plant:1.6), (sprout:1.6), (seedling:1.6), (leaves:1.6), (foliage:1.6), (green:1.4), "
                     "(stem:1.5), (branch:1.4), (tree:1.5), (sapling:1.5), (flower:1.5), (bud:1.4), (grass:1.4), "
                     "(weeds:1.4), (moss:1.4), (vegetation:1.5), (succulent:1.5), (aloe:1.5), (cactus:1.4), "
                     "(greenery:1.5), growing plant, green shoots, watermark, text, logo, low quality, blurry")
        comfy_client.generate_image(img_prompt, first, width=wan_w, height=wan_h, negative=empty_neg)

    out = out_dir / "video.mp4"

    if args.provider == "grok":
        # 3) UN clip continuo con Grok Imagine (imagen→vídeo): crecimiento fluido de
        # semilla a planta madura en un solo plano. Mucho mejor que encadenar clips WAN.
        from app.services import grok_video  # noqa: E402
        if not grok_video.is_configured():
            raise SystemExit("Falta GROK_API_KEY en .env.")
        scene = plan.get("locked_scene", "")
        plant_name = rec.get("plant") or "plant"
        grow_prompt = (
            f"{scene} Continuous smooth time-lapse: starting from the bare empty soil, a seed "
            f"sprouts and the {plant_name} grows steadily and organically — the shoot rises, leaves "
            f"unfurl one after another, the plant fills out and matures, then buds, flowers and "
            f"(for a fruiting plant) ripe fruit appear on it by the end. The growth is gradual and "
            f"continuous the whole time, never jumping. Locked static camera, no zoom or pan. Day "
            f"and night light cycles pass, shadows sweep. NO hands, no people, nothing enters frame.")
        print(f"3/4 Generando el clip continuo con Grok ({args.duration}s)...", flush=True)
        raw = out_dir / "grok_raw.mp4"
        grok_video.generate_video(first, raw, grow_prompt, duration=args.duration)
        print("4/4 Normalizando a vertical...", flush=True)
        _normalize(raw, out, out_w, out_h, args.ffmpeg)
        if not out.exists():
            raise SystemExit("Falló normalizando el clip de Grok.")
    else:
        # 3) 3 clips WAN encadenados por el último fotograma (local, GPU).
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
            nxt = out_dir / f"frame_{i}.jpg"
            if _last_frame(norm, nxt, args.ffmpeg):
                start_img = nxt
        print("4/5 Uniendo los clips...", flush=True)
        listfile = out_dir / "concat.txt"
        listfile.write_text("\n".join(f"file '{c.resolve()}'" for c in norm_clips), encoding="utf-8")
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
