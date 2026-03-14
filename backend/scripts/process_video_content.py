#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services.content_pipeline import VideoContentPipeline, VideoContentRequest
from app.services.transcription import AssemblyAiTranscriptionService
from app.services.video_download import VideoDownloadService


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="URL del video origen")
    parser.add_argument("--browser", default=None, help="chrome | firefox | brave | edge")
    parser.add_argument("--cookies", default=None, help="Ruta a cookies.txt exportado")
    parser.add_argument("--ffmpeg", default=None, help="Ruta opcional a ffmpeg")
    parser.add_argument("--lang", default="auto", help="auto | es | en | ...")
    parser.add_argument("--format", default="vtt", choices=["vtt", "srt"])
    args = parser.parse_args()

    request = VideoContentRequest(
        url=args.url,
        browser=args.browser,
        cookies_file=args.cookies,
        ffmpeg=args.ffmpeg,
        lang=args.lang,
        subtitle_format=args.format,
    )

    pipeline = VideoContentPipeline(
        download_service=VideoDownloadService(root_dir=ROOT_DIR),
        transcription_service=AssemblyAiTranscriptionService(),
    )
    artifacts = pipeline.run(request)

    print("")
    print("Pipeline completado")
    print(f"MP3: {artifacts.mp3_file}")
    print(f"TXT: {artifacts.transcription.text_file}")
    print(f"SUBS: {artifacts.transcription.subtitles_file}")
    if artifacts.transcription.language_file:
        print(f"LANG: {artifacts.transcription.language_file}")


if __name__ == "__main__":
    main()
