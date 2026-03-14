#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
from pathlib import Path
EXTS = {".png", ".jpg", ".jpeg", ".webp"}

from moviepy import ImageClip, concatenate_videoclips

def concatenar_imatges(img_dir: Path, seconds_per_image: float, output_file: Path, gap: float = 0.6):
    images = sorted([p for p in img_dir.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}])
    if not images:
        raise SystemExit(f"⚠️ No s'han trobat imatges a: {img_dir}")

    # Un clip per imatge, sense efectes (MoviePy v2)
    clips = [ImageClip(str(p)).with_duration(seconds_per_image) for p in images]

    # Concatena amb un espai negre entre clips (gap en segons)
    video = concatenate_videoclips(clips, method="compose", padding=gap)

    video.write_videofile(str(output_file), fps=24)
    print(f"✅ Vídeo creat amb tall negre de {gap}s entre fotos: {output_file}")



def main():
    ap = argparse.ArgumentParser(description="Concatena imatges en un vídeo (sense redimensionar).")
    ap.add_argument("--img-dir", required=True, help="Carpeta amb imatges")
    ap.add_argument("--seconds", type=float, default=2.0, help="Durada per imatge")
    ap.add_argument("--out", default="sortida.mp4", help="Fitxer de sortida")
    ap.add_argument("--fade", type=float, default=0.8, help="Durada del fade (seg.)")
    ap.add_argument("--gap", type=float, default=0.6, help="Durada del tall negre entre fotos (s)")

    args = ap.parse_args()

    img_dir = Path(args.img_dir)
    if not img_dir.exists():
        raise SystemExit(f"❌ No existeix la carpeta: {img_dir}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    concatenar_imatges(img_dir, args.seconds, out, gap=args.gap)

if __name__ == "__main__":
    main()
