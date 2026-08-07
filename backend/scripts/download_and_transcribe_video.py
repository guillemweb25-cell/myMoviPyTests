#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Descarga un video desde una URL y lo transcribe, dejando el .mp4 y su .vtt en
la misma carpeta de output para poder generar clips directamente.

Reutiliza download_video (con fallback KVS + impersonation) y el servicio de
transcripcion AssemblyAI del proyecto.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Permite importar app.services (backend/) ademas de los scripts hermanos.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from download_video import download_video  # noqa: E402  (script hermano)
from app.services.transcription import AssemblyAiTranscriptionService  # noqa: E402


def extract_audio_mp3(video_path: str, ffmpeg: str = "ffmpeg") -> Path:
    video = Path(video_path)
    mp3 = video.with_suffix(".mp3")
    subprocess.run(
        [ffmpeg, "-y", "-i", str(video), "-vn", "-acodec", "libmp3lame", "-b:a", "192k", str(mp3)],
        check=True,
    )
    return mp3


def main() -> None:
    parser = argparse.ArgumentParser(description="Descarga y transcribe un video para clipping")
    parser.add_argument("--url", required=True)
    parser.add_argument("--browser", default=None)
    parser.add_argument("--cookies", default=None)
    parser.add_argument("--ffmpeg", default=None)
    parser.add_argument("--lang", default="auto")
    parser.add_argument("--format", default="vtt")
    args = parser.parse_args()

    print("Paso 1/2: descargando video...", flush=True)
    result = download_video(args.url, args.ffmpeg, args.browser, args.cookies)
    if not result or not result[0]:
        raise SystemExit("No se pudo determinar el video descargado.")
    video_path, out_dir = result
    print(f"Video descargado: {video_path}", flush=True)

    print("Paso 2/2: extrayendo audio y transcribiendo...", flush=True)
    mp3 = extract_audio_mp3(video_path, args.ffmpeg or "ffmpeg")
    service = AssemblyAiTranscriptionService()
    artifacts = service.transcribe(mp3, lang=args.lang, subtitle_format=args.format)
    print(f"Transcripcion generada: {artifacts.subtitles_file}", flush=True)
    print(f"✅ Video listo para clipping en: {out_dir}", flush=True)


if __name__ == "__main__":
    main()
