#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image

from moviepy import (
    ImageClip,
    VideoClip,
    CompositeVideoClip,
    vfx,
)

EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


# ---------------------------
# Duraciones desde JSON
# ---------------------------

def load_durations_from_json(json_path: Path) -> list[float]:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    durations: list[float] = []
    for item in data.get("items", []):
        secs = float(item.get("seconds") or 0.0)
        spi = item.get("seconds_per_image")
        if spi is None:
            img_count = int(item.get("images_count") or len(item.get("prompts") or []))
            spi = secs / img_count if img_count else secs
        spi = float(spi)
        for _ in item.get("prompts") or []:
            durations.append(spi)
    return durations


# ---------------------------
# Ken Burns
# ---------------------------

BASE_DURATION = 6.0
BASE_DELTA_Z = 0.08
ZOOM_SPEED = BASE_DELTA_Z / BASE_DURATION  # zoom por segundo

def zoom_for_duration(duration: float, zmin: float, zmax: float) -> tuple[float, float]:
    ideal = 1.0 + ZOOM_SPEED * duration
    z1 = max(zmin, min(zmax, ideal))
    return 1.0, z1

def ken_burns_clip(
    img_path: Path,
    duration: float,
    out_w: int,
    out_h: int,
    z0: float,
    z1: float,
    mode: str = "linear",   # linear | pingpong
) -> VideoClip:
    base = Image.open(img_path).convert("RGB")
    W0, H0 = base.size
    scale_base = max(out_w / W0, out_h / H0)  # cover

    def zoom_factor(t: float) -> float:
        u = t / max(duration, 1e-6)
        if mode == "pingpong":
            if u <= 0.5:
                v = u / 0.5
                return z0 + (z1 - z0) * v
            v = (u - 0.5) / 0.5
            return z1 - (z1 - z0) * v
        return z0 + (z1 - z0) * u

    def make_frame(t: float):
        z = zoom_factor(t)
        scale = scale_base * z

        new_w = max(1, int(W0 * scale))
        new_h = max(1, int(H0 * scale))

        img_resized = base.resize((new_w, new_h), Image.LANCZOS)
        arr = np.asarray(img_resized)

        x_center = new_w // 2
        y_center = new_h // 2

        x1 = x_center - out_w // 2
        y1 = y_center - out_h // 2

        # clamp (por seguridad ante redondeos)
        x1 = max(0, min(x1, new_w - out_w))
        y1 = max(0, min(y1, new_h - out_h))

        frame = arr[y1:y1 + out_h, x1:x1 + out_w].copy()
        return frame

    return VideoClip(make_frame, duration=duration)


# ---------------------------
# Utilidades: cover/crop + zoom simple
# ---------------------------

def cover_crop(clip, w: int, h: int):
    c = clip.resized(height=h)
    if c.w < w:
        c = c.resized(width=w)
    return c.cropped(x_center=c.w/2, y_center=c.h/2, width=w, height=h)

def apply_zoom_motion(clip, motion: str, z0: float, z1: float):
    if motion == "none":
        return clip
    if motion == "zoom_in":
        a, b = z0, z1
    elif motion == "zoom_out":
        a, b = z1, z0
    else:
        return clip

    dur = clip.duration

    def factor(t):
        if dur <= 0:
            return a
        return a + (b - a) * (t / dur)

    return clip.with_effects([vfx.Resize(factor)])


# ---------------------------
# Transiciones: fade + slide
# ---------------------------

def apply_transition_fx(clip, transition: str, tlen: float):
    if transition == "fade" and tlen > 0:
        return clip.with_effects([vfx.FadeIn(tlen), vfx.FadeOut(tlen)])
    return clip

def slide_position_functions(w: int, transition: str, tlen: float):
    def outgoing(duration: float):
        def f(t):
            if tlen <= 0 or transition not in ("slide_left", "slide_right"):
                return (0, 0)
            if t < duration - tlen:
                return (0, 0)
            p = (t - (duration - tlen)) / tlen  # 0..1
            return (-w * p, 0) if transition == "slide_left" else (w * p, 0)
        return f

    def incoming():
        def f(t):
            if tlen <= 0 or transition not in ("slide_left", "slide_right"):
                return (0, 0)
            if t < tlen:
                p = t / tlen
                return (w * (1 - p), 0) if transition == "slide_left" else (-w * (1 - p), 0)
            return (0, 0)
        return f

    return outgoing, incoming


