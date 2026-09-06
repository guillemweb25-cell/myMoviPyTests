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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app import db  # noqa: E402

CANVAS_W, CANVAS_H = 1080, 1920
HOLD = 2.5
FONT_ANTON = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "Anton-Regular.ttf"


def _split_two(text: str) -> tuple[str, str]:
    """Parte el gancho en 2 líneas (como videos_automaticos): por '...' si lo hay,
    o por la mitad si son >4 palabras; si no, una sola línea."""
    text = text.strip()
    if "..." in text:
        a, b = text.split("...", 1)
        return a.strip() + "...", (("..." + b.strip()) if b.strip() else "")
    words = text.split()
    if len(words) > 4:
        h = len(words) // 2
        return " ".join(words[:h]) + "...", "..." + " ".join(words[h:])
    return text, ""


def _thumb_frame(image: Path, hook: str, position: str, out: Path, ffmpeg: str) -> None:
    """Miniatura estilo videos_automaticos: imagen a cover 1080x1920 + gancho en
    fuente condensada (Anton) MAYÚSCULAS, línea 1 degradado amarillo→dorado y
    línea 2 naranja, con contorno negro y scrim oscuro detrás. Posición top/center/bottom."""
    from PIL import Image, ImageDraw, ImageFont  # noqa: E402

    img = Image.open(image).convert("RGBA")
    # cover 1080x1920
    scale = max(CANVAS_W / img.width, CANVAS_H / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)))
    left = (img.width - CANVAS_W) // 2
    top = (img.height - CANVAS_H) // 2
    img = img.crop((left, top, left + CANVAS_W, top + CANVAS_H))
    W, H = img.size
    draw = ImageDraw.Draw(img)

    font_path = str(FONT_ANTON) if FONT_ANTON.exists() else None
    line1, line2 = _split_two(hook)
    line1, line2 = line1.upper(), line2.upper()
    base_dim = min(W, H)

    def fit(text: str, start: int, max_w: float) -> "ImageFont.FreeTypeFont":
        size = start
        while size > 12:
            f = ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()
            if not font_path:
                return f
            b = draw.textbbox((0, 0), text, font=f, stroke_width=8)
            if (b[2] - b[0]) <= max_w:
                return f
            size -= 4
        return ImageFont.truetype(font_path, size) if font_path else ImageFont.load_default()

    max_w = W * 0.92
    f1 = fit(line1, int(base_dim * 0.16), max_w)
    f2 = fit(line2, int(base_dim * 0.11), max_w) if line2 else f1
    ow1, ow2 = 8, 6
    b1 = draw.textbbox((0, 0), line1, font=f1, stroke_width=ow1)
    h1 = b1[3] - b1[1]
    h2 = 0
    b2 = (0, 0, 0, 0)
    if line2:
        b2 = draw.textbbox((0, 0), line2, font=f2, stroke_width=ow2)
        h2 = b2[3] - b2[1]
    gap = int(base_dim * 0.11 * 0.25)
    h_stack = h1 + ((gap + h2) if line2 else 0)

    pos = (position or "bottom").lower()
    if pos == "bottom":
        stack_y = int(H * 0.94) - h_stack
        scrim_anchor = "bottom"
    elif pos == "center":
        stack_y = (H - h_stack) // 2
        scrim_anchor = "center"
    else:
        stack_y = int(H * 0.05)
        scrim_anchor = "top"

    # Scrim oscuro degradado detrás del texto (para leerse sobre cualquier imagen).
    if scrim_anchor == "center":
        scrim_h = min(H, h_stack + int(H * 0.22))
        scrim_y = max(0, stack_y - int(H * 0.11))
    else:
        scrim_h = int(H * 0.42)
        scrim_y = 0 if scrim_anchor == "top" else H - scrim_h
    alpha = Image.new("L", (1, scrim_h))
    for yy in range(scrim_h):
        t = yy / max(1, scrim_h - 1)
        if scrim_anchor == "top":
            v = 205 * (1 - t)
        elif scrim_anchor == "bottom":
            v = 205 * t
        else:
            v = 205 * (1 - abs(2 * t - 1))
        alpha.putpixel((0, yy), int(v))
    scrim = Image.new("RGBA", (W, scrim_h), (0, 0, 0, 255))
    scrim.putalpha(alpha.resize((W, scrim_h)))
    img.alpha_composite(scrim, (0, scrim_y))
    draw = ImageDraw.Draw(img)

    def grad_text(text: str, y: int, font, top_c, bot_c, outline_w) -> None:
        b = draw.textbbox((0, 0), text, font=font, stroke_width=outline_w)
        tw = b[2] - b[0]
        x = (W - tw) // 2 - b[0]
        # contorno negro
        draw.text((x, y), text, font=font, fill=(0, 0, 0, 0), stroke_width=outline_w, stroke_fill="black")
        # relleno degradado vertical a través de una máscara
        grad = Image.new("RGB", (1, H))
        for yy in range(H):
            t = yy / max(1, H - 1)
            grad.putpixel((0, yy), tuple(int(top_c[i] * (1 - t) + bot_c[i] * t) for i in range(3)))
        grad = grad.resize((W, H)).convert("RGBA")
        mask = Image.new("L", (W, H), 0)
        ImageDraw.Draw(mask).text((x, y), text, font=font, fill=255)
        img.paste(grad, (0, 0), mask)

    def outline_text(text: str, y: int, font, color, outline_w) -> None:
        b = draw.textbbox((0, 0), text, font=font, stroke_width=outline_w)
        x = (W - (b[2] - b[0])) // 2 - b[0]
        draw.text((x, y), text, font=font, fill=color, stroke_width=outline_w, stroke_fill="black")

    y1 = stack_y - b1[1]
    if line1:
        grad_text(line1, y1, f1, (255, 235, 60), (255, 185, 40), ow1)
        draw = ImageDraw.Draw(img)
    if line2:
        y2 = stack_y + h1 + gap - b2[1]
        outline_text(line2, y2, f2, (255, 120, 30), ow2)

    img.convert("RGB").save(out, "JPEG", quality=90)
    if not out.exists():
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
    ap = argparse.ArgumentParser(description="Miniatura del reel (preview / añadir al final)")
    ap.add_argument("--reel", required=True)
    ap.add_argument("--hook", default="")
    ap.add_argument("--position", default="bottom", choices=["top", "center", "bottom"])
    ap.add_argument("--image", default="", help="imagen propia; si falta, se genera con ComfyUI")
    ap.add_argument("--mode", default="preview", choices=["preview", "append"])
    ap.add_argument("--regen-image", action="store_true", help="fuerza generar una imagen nueva")
    ap.add_argument("--ffmpeg", default="ffmpeg")
    args = ap.parse_args()

    root = Path.cwd()
    db.init(root / "backend" / "runs" / "jobs.db")
    reel = db.get_reel(args.reel)
    if not reel or not reel.get("video") or not (root / reel["video"]).exists():
        raise SystemExit("El reel no tiene vídeo compuesto.")
    reel_video = root / reel["video"]
    thumbimg = reel_video.with_name(reel_video.stem + "_thumbimg.jpg")  # imagen base
    thumb = reel_video.with_name(reel_video.stem + "_thumb.jpg")        # miniatura final

    if args.mode == "append":
        if not thumb.exists():
            raise SystemExit("No hay miniatura previsualizada que añadir.")
        print("Añadiendo la miniatura al final del reel...", flush=True)
        _append(reel_video, thumb, args.ffmpeg)
        print(f"Miniatura añadida: {reel_video}", flush=True)
        return

    # PREVIEW: decide la imagen base (propia / reusa la generada / genera nueva).
    if args.image and (root / args.image).exists():
        image = root / args.image
    elif thumbimg.exists() and not args.regen_image:
        image = thumbimg  # reusar la imagen ya generada (solo re-quemar el texto)
    else:
        from app.services import comfy_client  # noqa: E402
        from app.services.reel_engine import thumbnail_prompt, content_text  # noqa: E402
        if not comfy_client.is_up():
            raise SystemExit("ComfyUI no responde (para generar la imagen de la miniatura).")
        # Imagen ANCLADA a lo que REALMENTE dice el reel (transcribe si el guion está
        # vacío, p. ej. generaciones recuperadas), no al gancho clickbait.
        if not (reel.get("script") or "").strip():
            print("Sin guion guardado: transcribiendo el audio para anclar la imagen...", flush=True)
        script = content_text(reel, root)
        if script and not (reel.get("script") or "").strip():
            db.update_reel(args.reel, {"script": script})  # backfill
        prompt = thumbnail_prompt(script or args.hook)
        print(f"Generando imagen de miniatura: {prompt[:70]}...", flush=True)
        comfy_client.generate_image(prompt, thumbimg)
        image = thumbimg

    print("Componiendo miniatura (imagen + gancho)...", flush=True)
    _thumb_frame(image, args.hook, args.position, thumb, args.ffmpeg)
    print(f"THUMB: {thumb.relative_to(root)}", flush=True)


if __name__ == "__main__":
    main()
