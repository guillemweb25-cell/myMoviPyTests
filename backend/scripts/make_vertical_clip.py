#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Genera un clip vertical 1080x1920 con pantalla partida.

- Arriba (por defecto 50%): el segmento [start, end] del video, escalado al
  ancho y centrado (letterbox si hace falta).
- Abajo: por ahora un fondo derivado del propio clip (zoom + desenfoque). En una
  fase posterior esta mitad se rellenara con imagenes generadas por ComfyUI.

El corte y la composicion se hacen en una sola pasada de ffmpeg.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

CANVAS_W = 1080
CANVAS_H = 1920


def parse_timecode(value: str) -> float:
    """Acepta segundos (12.5) o HH:MM:SS(.ms) / MM:SS y devuelve segundos."""
    value = value.strip()
    if ":" not in value:
        return float(value)
    parts = value.split(":")
    parts = [float(p) for p in parts]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    hours, minutes, seconds = parts[-3], parts[-2], parts[-1]
    return hours * 3600 + minutes * 60 + seconds


FOCUS_X = {
    "left": "0",
    "center": "(iw-ow)/2",
    "right": "iw-ow",
}


BOTTOM_COLOR = "0x0b1120"  # fondo solido oscuro (lo ocupara ComfyUI mas adelante)


def build_filter(top_ratio: float, focus: str = "center", zoom: float = 1.0, duration: float = 0.0) -> str:
    top_h = int(CANVAS_H * top_ratio)
    top_h -= top_h % 2  # alto par para el codec
    bottom_h = CANVAS_H - top_h

    zoom = max(1.0, float(zoom))
    scaled_w = int(CANVAS_W * zoom)
    scaled_h = int(top_h * zoom)
    x_expr = FOCUS_X.get(focus, FOCUS_X["center"])
    color_dur = f":d={duration:.3f}" if duration > 0 else ""

    return (
        f"[0:v]scale={scaled_w}:{scaled_h}:force_original_aspect_ratio=increase,"
        f"crop={CANVAS_W}:{top_h}:{x_expr}:(ih-oh)/2,setsar=1[toppad];"
        f"color=c={BOTTOM_COLOR}:s={CANVAS_W}x{bottom_h}:r=30{color_dur}[bot];"
        f"[toppad][bot]vstack=inputs=2:shortest=1[v]"
    )


def make_clip(
    video: Path,
    start: float,
    end: float,
    out_path: Path,
    top_ratio: float = 0.5,
    focus: str = "center",
    zoom: float = 1.0,
    ffmpeg: str = "ffmpeg",
) -> Path:
    duration = round(end - start, 3)
    if duration <= 0:
        raise SystemExit("La duracion del clip debe ser mayor que 0 (end > start).")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg, "-y",
        "-ss", f"{start:.3f}",
        "-i", str(video),
        "-t", f"{duration:.3f}",
        "-filter_complex", build_filter(top_ratio, focus, zoom, duration),
        "-map", "[v]",
        "-map", "0:a?",
        "-c:v", "libx264",
        "-crf", "20",
        "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-c:a", "aac",
        "-b:a", "160k",
        str(out_path),
    ]
    print(f"Generando clip vertical [{start:.2f}s -> {end:.2f}s] ({duration:.2f}s)", flush=True)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr[-1500:])
        raise SystemExit(f"ffmpeg fallo al generar el clip (codigo {result.returncode})")

    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"Clip vertical guardado: {out_path} ({size_mb:.1f} MB)", flush=True)
    return out_path


def default_output(video: Path, start: float, end: float) -> Path:
    clips_dir = video.parent / "clips"
    stem = video.stem[:40]
    return clips_dir / f"{stem}_clip_{int(start)}-{int(end)}_vertical.mp4"


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera un clip vertical con pantalla partida")
    parser.add_argument("--video", required=True, help="Ruta al video de origen")
    parser.add_argument("--start", required=True, help="Inicio (segundos o HH:MM:SS)")
    parser.add_argument("--end", required=True, help="Fin (segundos o HH:MM:SS)")
    parser.add_argument("--out", default=None, help="Ruta de salida .mp4 (opcional)")
    parser.add_argument("--top-ratio", type=float, default=0.5, help="Fraccion de alto para el clip superior (0-1)")
    parser.add_argument("--focus", default="center", choices=["left", "center", "right"], help="Encuadre horizontal del clip superior")
    parser.add_argument("--zoom", type=float, default=1.0, help="Zoom del clip superior (1.0 = sin zoom)")
    parser.add_argument("--ffmpeg", default="ffmpeg", help="Ruta a ffmpeg")
    args = parser.parse_args()

    video = Path(args.video)
    if not video.exists():
        raise SystemExit(f"No existe el video: {video}")

    start = parse_timecode(args.start)
    end = parse_timecode(args.end)
    out_path = Path(args.out) if args.out else default_output(video, start, end)

    make_clip(video, start, end, out_path, top_ratio=args.top_ratio, focus=args.focus, zoom=args.zoom, ffmpeg=args.ffmpeg)


if __name__ == "__main__":
    main()
