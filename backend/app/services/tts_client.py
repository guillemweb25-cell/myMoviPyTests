"""Cliente del TTS local (XTTSv2) para clonar la voz — reutiliza la lógica de
troceo/crossfade del proyecto videos_automaticos (afinada para que XTTS-v2 no
meta artefactos: fragmentos <=210 chars, se fusionan los muy cortos, y se
concatenan con un crossfade de 35 ms que enmascara el ruido de fin de clip).

El servidor XTTS es nativo en el Windows (LOCAL_TTS_URL, por defecto :8022):
POST /generate (Form: text, language, voice_id) -> WAV. GET /voices -> lista.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import requests


def _tts_url() -> str:
    return (os.environ.get("LOCAL_TTS_URL") or "http://192.168.1.46:8022").rstrip("/")


def list_voices() -> list[str]:
    try:
        r = requests.get(f"{_tts_url()}/voices", timeout=8)
        r.raise_for_status()
        return sorted(r.json().get("voices", []))
    except Exception:
        return []


def detect_language(text: str) -> str:
    """Código ISO de 2 letras que espera XTTS (es/en/...), por bloque unicode +
    heurística es/en (latino). Cae a 'es'."""
    if not text:
        return "es"
    sample = text[:2000]
    counts = {"ko": 0, "ja": 0, "han": 0, "ru": 0, "ar": 0, "latin": 0}
    for c in sample:
        cp = ord(c)
        if 0xAC00 <= cp <= 0xD7AF:
            counts["ko"] += 1
        elif 0x3040 <= cp <= 0x309F or 0x30A0 <= cp <= 0x30FF:
            counts["ja"] += 1
        elif 0x4E00 <= cp <= 0x9FFF:
            counts["han"] += 1
        elif 0x0400 <= cp <= 0x04FF:
            counts["ru"] += 1
        elif 0x0600 <= cp <= 0x06FF:
            counts["ar"] += 1
        elif c.isalpha():
            counts["latin"] += 1
    total = sum(counts.values()) or 1
    if counts["ko"] / total > 0.03:
        return "ko"
    if counts["ja"] / total > 0.03:
        return "ja"
    if counts["han"] / total > 0.05:
        return "zh-cn"
    if counts["ru"] / total > 0.10:
        return "ru"
    if counts["ar"] / total > 0.10:
        return "ar"
    # es/en por stopwords/diacríticos
    low = " " + sample.lower() + " "
    es_marks = sum(low.count(ch) for ch in "áéíóúñ¿¡")
    es_w = sum(low.count(f" {w} ") for w in ("que", "de", "la", "el", "los", "con", "para", "una", "es", "y", "en"))
    en_w = sum(low.count(f" {w} ") for w in ("the", "and", "of", "to", "is", "that", "this", "for", "with", "you"))
    return "es" if (es_marks > 0 or es_w >= en_w) else "en"


def _split_text(s: str, limit: int = 210) -> list[str]:
    """Trocea por frases (<=limit chars); parte frases largas por comas/espacios;
    y FUSIONA fragmentos cortos (<60) en el vecino (evita el artefacto de voz
    'de tumba' de XTTS con fragmentos diminutos)."""
    parts: list[str] = []
    sentences = re.split(r"(?<=[.!?])\s+", s.strip())
    current = ""
    for sentence in sentences:
        if not sentence.strip():
            continue
        if len(current) + len(sentence) <= limit:
            current += sentence + " "
        else:
            if current:
                parts.append(current.strip())
            if len(sentence) > limit:
                for sub in re.split(r"(?<=[,;:…])\s+", sentence):
                    if len(sub) > limit:
                        w_curr = ""
                        for w in sub.split():
                            if len(w_curr) + len(w) <= limit:
                                w_curr += w + " "
                            else:
                                if w_curr:
                                    parts.append(w_curr.strip())
                                w_curr = w + " "
                        if w_curr:
                            parts.append(w_curr.strip())
                    else:
                        parts.append(sub.strip())
                current = ""
            else:
                current = sentence + " "
    if current:
        parts.append(current.strip())

    MIN_LEN = 60
    if len(parts) > 1:
        merged: list[str] = []
        for p in parts:
            if merged and (len(p) < MIN_LEN or len(merged[-1]) < MIN_LEN) \
                    and len(merged[-1]) + 1 + len(p) <= limit + 120:
                merged[-1] = f"{merged[-1]} {p}"
            else:
                merged.append(p)
        parts = merged
    return [p for p in parts if p.strip()]


def _concat(paths: list[Path], out_path: Path) -> None:
    from pydub import AudioSegment

    segs = [AudioSegment.from_file(p) for p in paths]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not segs:
        AudioSegment.silent(duration=100).export(out_path, format="mp3")
        return
    final = segs[0]
    for seg in segs[1:]:
        cf = min(35, len(final), len(seg))
        final = final.append(seg, crossfade=cf)
    final.export(out_path, format="mp3")


def synthesize(text: str, voice_id: str, out_path: Path, language: str | None = None) -> Path:
    """Genera la voz clonada de `text` con la voz `voice_id` y la escribe en
    `out_path` (mp3). Lanza si el servidor TTS no responde o falla algún trozo."""
    if not text.strip():
        raise ValueError("Texto vacío para TTS")
    language = language or detect_language(text)
    url = f"{_tts_url()}/generate"
    parts = _split_text(text, 210)
    tmp_dir = out_path.parent / "__tts_tmp__"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    chunk_paths: list[Path] = []
    try:
        for i, part in enumerate(parts):
            print(f"XTTS chunk {i + 1}/{len(parts)} ({len(part)} chars, lang={language})...", flush=True)
            r = requests.post(url, data={"text": part, "language": language, "voice_id": voice_id}, timeout=180)
            if not r.ok:
                raise RuntimeError(f"TTS {r.status_code}: {r.text[:200]}")
            cp = tmp_dir / f"{out_path.stem}_{i:03d}.wav"
            cp.write_bytes(r.content)
            chunk_paths.append(cp)
        _concat(chunk_paths, out_path)
        return out_path
    finally:
        for p in chunk_paths:
            p.unlink(missing_ok=True)
        try:
            tmp_dir.rmdir()
        except OSError:
            pass
