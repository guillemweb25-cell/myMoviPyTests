from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import assemblyai as aai
from decouple import config


@dataclass
class TranscriptionArtifacts:
    text_file: Path
    subtitles_file: Path
    language_file: Path | None
    detected_language: str | None


def export_subtitles(transcript: object, subtitle_format: str) -> str:
    subtitle_format = subtitle_format.lower()

    if subtitle_format == "vtt" and hasattr(transcript, "export_subtitles_vtt"):
        return transcript.export_subtitles_vtt()
    if subtitle_format == "srt" and hasattr(transcript, "export_subtitles_srt"):
        return transcript.export_subtitles_srt()

    if hasattr(transcript, "export_subtitles"):
        if subtitle_format == "vtt":
            return transcript.export_subtitles(subtitle_format=aai.SubtitleFormat.VTT)
        return transcript.export_subtitles(subtitle_format=aai.SubtitleFormat.SRT)

    raise SystemExit(
        "Tu version de assemblyai no soporta exportar subtitulos con los metodos esperados."
    )


class AssemblyAiTranscriptionService:
    def __init__(self) -> None:
        api_key = config("AAI_API_KEY", default=None)
        if not api_key:
            raise SystemExit("Falta AAI_API_KEY en el .env")
        aai.settings.api_key = api_key

    def transcribe(
        self,
        mp3_path: Path,
        lang: str = "auto",
        subtitle_format: str = "vtt",
    ) -> TranscriptionArtifacts:
        mp3_path = mp3_path.resolve()
        if not mp3_path.exists():
            raise SystemExit(f"No existe el fichero de audio: {mp3_path}")

        if lang.lower() == "auto":
            cfg = aai.TranscriptionConfig(language_detection=True, speech_model="best")
        else:
            cfg = aai.TranscriptionConfig(language_code=lang, speech_model="best")

        transcriber = aai.Transcriber()

        print(f"Transcribiendo: {mp3_path.name}")
        tx = transcriber.transcribe(str(mp3_path), config=cfg)

        if tx.status == aai.TranscriptStatus.error:
            raise SystemExit(f"Error de transcripcion: {tx.error}")

        base = mp3_path.with_suffix("")
        text_file = base.with_suffix(".txt")
        subtitles_file = base.with_suffix(".vtt" if subtitle_format == "vtt" else ".srt")

        text_file.write_text(tx.text or "", encoding="utf-8")
        print(f"Texto guardado en: {text_file}")

        transcript = aai.Transcript.get_by_id(tx.id)
        subtitles = export_subtitles(transcript, subtitle_format)
        subtitles_file.write_text(subtitles or "", encoding="utf-8")
        print(f"Subtitulos guardados en: {subtitles_file}")

        detected_language = getattr(tx, "language_code", None)
        language_file: Path | None = None
        if detected_language:
            language_file = base.with_suffix(".lang")
            language_file.write_text(detected_language, encoding="utf-8")
            print(f"Idioma detectado: {detected_language}")

        return TranscriptionArtifacts(
            text_file=text_file,
            subtitles_file=subtitles_file,
            language_file=language_file,
            detected_language=detected_language,
        )
