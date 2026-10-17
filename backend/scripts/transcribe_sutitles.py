#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Transcribe un MP3 con AssemblyAI y deja junto a el .txt, .vtt/.srt, .lang y
.json (tramos + tiempos por palabra). Usa el servicio comun de transcripcion."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.transcription import AssemblyAiTranscriptionService  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True, help="Ruta al MP3")
    p.add_argument("--lang", default="auto", help="auto | es | en | ...")
    p.add_argument("--format", default="vtt", choices=["vtt", "srt"])
    args = p.parse_args()

    AssemblyAiTranscriptionService().transcribe(
        Path(args.file), lang=args.lang, subtitle_format=args.format
    )


if __name__ == "__main__":
    main()
