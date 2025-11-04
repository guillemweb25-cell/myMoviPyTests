#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
from pathlib import Path
from decouple import config
import assemblyai as aai

def transcribe_file(mp3_path: str, lang: str):
    mp3_path = Path(mp3_path).resolve()
    if not mp3_path.exists():
        raise SystemExit(f"❌ El fitxer no existeix: {mp3_path}")

    out_dir = mp3_path.parent
    out_txt = out_dir / "transcription.txt"

    api_key = config("AAI_API_KEY", default=None)
    if not api_key:
        raise SystemExit("❌ No hi ha AAI_API_KEY al .env")

    aai.settings.api_key = api_key

    # Configuració d'idioma: 'auto' activa detecció; si no, força el codi ISO (ex: 'es' o 'es-ES')
    if lang.lower() == "auto":
        cfg = aai.TranscriptionConfig(language_detection=True, speech_model="best")  # universal-2
    else:
        cfg = aai.TranscriptionConfig(language_code=lang, speech_model="best")

    transcriber = aai.Transcriber()

    print(f"📤 Transcrivint: {mp3_path.name}  |  idioma={'detecció' if lang=='auto' else lang}")
    tx = transcriber.transcribe(str(mp3_path), config=cfg)

    if tx.status == aai.TranscriptStatus.error:
        raise SystemExit(f"❌ Error a la transcripció: {tx.error}")

    out_txt.write_text(tx.text or "", encoding="utf-8")
    # Guarda també l’idioma detectat/forçat si està disponible
    detected = getattr(tx, "language_code", None)
    if detected:
        (out_dir / "transcription.lang").write_text(detected, encoding="utf-8")

    print(f"✅ Transcripció guardada: {out_txt}")
    if detected:
        print(f"ℹ️ Idioma: {detected}")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True, help="Ruta local al MP3")
    p.add_argument("--lang", default="auto", help="Codi d'idioma, p. ex. es, es-ES, en. Usa 'auto' per detecció")
    a = p.parse_args()
    transcribe_file(a.file, a.lang)
