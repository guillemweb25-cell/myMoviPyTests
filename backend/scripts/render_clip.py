#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Renderiza un clip vertical completo: corte + pantalla partida + (opcional)
subtitulos karaoke incrustados.

Encadena make_vertical_clip (composicion vertical) y subtitle_engine
(transcripcion por palabra -> ASS karaoke -> quemado con ffmpeg).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from make_vertical_clip import CANVAS_H, CANVAS_W, default_output, make_clip, parse_timecode
from subtitle_engine import SubtitleEngine


def extract_audio(video_path: Path, ffmpeg: str = "ffmpeg") -> Path:
    audio_path = video_path.with_suffix(".clip_audio.wav")
    cmd = [ffmpeg, "-y", "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000", str(audio_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr[-800:])
        raise SystemExit("No se pudo extraer el audio del clip para subtitular.")
    return audio_path


def add_subtitles(vertical_path: Path, ffmpeg: str = "ffmpeg") -> Path:
    engine = SubtitleEngine()
    audio_path = extract_audio(vertical_path, ffmpeg)
    try:
        words = engine.transcribe_words(audio_path)
    finally:
        audio_path.unlink(missing_ok=True)

    if not words:
        print("Sin palabras en la transcripcion; se omiten subtitulos.", flush=True)
        return vertical_path

    ass_path = vertical_path.with_suffix(".karaoke.ass")
    engine.generate_ass(words, (CANVAS_W, CANVAS_H), ass_path)
    subtitled_path = vertical_path.with_name(f"{vertical_path.stem}_sub.mp4")
    engine.burn_subtitles(vertical_path, ass_path, subtitled_path)
    ass_path.unlink(missing_ok=True)
    vertical_path.unlink(missing_ok=True)
    return subtitled_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Render de clip vertical con subtitulos opcionales")
    parser.add_argument("--video", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--out", default=None)
    parser.add_argument("--top-ratio", type=float, default=0.5)
    parser.add_argument("--subtitles", action="store_true", help="Quemar subtitulos karaoke")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args()

    video = Path(args.video)
    if not video.exists():
        raise SystemExit(f"No existe el video: {video}")

    start = parse_timecode(args.start)
    end = parse_timecode(args.end)
    out_path = Path(args.out) if args.out else default_output(video, start, end)

    vertical = make_clip(video, start, end, out_path, top_ratio=args.top_ratio, ffmpeg=args.ffmpeg)

    if args.subtitles:
        print("Anadiendo subtitulos karaoke...", flush=True)
        final = add_subtitles(vertical, ffmpeg=args.ffmpeg)
        print(f"Clip final con subtitulos: {final}", flush=True)
    else:
        print(f"Clip final: {vertical}", flush=True)


if __name__ == "__main__":
    main()