# ---------------------------
# Main
# ---------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", required=True)
    ap.add_argument("--out", required=True)

    ap.add_argument("--w", type=int, default=1280)
    ap.add_argument("--h", type=int, default=720)
    ap.add_argument("--fps", type=int, default=30)

    ap.add_argument("--time", type=float, default=6.0, help="Duración por imagen si no hay JSON")
    ap.add_argument("--json-durations", type=str, help="Path a image_prompts_all.json")

    ap.add_argument("--transition", choices=["none", "fade", "slide_left", "slide_right"], default="none")
    ap.add_argument("--tlen", type=float, default=1.0, help="Duración transición")

    ap.add_argument("--motion", choices=["none", "zoom_in", "zoom_out", "kenburns"], default="none")
    ap.add_argument("--z0", type=float, default=1.00)
    ap.add_argument("--z1", type=float, default=1.12)

    ap.add_argument("--kb_mode", choices=["linear", "pingpong"], default="linear")
    ap.add_argument("--kb_zmin", type=float, default=1.08)
    ap.add_argument("--kb_zmax", type=float, default=1.35)

    args = ap.parse_args()

    folder = Path(args.folder)
    if not folder.is_dir():
        raise SystemExit("La carpeta no existe")

    imgs = sorted([p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in EXTS],
                  key=lambda p: p.name.lower())
    if not imgs:
        raise SystemExit("No hay imágenes")

    # duraciones
    if args.json_durations:
        durs = load_durations_from_json(Path(args.json_durations))
    else:
        durs = [args.time] * len(imgs)

    if len(durs) < len(imgs):
        durs = durs + [args.time] * (len(imgs) - len(durs))

    if args.transition != "none" and args.tlen > 0:
        if args.tlen >= min(durs):
            raise SystemExit("--tlen debe ser menor que la menor duración de imagen (por overlap).")

    outgoing_pos, incoming_pos = slide_position_functions(args.w, args.transition, args.tlen)

    # starts con overlap
    starts = [0.0]
    for i in range(1, len(imgs)):
        prev = durs[i - 1]
        step = prev - args.tlen if (args.transition != "none" and args.tlen > 0) else prev
        starts.append(starts[-1] + step)

    clips = []
    for i, img in enumerate(imgs):
        dur = float(durs[i])

        # --- generar clip base ---
        if args.motion == "kenburns":
            z_in_0, z_in_1 = zoom_for_duration(dur, args.kb_zmin, args.kb_zmax)
            if args.kb_mode == "linear":
                # alterna IN/OUT
                z0, z1 = (z_in_0, z_in_1) if (i % 2 == 0) else (z_in_1, z_in_0)
            else:
                z0, z1 = z_in_0, z_in_1

            c = ken_burns_clip(
                img_path=img,
                duration=dur,
                out_w=args.w,
                out_h=args.h,
                z0=z0,
                z1=z1,
                mode=args.kb_mode,
            )
        else:
            c = ImageClip(str(img)).with_duration(dur)
            c = cover_crop(c, args.w, args.h)
            c = apply_zoom_motion(c, args.motion, args.z0, args.z1)
            c = cover_crop(c, args.w, args.h)  # seguridad

        # --- transición ---
        c = apply_transition_fx(c, args.transition, args.tlen)

        # slide positions
        if args.transition in ("slide_left", "slide_right") and args.tlen > 0:
            if i == 0:
                c = c.with_position(outgoing_pos(c.duration))
            else:
                in_f = incoming_pos()
                if i < len(imgs) - 1:
                    out_f = outgoing_pos(c.duration)
                    def combo(t, in_f=in_f, out_f=out_f, d=c.duration, tl=args.tlen):
                        return in_f(t) if t < tl else out_f(t)
                    c = c.with_position(combo)
                else:
                    c = c.with_position(in_f)

        c = c.with_start(starts[i])
        clips.append(c)

    final = CompositeVideoClip(clips, size=(args.w, args.h))
    final.write_videofile(args.out, fps=args.fps, codec="libx264", audio=False)

if __name__ == "__main__":
    main()
