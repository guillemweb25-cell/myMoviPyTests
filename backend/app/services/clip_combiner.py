"""Combina varios clips relacionados en un solo short con IA.

Recibe la transcripcion y los tramos de los clips elegidos, numera sus cues y le
pide a OpenAI un montaje (gancho -> desarrollo -> cierre) como RANGOS DE CUES, no
como tiempos: asi cada fragmento corta en limites de frase y el modelo no puede
inventarse marcas de tiempo. El montaje se materializa luego con `concat_segments`
(corte seco) y se trata como un clip normal.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .clip_detector import Cue, parse_subtitles

SYSTEM_PROMPT = (
    "Eres un editor experto en clips virales para TikTok, Reels y Shorts. Recibes "
    "fragmentos de la transcripcion de un mismo video (cues numerados con tiempos en "
    "segundos), agrupados por clip. Tu trabajo es montar UN SOLO short combinando "
    "frases de esos clips con cortes secos: un gancho fuerte al principio, desarrollo "
    "y un cierre que remate. Puedes reordenar, pero no cambies el sentido de lo que "
    "dice la persona ni lo saques de contexto. Cada fragmento debe ser una idea "
    "completa que se entienda sola al empalmarla con la anterior."
)


def _user_prompt(groups: list[tuple[int, list[tuple[int, Cue]]]], target_dur: int) -> str:
    blocks = []
    for n, cues in groups:
        lines = [f"[{i}] ({c.end - c.start:.1f}s) {c.text}" for i, c in cues]
        blocks.append(f"### Clip {n}\n" + "\n".join(lines))
    return (
        "\n\n".join(blocks)
        + f"\n\nMonta un short de unos {target_dur} segundos usando cues de estos clips "
        "(entre parentesis, lo que dura cada cue). La SUMA de lo que duran los cues "
        f"elegidos no puede pasar de {target_dur + 15} segundos: no metas todo, quedate "
        "con lo mejor. Usa al menos un fragmento de cada clip.\n"
        "Responde SOLO con JSON con esta forma:\n"
        '{"title": "titulo corto y con gancho", "reason": "por que funciona el montaje", '
        '"fragments": [{"from": indice_cue_inicial, "to": indice_cue_final}]}\n'
        "Los fragmentos van en el orden en que deben sonar. Cada fragmento es un rango "
        "CONTINUO de cues del mismo clip (from <= to)."
    )


def combine_clips(subtitles_path: Path, ranges: list[tuple[float, float]], target_dur: int = 45,
                  model: str | None = None) -> dict:
    """Devuelve {title, reason, segments: [[start, end], ...]} en segundos del video
    fuente, con los fragmentos en el orden del montaje."""
    from openai import OpenAI

    all_cues = parse_subtitles(subtitles_path)
    if not all_cues:
        raise ValueError("No se pudieron leer cues de la transcripcion")

    # Cues de cada clip, con su indice global (el que ve el modelo).
    groups: list[tuple[int, list[tuple[int, Cue]]]] = []
    allowed: dict[int, int] = {}  # indice de cue -> nº de clip
    for n, (start, end) in enumerate(ranges, 1):
        cues = [(i, c) for i, c in enumerate(all_cues) if c.end > start and c.start < end]
        if cues:
            groups.append((n, cues))
            for i, _ in cues:
                allowed.setdefault(i, n)
    if len(groups) < 2:
        raise ValueError("Hacen falta al menos dos clips con transcripcion para combinar")

    client = OpenAI()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": _user_prompt(groups, target_dur)},
    ]
    max_dur = target_dur + 15
    segments: list[list[float]] = []
    payload: dict = {}
    # Si se pasa de duracion, se le dice cuanto ha durado y se le pide una vez que recorte.
    for _ in range(2):
        response = client.chat.completions.create(
            model=model or os.getenv("OPENAI_CLIP_MODEL", "gpt-4o"),
            temperature=0.4,
            response_format={"type": "json_object"},
            messages=messages,
        )
        content = response.choices[0].message.content or "{}"
        payload = json.loads(content)
        segments = _parse_fragments(payload, all_cues, allowed)
        total = sum(e - s for s, e in segments)
        if not segments or total <= max_dur:
            break
        messages += [
            {"role": "assistant", "content": content},
            {"role": "user", "content": (
                f"Ese montaje dura {total:.0f} s y el maximo es {max_dur} s. Quita los "
                f"fragmentos que menos aporten hasta quedarte en unos {target_dur} s, "
                "manteniendo el gancho y el cierre. Mismo formato JSON."
            )},
        ]
    if not segments:
        raise ValueError("La IA no devolvio fragmentos validos")

    return {
        "title": str(payload.get("title") or "").strip(),
        "reason": str(payload.get("reason") or "").strip(),
        "segments": segments,
    }


def _parse_fragments(payload: dict, all_cues: list[Cue], allowed: dict[int, int]) -> list[list[float]]:
    """Pasa los rangos de cues del modelo a [[start, end], ...], descartando los que
    salgan de los clips elegidos o mezclen dos clips en un mismo fragmento."""
    segments: list[list[float]] = []
    for frag in payload.get("fragments", []):
        try:
            a, b = int(frag["from"]), int(frag["to"])
        except (KeyError, TypeError, ValueError):
            continue
        if a > b:
            a, b = b, a
        # Solo cues de los clips elegidos, y el rango entero dentro del mismo clip.
        if a not in allowed or allowed.get(b) != allowed[a]:
            continue
        if not all(allowed.get(i) == allowed[a] for i in range(a, b + 1)):
            continue
        seg = [round(all_cues[a].start, 3), round(all_cues[b].end, 3)]
        if seg[1] - seg[0] >= 0.5:
            segments.append(seg)
    return segments


def segments_text(subtitles_path: Path, segments: list[list[float]]) -> str:
    """Texto de la transcripcion de los fragmentos, en el orden del montaje."""
    cues = parse_subtitles(subtitles_path)
    return " ".join(
        c.text for s, e in segments for c in cues if c.end > s and c.start < e
    )


def concat_segments(video: Path, segments: list[list[float]], out: Path, ffmpeg: str = "ffmpeg") -> float:
    """Une los fragmentos del video con corte seco en `out` y devuelve la duracion.
    Cada fragmento se busca con -ss antes de -i (rapido en videos largos). El audio
    lleva un fundido de 10 ms en cada borde: inaudible, pero evita el chasquido."""
    cmd = [ffmpeg, "-y"]
    for s, e in segments:
        cmd += ["-ss", f"{s:.3f}", "-t", f"{e - s:.3f}", "-i", str(video)]
    filters, labels = [], []
    for i, (s, e) in enumerate(segments):
        d = e - s
        filters.append(f"[{i}:v]setpts=PTS-STARTPTS,format=yuv420p[v{i}]")
        filters.append(
            f"[{i}:a]asetpts=PTS-STARTPTS,aresample=48000,"
            f"afade=t=in:d=0.01,afade=t=out:st={max(0.0, d - 0.01):.3f}:d=0.01[a{i}]"
        )
        labels.append(f"[v{i}][a{i}]")
    filters.append(f"{''.join(labels)}concat=n={len(segments)}:v=1:a=1[v][a]")
    tmp = out.with_name(out.stem + "_tmp.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd += [
        "-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(tmp),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg fallo al unir los fragmentos: {result.stderr[-400:]}")
    tmp.replace(out)
    return round(sum(e - s for s, e in segments), 3)
