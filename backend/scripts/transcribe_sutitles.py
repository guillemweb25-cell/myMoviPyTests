#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
from pathlib import Path
from decouple import config
import assemblyai as aai


def export_subtitles(transcript, fmt: str) -> str:
    fmt = fmt.lower()

    # API típica en 0.50.0
    if fmt == "vtt" and hasattr(transcript, "export_subtitles_vtt"):
        return transcript.export_subtitles_vtt()
    if fmt == "srt" and hasattr(transcript, "export_subtitles_srt"):
        return transcript.export_subtitles_srt()

    # Fallback si en tu versión existe export_subtitles(...) con enum
    if hasattr(transcript, "export_subtitles"):
        if fmt == "vtt":
            return transcript.export_subtitles(subtitle_format=aai.SubtitleFormat.VTT)
        return transcript.export_subtitles(subtitle_format=aai.SubtitleFormat.SRT)

    raise SystemExit(
        "❌ Tu versión de assemblyai no soporta exportar subtítulos con los métodos esperados. "
        "Prueba: pip install -U assemblyai"
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True, help="Ruta al MP3")
    p.add_argument("--lang", default="auto", help="auto | es | en | ...")
    p.add_argument("--format", default="vtt", choices=["vtt", "srt"])
    args = p.parse_args()

    mp3_path = Path(args.file).resolve()
    if not mp3_path.exists():
        raise SystemExit(f"❌ No existe: {mp3_path}")

    api_key = config("AAI_API_KEY", default=None)
    if not api_key:
        raise SystemExit("❌ Falta AAI_API_KEY en el .env")

    aai.settings.api_key = api_key

    if args.lang.lower() == "auto":
        cfg = aai.TranscriptionConfig(language_detection=True, speech_model="best")
    else:
        cfg = aai.TranscriptionConfig(language_code=args.lang, speech_model="best")

    transcriber = aai.Transcriber()

    print(f"📤 Transcribiendo: {mp3_path.name}")
    tx = transcriber.transcribe(str(mp3_path), config=cfg)

    if tx.status == aai.TranscriptStatus.error:
        raise SystemExit(f"❌ Error: {tx.error}")

    base = mp3_path.with_suffix("")  # mismo nombre base

    # Texto plano
    txt_file = base.with_suffix(".txt")
    txt_file.write_text(tx.text or "", encoding="utf-8")
    print(f"✅ Texto: {txt_file.name}")

    # Subtítulos
    transcript = aai.Transcript.get_by_id(tx.id)
    subs = export_subtitles(transcript, args.format)

    subs_file = base.with_suffix(".vtt" if args.format == "vtt" else ".srt")
    subs_file.write_text(subs or "", encoding="utf-8")
    print(f"✅ Subtítulos: {subs_file.name}")

    # Idioma detectado/forzado (si está disponible)
    detected = getattr(tx, "language_code", None)
    if detected:
        lang_file = base.with_suffix(".lang")
        lang_file.write_text(detected, encoding="utf-8")
        print(f"ℹ️ Idioma: {detected} ({lang_file.name})")


if __name__ == "__main__":
    main()
