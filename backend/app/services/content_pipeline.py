from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .transcription import AssemblyAiTranscriptionService, TranscriptionArtifacts
from .video_download import VideoDownloadService


@dataclass
class VideoContentRequest:
    url: str
    browser: str | None = None
    cookies_file: str | None = None
    ffmpeg: str | None = None
    lang: str = "auto"
    subtitle_format: str = "vtt"

    def to_cli_args(self) -> list[str]:
        args = [
            "--url",
            self.url,
            "--lang",
            self.lang,
            "--format",
            self.subtitle_format,
        ]
        if self.browser:
            args.extend(["--browser", self.browser])
        if self.cookies_file:
            args.extend(["--cookies", self.cookies_file])
        if self.ffmpeg:
            args.extend(["--ffmpeg", self.ffmpeg])
        return args


@dataclass
class VideoContentArtifacts:
    mp3_file: Path
    transcription: TranscriptionArtifacts


class VideoContentPipeline:
    def __init__(
        self,
        download_service: VideoDownloadService,
        transcription_service: AssemblyAiTranscriptionService,
    ) -> None:
        self.download_service = download_service
        self.transcription_service = transcription_service

    def run(self, request: VideoContentRequest) -> VideoContentArtifacts:
        mp3_file = self.download_service.download_mp3(
            url=request.url,
            ffmpeg_path=request.ffmpeg,
            browser=request.browser,
            cookies_file=request.cookies_file,
        )
        transcription = self.transcription_service.transcribe(
            mp3_path=mp3_file,
            lang=request.lang,
            subtitle_format=request.subtitle_format,
        )
        return VideoContentArtifacts(mp3_file=mp3_file, transcription=transcription)
