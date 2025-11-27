#!/usr/bin/env python
# make_kenburns.py

import argparse
from pathlib import Path

# --- parche Pillow para moviepy 1.0.3 (ANTIALIAS eliminado en versiones nuevas) ---
from PIL import Image as PILImage
if not hasattr(PILImage, "ANTIALIAS"):
    PILImage.ANTIALIAS = PILImage.Resampling.LANCZOS

from moviepy.editor import ImageClip, concatenate_videoclips, vfx

EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


def ken_burns_clip(img_path: Path, duration: float, size, z0: float, z1: float):
    W, H = size
    img = ImageClip(str(img_path))

    # Escala base para cubrir el frame
    base = max(W / img.w, H / img.h)
    img = img.resize(base)

    # Zoom progresivo desde z0 a z1 (multiplicadores sobre la imagen ya escalada)
    def zoom_factor(t):
        return z0 + (z1 - z0) * (t / float(duration))

    clip = (
        img.set_duration(duration)
           .fx(vfx.resize, lambda t: base * zoom_factor(t))
           .set_position("center")
    )

    # Recorte centrado al tamaño final
    clip = clip.crop(width=W, height=H,
                     x_center=clip.w / 2,
                     y_center=clip.h / 2)

    return clip


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", required=True, help="Carpeta con imágenes")
    parser.add_argument("--duration", type=float, default=6.0,
                        help="Segundos por imagen")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--output", default="output.mp4")
    args = parser.parse_args()

    folder = Path(args.folder)
    imgs = sorted(p for p in folder.iterdir() if p.suffix.lower() in EXTS)
    if not imgs:
        raise SystemExit("No hay imágenes válidas en esa carpeta")

    size = (args.width, args.height)

    clips = []
    for i, img in enumerate(imgs):
        # alterna zoom in / out
        if i % 2 == 0:
            z0, z1 = 1.0, 1.08
        else:
            z0, z1 = 1.08, 1.0
        clips.append(ken_burns_clip(img, args.duration, size, z0, z1))

    final = concatenate_videoclips(clips, method="compose")
    final.write_videofile(
        args.output,
        fps=args.fps,
        codec="libx264",
        audio=False,
    )


if __name__ == "__main__":
    main()
