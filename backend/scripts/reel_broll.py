#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Job del b-roll de un reel. Transcribe el AUDIO (lo que realmente se dice),
lo parte en tramos con tiempos, genera UNA imagen por tramo anclada a ese texto
(ComfyUI) y compone un slideshow SINCRONIZADO (cada imagen dura lo que dura su
tramo) + karaoke + voz. Corre como JOB (sobrevive a recargas del backend).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app import db  # noqa: E402
from app.services import comfy_client  # noqa: E402
from app.services.reel_engine import broll_prompts, broll_prompts_for  # noqa: E402


def _duration(audio: Path) -> float:
    import re
    proc = subprocess.run(["ffmpeg", "-i", str(audio)], capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", proc.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def _segments(words: list[dict], n: int, dur: float) -> list[dict]:
    """Parte las palabras en n grupos contiguos → tramos {text, t0, t1} (segundos)."""
    words = [w for w in words if w.get("text")]
    if not words:
        return []
    n = max(1, min(n, len(words)))
    per = max(1, round(len(words) / n))
    groups = [words[i:i + per] for i in range(0, len(words), per)]
    segs = []
    for g in groups:
        segs.append({"text": " ".join(w["text"] for w in g),
                     "t0": g[0]["start"] / 1000.0, "t1": g[-1]["end"] / 1000.0})
    # Duraciones contiguas: cada imagen dura hasta que empieza la siguiente.
    for i, s in enumerate(segs):
        nxt = segs[i + 1]["t0"] if i + 1 < len(segs) else dur
        s["hold"] = max(0.8, round(nxt - s["t0"], 3))
    return segs


def main() -> None:
    ap = argparse.ArgumentParser(description="Genera el b-roll de un reel y lo compone")
    ap.add_argument("--reel", required=True)
    ap.add_argument("--title", default="")
    ap.add_argument("--lang", default="es")
    ap.add_argument("--no-subtitles", action="store_true")
    args = ap.parse_args()

    root = Path.cwd()
    db.init(root / "backend" / "runs" / "jobs.db")
    reel = db.get_reel(args.reel)
    if not reel:
        raise SystemExit(f"Generación {args.reel} no encontrada.")
    audio = root / reel["audio"]
    if not reel["audio"] or not audio.exists():
        raise SystemExit("La generación no tiene audio.")
    if not comfy_client.is_up():
        raise SystemExit("ComfyUI no responde (¿encendido en el Windows y la GPU libre?).")

    dur = _duration(audio)
    n = max(3, min(10, round(dur / 5)))

    # Transcribe lo que realmente se dice → tramos con tiempos.
    print("Transcribiendo el audio para anclar las imágenes...", flush=True)
    from subtitle_engine import SubtitleEngine  # noqa: E402
    try:
        words = SubtitleEngine().transcribe_words(audio, language_code=args.lang)
    except Exception as exc:  # noqa: BLE001
        print(f"No se pudo transcribir ({exc}); uso el guion.", flush=True)
        words = []

    out = audio.with_name(audio.stem + "_video.mp4")
    segs = _segments(words, n, dur)
    if segs:
        prompts = broll_prompts_for([s["text"] for s in segs])
        durations = [s["hold"] for s in segs]
    else:
        prompts = broll_prompts(reel.get("script") or "", n)
        durations = []

    broll_dir = audio.parent / (audio.stem + "_broll")
    broll_dir.mkdir(parents=True, exist_ok=True)
    images = []
    for i, p in enumerate(prompts):
        print(f"[{i + 1}/{len(prompts)}] {p[:70]}...", flush=True)
        images.append(str(comfy_client.generate_image(p, broll_dir / f"img_{i:02d}.jpg")))

    # Reaprovecha la transcripción para los subtítulos (evita re-transcribir).
    if words and not args.no_subtitles:
        cache_dir = out.parent / f".sub_{out.stem}"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "subtitle_words.json").write_text(json.dumps(words), encoding="utf-8")

    print("Componiendo slideshow sincronizado + karaoke...", flush=True)
    cmd = [sys.executable, str(Path(__file__).with_name("reel_compose.py")),
           "--audio", str(audio), "--out", str(out), "--images", ",".join(images)]
    if durations:
        cmd += ["--durations", ",".join(f"{d:.3f}" for d in durations)]
    if args.title.strip():
        cmd += ["--title", args.title.strip()]
    if not args.no_subtitles:
        cmd.append("--subtitles")
    rc = subprocess.run(cmd, cwd=str(root)).returncode
    if rc != 0 or not out.exists():
        raise SystemExit(f"Fallo componiendo el reel (rc={rc}).")

    db.update_reel(args.reel, {"video_path": str(out.relative_to(root)), "title": args.title})
    print(f"Reel con b-roll listo: {out}", flush=True)


if __name__ == "__main__":
    main()
