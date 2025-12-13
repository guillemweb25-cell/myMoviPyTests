#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations
import argparse
import subprocess
from pathlib import Path
import shlex

IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

def run(cmd: list[str]) -> None:
    print(">", " ".join(shlex.quote(c) for c in cmd))
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(p.stderr.strip() or f"ffmpeg falló (code={p.returncode})")

def main():
    ap = argparse.ArgumentParser(description="Crea un vídeo a partir de imágenes (slideshow).")
    ap.add_argument("--folder", required=True, help="Carpeta con imágenes")
    ap.add_argument("--out", required=True, help="Salida MP4, ej: nombre_video.mp4")
    ap.add_argument("--time", type=float, required=True, help="Segundos por imagen (ej: 3)")
    ap.add_argument("--fps", type=int, default=30, help="FPS del vídeo (default: 30)")
    ap.add_argument("--w", type=int, default=1280, help="Ancho salida (default: 1280)")
    ap.add_argument("--h", type=int, default=720, help="Alto salida (default: 720)")
    ap.add_argument("--sort", choices=["name", "mtime"], default="name", help="Orden de imágenes")
    args = ap.parse_args()

    folder = Path(args.folder).expanduser().resolve()
    out = Path(args.out).expanduser().resolve()

    if not folder.is_dir():
        raise SystemExit(f"No existe la carpeta: {folder}")

    imgs = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMG_EXTS]
    if not imgs:
        raise SystemExit(f"No hay imágenes en {folder} ({', '.join(sorted(IMG_EXTS))})")

    if args.sort == "mtime":
        imgs.sort(key=lambda p: p.stat().st_mtime)
    else:
        imgs.sort(key=lambda p: p.name.lower())

    # archivo concat para ffmpeg
    concat_txt = folder / "_ffconcat_images.txt"
    lines = []
    for p in imgs:
        # duration aplica al archivo *anterior*, por eso repetimos el último al final
        lines.append(f"file {p.as_posix()!r}")
        lines.append(f"duration {args.time}")
    lines.append(f"file {imgs[-1].as_posix()!r}")
    concat_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")

    out.parent.mkdir(parents=True, exist_ok=True)

    # scale "cover" sin bandas: escala y recorta al centro
    vf = (
        f"scale={args.w}:{args.h}:force_original_aspect_ratio=increase,"
        f"crop={args.w}:{args.h},"
        f"fps={args.fps},format=yuv420p"
    )

    cmd = [
        "ffmpeg", "-y",
        "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_txt),
        "-vf", vf,
        "-c:v", "libx264",
        "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(out),
    ]
    run(cmd)

    try:
        concat_txt.unlink(missing_ok=True)
    except Exception:
        pass

    print(f"[OK] Generado: {out}")

if __name__ == "__main__":
    main()
