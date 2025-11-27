#!/usr/bin/env python3
# make_kenburns_tiktok.py  (para MoviePy 2.x)

import argparse
from pathlib import Path

import numpy as np
from PIL import Image
from moviepy import VideoClip, concatenate_videoclips

EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def ken_burns_tiktok_clip(img_path, duration, out_w, out_h, z0, z1):
    base = Image.open(img_path).convert("RGB")
    W0, H0 = base.size

    # escala mínima para cubrir el lienzo
    scale_base = max(out_w / W0, out_h / H0)

    def make_frame(t):
        s = t / duration  # 0→1

        # easing suave
        ease = s * s * (3 - 2 * s)

        # zoom más fuerte
        zoom = z0 + (z1 - z0) * ease      # ej. 1.0 → 1.25
        scale = scale_base * zoom

        new_w = int(W0 * scale)
        new_h = int(H0 * scale)
        img_resized = base.resize((new_w, new_h), Image.LANCZOS)
        arr = np.array(img_resized)

        # paneo horizontal suave
        pan_amp = int(new_w * 0.12)   # 12% del ancho
        pan = np.sin(np.pi * (s - 0.5))
        x_center = new_w // 2 + int(pan_amp * pan)
        y_center = new_h // 2

        x1 = x_center - out_w // 2
        y1 = y_center - out_h // 2
        x1 = max(0, min(x1, new_w - out_w))
        y1 = max(0, min(y1, new_h - out_h))
        x2 = x1 + out_w
        y2 = y1 + out_h

        frame = arr[y1:y2, x1:x2].copy()
        return frame

    return VideoClip(make_frame, duration=duration)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", required=True)
    ap.add_argument("--out", default="kenburns_tiktok.mp4")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--duration", type=float, default=6)
    args = ap.parse_args()

    folder = Path(args.folder)
    imgs = sorted([p for p in folder.iterdir() if p.suffix.lower() in EXTS])

    clips = []
    for i, img in enumerate(imgs):
        # alterna push-in / push-out
        if i % 2 == 0:
            z0, z1 = 1.0, 1.25
        else:
            z0, z1 = 1.25, 1.0

        clips.append(
            ken_burns_tiktok_clip(
                img,
                duration=args.duration,
                out_w=args.width,
                out_h=args.height,
                z0=z0,
                z1=z1,
            )
        )

    final = concatenate_videoclips(clips)
    final.write_videofile(args.out, fps=args.fps, codec="libx264", audio=False)


if __name__ == "__main__":
    main()
