#!/usr/bin/env python3
# make_overlay_kenburns.py  (basat en el teu script, MoviePy 2.x)

import argparse
from pathlib import Path

import numpy as np
from PIL import Image
from moviepy import VideoClip, VideoFileClip, concatenate_videoclips

EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def ken_burns_tiktok_clip(img_path, duration, out_w, out_h, z0, z1):
    base = Image.open(img_path).convert("RGB")
    W0, H0 = base.size

    # escala mínima per cobrir el canvas
    scale_base = max(out_w / W0, out_h / H0)

    def make_frame(t):
        s = t / duration  # 0→1

        # easing suau
        ease = s * s * (3 - 2 * s)

        # zoom
        zoom = z0 + (z1 - z0) * ease
        scale = scale_base * zoom

        new_w = int(W0 * scale)
        new_h = int(H0 * scale)
        img_resized = base.resize((new_w, new_h), Image.LANCZOS)
        arr = np.array(img_resized)

        # paneig horitzontal
        pan_amp = int(new_w * 0.12)
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


def blend_with_overlay(base_clip: VideoClip,
                       overlay_path: Path,
                       mode: str = "screen",
                       opacity: float = 0.9) -> VideoClip:
    """Superposa l'overlay fent-lo loop durant TOTA la durada del base."""
    ov = VideoFileClip(str(overlay_path))

    def make_frame(t):
        fb = base_clip.get_frame(t).astype(float) / 255.0
        # loop de l'overlay
        fo = ov.get_frame(t % ov.duration).astype(float) / 255.0

        fo = fo * opacity

        if mode == "normal":
            out = fb * (1.0 - opacity) + fo
        else:
            # SCREEN: fons negre a l'overlay
            out = 1.0 - (1.0 - fb) * (1.0 - fo)

        return (out * 255.0).clip(0, 255).astype("uint8")

    # ara dura igual que el Ken Burns amb totes les fotos
    return VideoClip(make_frame, duration=base_clip.duration)



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", required=True, help="Carpeta d’imatges")
    ap.add_argument("--overlay", required=True, help="Vídeo overlay .mp4/.mov")
    ap.add_argument("--out", default="kenburns_overlay.mp4")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--duration", type=float, default=6)
    ap.add_argument("--opacity", type=float, default=0.9)
    ap.add_argument("--blend", choices=["normal", "screen"], default="screen")
    args = ap.parse_args()

    folder = Path(args.folder)
    imgs = sorted([p for p in folder.iterdir() if p.suffix.lower() in EXTS])

    if not imgs:
        raise SystemExit(f"No s'han trobat imatges a {folder}")

    clips = []
    for i, img in enumerate(imgs):
        # alterna zoom in / zoom out com al teu script
        if i % 2 == 0:
            z0, z1 = 1.0, 1.25
        else:
            z0, z1 = 1.25, 1.0

        clips.append(
            ken_burns_tiktok_clip(
                img_path=img,
                duration=args.duration,
                out_w=args.width,
                out_h=args.height,
                z0=z0,
                z1=z1,
            )
        )

    base = concatenate_videoclips(clips)
    final = blend_with_overlay(
        base_clip=base,
        overlay_path=Path(args.overlay),
        mode=args.blend,
        opacity=args.opacity,
    )

    final.write_videofile(args.out, fps=args.fps, codec="libx264", audio=False)


if __name__ == "__main__":
    main()
