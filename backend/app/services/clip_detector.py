"""Deteccion de clips "virales" a partir de una transcripcion con timestamps.

Lee un fichero .vtt/.srt, construye una transcripcion indexada con tiempos y le
pide a un modelo de OpenAI que seleccione los mejores momentos para clips
verticales (gancho, motivo y una puntuacion). Devuelve candidatos con inicio y
fin en segundos, listos para el render vertical.
"""
from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Cue:
    start: float
    end: float
    text: str


@dataclass
class ClipCandidate:
    start: float
    end: float
    title: str
    reason: str
    score: int
    transcript: str = ""

    def to_dict(self) -> dict:
        return {
            "start": round(self.start, 2),
            "end": round(self.end, 2),
            "duration": round(self.end - self.start, 2),
            "title": self.title,
            "reason": self.reason,
            "score": self.score,
            "transcript": self.transcript,
        }


_TIME_RE = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})")


def _parse_timecode(value: str) -> float:
    match = _TIME_RE.search(value)
    if not match:
        return 0.0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2))
    seconds = int(match.group(3))
    millis = int(match.group(4).ljust(3, "0"))
    return hours * 3600 + minutes * 60 + seconds + millis / 1000


def parse_subtitles(path: Path) -> list[Cue]:
    """Parsea un .vtt o .srt en una lista de cues con tiempos en segundos."""
    raw = path.read_text(encoding="utf-8", errors="ignore")
    cues: list[Cue] = []
    blocks = re.split(r"\n\s*\n", raw)
    for block in blocks:
        lines = [line for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        time_line = next((line for line in lines if "-->" in line), None)
        if not time_line:
            continue
        left, _, right = time_line.partition("-->")
        start = _parse_timecode(left)
        end = _parse_timecode(right)
        text_lines = [line for line in lines if "-->" not in line and not line.strip().isdigit()]
        text = " ".join(text_lines).strip()
        if text and end > start:
            cues.append(Cue(start=start, end=end, text=text))
    return cues


def _build_transcript_block(cues: list[Cue]) -> str:
    lines = []
    for index, cue in enumerate(cues):
        lines.append(f"[{index}] {cue.start:.1f}-{cue.end:.1f}s: {cue.text}")
    return "\n".join(lines)


SYSTEM_PROMPT = (
    "Eres un editor experto en clips virales para TikTok, Reels y Shorts. "
    "Recibes la transcripcion de un video con marcas de tiempo (en segundos) y "
    "debes seleccionar los momentos con mayor potencial viral: ganchos, "
    "revelaciones, giros, frases impactantes o emocionales, o segmentos "
    "autoconclusivos. Cada clip debe empezar y terminar en pausas naturales. "
    "Construye cada clip como un ARCO COMPLETO (preambulo/contexto -> desarrollo -> "
    "desenlace), no solo la frase punchline: incluye el contexto previo y el cierre "
    "para que dure lo pedido y se entienda solo."
)


def _user_prompt(transcript_block: str, count: int, target_dur: int, min_dur: int, max_dur: int) -> str:
    return (
        f"Este es UN SEGMENTO de la transcripcion (indice, tiempo en segundos, texto):\n\n{transcript_block}\n\n"
        f"Selecciona hasta {count} clips con potencial viral de ESTE segmento. Reglas:\n"
        f"- DURACION (IMPORTANTE): cada clip DEBE durar entre {min_dur} y {max_dur} segundos, "
        f"idealmente ~{target_dur}s. Si el momento potente es corto, EXTIENDE los limites "
        f"(hacia atras para incluir el planteamiento y hacia delante para incluir la reaccion/"
        f"desenlace) hasta alcanzar ~{target_dur}s. NO devuelvas clips mas cortos de {min_dur}s.\n"
        "- 'start' y 'end' en segundos (numeros), alineados a los tiempos de los cues del segmento.\n"
        "- Cada clip debe ser autoconclusivo y engancharse desde el primer segundo.\n"
        "- Ordena de mayor a menor potencial.\n\n"
        "Responde SOLO con JSON valido de esta forma:\n"
        '{"clips": [{"start": number, "end": number, "title": "gancho corto", '
        '"reason": "por que funciona", "score": number_0_100}]}'
    )


def _extend_to_target(s: float, e: float, cues: list[Cue], target: int, max_dur: int, total_end: float) -> tuple[float, float]:
    """Si el clip es mas corto que `target`, extiende los limites encajando a inicios/
    finales de cue (primero hacia delante, luego hacia atras), sin pasar de `max_dur`
    ni salirse del video. Asi se respeta la duracion pedida aunque el LLM acorte."""
    if e - s >= target:
        return s, e
    # Hacia delante: alarga el final al siguiente fin de cue mientras quepa.
    for cue in cues:
        if cue.end > e and (cue.end - s) <= max_dur and cue.end <= total_end + 0.01:
            e = cue.end
            if e - s >= target:
                return s, e
    # Si sigue corto, hacia atras: adelanta el inicio a un comienzo de cue anterior.
    for cue in reversed(cues):
        if cue.start < s and (e - cue.start) <= max_dur:
            s = cue.start
            if e - s >= target:
                break
    return max(0.0, s), e


def _text_between(cues: list[Cue], start: float, end: float) -> str:
    parts = [cue.text for cue in cues if cue.start >= start - 0.5 and cue.end <= end + 0.5]
    return " ".join(parts).strip()


def _resolve_parts(cues: list[Cue], parts: int | None) -> int:
    """Si parts es None/0, calcula ~1 parte por cada 15 min de video."""
    if parts and parts > 0:
        return parts
    total_min = (cues[-1].end / 60) if cues else 0
    return max(1, round(total_min / 15))


def detect_clips(
    subtitles_path: Path,
    parts: int | None = 4,
    clips_per_part: int = 5,
    target_dur: int = 40,
    model: str | None = None,
) -> list[ClipCandidate]:
    from openai import OpenAI

    cues = parse_subtitles(subtitles_path)
    if not cues:
        raise ValueError("No se pudieron leer cues de la transcripcion")

    model = model or os.getenv("OPENAI_CLIP_MODEL", "gpt-4o")
    client = OpenAI()
    total_end = cues[-1].end
    min_dur = max(5, target_dur - 10)
    max_dur = target_dur + 15

    n_parts = _resolve_parts(cues, parts)
    chunk_size = math.ceil(len(cues) / n_parts)
    candidates: list[ClipCandidate] = []

    for start_idx in range(0, len(cues), chunk_size):
        chunk = cues[start_idx:start_idx + chunk_size]
        if not chunk:
            continue
        block = _build_transcript_block(chunk)
        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0.4,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": _user_prompt(block, clips_per_part, target_dur, min_dur, max_dur)},
                ],
            )
            payload = json.loads(response.choices[0].message.content or "{}")
        except Exception:  # noqa: BLE001
            continue  # una parte que falle no tumba el resto

        for item in payload.get("clips", []):
            try:
                clip_start = max(0.0, float(item["start"]))
                clip_end = min(total_end, float(item["end"]))
            except (KeyError, TypeError, ValueError):
                continue
            if clip_end - clip_start < 3:
                continue
            # Respeta la duracion pedida: si el LLM acorto, extiende hasta ~target.
            if clip_end - clip_start < min_dur:
                clip_start, clip_end = _extend_to_target(clip_start, clip_end, cues, target_dur, max_dur, total_end)
            candidates.append(
                ClipCandidate(
                    start=clip_start,
                    end=clip_end,
                    title=str(item.get("title", "")).strip()[:120],
                    reason=str(item.get("reason", "")).strip()[:300],
                    score=int(item.get("score", 0)) if str(item.get("score", "")).strip().isdigit() else 0,
                    transcript=_text_between(cues, clip_start, clip_end)[:600],
                )
            )

    candidates.sort(key=lambda clip: (clip.start))  # orden cronologico por defecto
    return candidates
