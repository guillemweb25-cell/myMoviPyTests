#!/usr/bin/env python3

import argparse
from pathlib import Path
import numpy as np
from PIL import Image
from moviepy import VideoClip, ImageClip, concatenate_videoclips

EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def ken_burns_clip(img_path, duration, out_w, out_h, z0, z1):
    # cargamos imagen base
    base = Image.open(img_path).convert("RGB")
    W0, H0 = base.size

    # escala mínima para cubrir el canvas
    scale_base = max(out_w / W0, out_h / H0)

    def make_frame(t):
        # zoom lineal
        z = z0 + (z1 - z0) * (t / duration)
        scale = scale_base * z

        # tamaño escalado
        new_w = int(W0 * scale)
        new_h = int(H0 * scale)

        # reescalar con Pillow
        img_resized = base.resize((new_w, new_h), Image.LANCZOS)
        arr = np.array(img_resized)

        # crop centrado
        x_center = new_w // 2
        y_center = new_h // 2

        x1 = x_center - out_w // 2
        y1 = y_center - out_h // 2
        x2 = x1 + out_w
        y2 = y1 + out_h

        # recorte final
        frame = arr[y1:y2, x1:x2].copy()
        return frame

    # clip por función de frame (MoviePy 2.x)
    return VideoClip(make_frame, duration=duration)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", required=True)
    ap.add_argument("--out", default="kenburns.mp4")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--duration", type=float, default=6)
    args = ap.parse_args()

    folder = Path(args.folder)
    imgs = sorted([p for p in folder.iterdir() if p.suffix.lower() in EXTS])

    clips = []
    for i, img in enumerate(imgs):
        if i % 2 == 0:
            z0, z1 = 1.0, 1.08
        else:
            z0, z1 = 1.08, 1.0

        clips.append(
            ken_burns_clip(
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
