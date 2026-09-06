#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JOB: crea un reel EXPLICATIVO a partir del resumen de un partido (enlace de
YouTube). Descarga el vídeo → transcribe → detecta los momentos más relevantes
(como en Clipping) → genera un guion explicativo → voz clonada → recorta un
FOTOGRAMA REAL del partido por cada momento (vertical 1080x1920 con fondo
desenfocado) → compone slideshow sincronizado + karaoke. Sin GPU salvo el TTS.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app import db  # noqa: E402
from app.services.clip_detector import detect_clips  # noqa: E402
from app.services.reel_engine import match_script  # noqa: E402

CANVAS_W, CANVAS_H = 1080, 1920


def _duration(media: Path, ffmpeg: str = "ffmpeg") -> float:
    proc = subprocess.run([ffmpeg, "-i", str(media)], capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", proc.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def _segments(words: list[dict], n: int, dur: float) -> list[dict]:
    """Parte las palabras en n grupos contiguos → tramos {text, t0, t1, hold}."""
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
    for i, s in enumerate(segs):
        nxt = segs[i + 1]["t0"] if i + 1 < len(segs) else dur
        s["hold"] = max(0.8, round(nxt - s["t0"], 3))
    return segs


def _vertical_frame(video: Path, t: float, out: Path, ffmpeg: str = "ffmpeg") -> bool:
    """Extrae el fotograma del instante t y lo lleva a 1080x1920 con la acción
    completa visible (encaje) sobre un fondo del propio fotograma desenfocado."""
    vf = ("split[a][b];"
          f"[a]scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=increase,"
          f"crop={CANVAS_W}:{CANVAS_H},boxblur=40[bg];"
          f"[b]scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=decrease[fg];"
          "[bg][fg]overlay=(W-w)/2:(H-h)/2")
    subprocess.run([ffmpeg, "-y", "-ss", f"{max(0.0, t):.2f}", "-i", str(video),
                    "-frames:v", "1", "-vf", vf, "-q:v", "3", str(out)],
                   capture_output=True, text=True)
    return out.exists()


def main() -> None:
    ap = argparse.ArgumentParser(description="Reel explicativo desde el resumen de un partido")
    ap.add_argument("--reel", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--voice", required=True)
    ap.add_argument("--lang", default="auto")
    ap.add_argument("--moments", type=int, default=6)
    ap.add_argument("--seconds", type=int, default=45)
    ap.add_argument("--ffmpeg", default="ffmpeg")
    args = ap.parse_args()

    root = Path.cwd()
    db.init(root / "backend" / "runs" / "jobs.db")
    reel = db.get_reel(args.reel)
    if not reel:
        raise SystemExit(f"Reel {args.reel} no encontrado.")

    # 1) Descargar el resumen del partido.
    print("1/6 Descargando el resumen del partido...", flush=True)
    from download_video import download_video  # noqa: E402
    # ffmpeg_path=None → yt-dlp usa el ffmpeg del PATH (lo necesita para fusionar
    # vídeo+audio). Pasar "ffmpeg" lo trata como ruta de fichero y falla al mergear.
    res = download_video(args.url, None, outbase="output/reels/matches")
    if not res or not res[0]:
        raise SystemExit("No se pudo descargar el vídeo del partido.")
    match_video = Path(res[0])

    # 2) Transcribir el partido → subtítulos con tiempos.
    print("2/6 Transcribiendo el partido...", flush=True)
    from download_and_transcribe_video import extract_audio_mp3  # noqa: E402
    from app.services.transcription import AssemblyAiTranscriptionService  # noqa: E402
    mp3 = extract_audio_mp3(str(match_video), args.ffmpeg)
    artifacts = AssemblyAiTranscriptionService().transcribe(mp3, lang=args.lang, subtitle_format="vtt")
    subs = Path(artifacts.subtitles_file)

    # 3) Momentos más relevantes (reutiliza la detección del Clipping).
    print("3/6 Detectando los momentos más relevantes...", flush=True)
    cands = detect_clips(subs, parts=None, clips_per_part=max(3, args.moments), target_dur=10)
    if not cands:
        raise SystemExit("No se detectaron momentos relevantes en el partido.")
    top = sorted(cands, key=lambda c: c.score, reverse=True)[:args.moments]
    top = sorted(top, key=lambda c: c.start)  # cronológico para narrar en orden

    # 4) Guion explicativo a partir de esos momentos.
    print("4/6 Generando el guion explicativo...", flush=True)
    script = match_script([(c.transcript or c.title) for c in top], seconds=args.seconds)
    if not script.strip():
        raise SystemExit("No se pudo generar el guion.")
    db.update_reel(args.reel, {"script": script})

    # 5) Voz clonada.
    print("5/6 Generando la voz clonada...", flush=True)
    from app.services import tts_client  # noqa: E402
    audio = root / "output" / "reels" / f"reel_{args.reel}.mp3"
    audio.parent.mkdir(parents=True, exist_ok=True)
    tts_client.synthesize(script, args.voice, audio)
    db.update_reel(args.reel, {"audio_path": str(audio.relative_to(root)), "voice_id": args.voice})

    # 6) Un fotograma real del partido por tramo hablado + composición + karaoke.
    print("6/6 Recortando fotogramas del partido y componiendo...", flush=True)
    from subtitle_engine import SubtitleEngine  # noqa: E402
    words = SubtitleEngine().transcribe_words(audio)
    dur = _duration(audio, args.ffmpeg)
    segs = _segments(words, len(top), dur)

    frames_dir = audio.parent / (audio.stem + "_frames")
    frames_dir.mkdir(parents=True, exist_ok=True)
    images, durations = [], []
    for i, c in enumerate(top):
        mid = (c.start + c.end) / 2.0
        fp = frames_dir / f"f_{i:02d}.jpg"
        if _vertical_frame(match_video, mid, fp, args.ffmpeg):
            images.append(str(fp))
            durations.append(segs[i]["hold"] if i < len(segs) else round(dur / len(top), 3))
    if not images:
        raise SystemExit("No se pudieron extraer fotogramas del partido.")

    out = audio.with_name(audio.stem + "_video.mp4")
    # Caché de subtítulos PROPIA de este reel (evita subtítulos cruzados).
    cache_dir = out.parent / f".sub_{out.stem}"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "subtitle_words.json").write_text(json.dumps(words), encoding="utf-8")

    cmd = [sys.executable, str(Path(__file__).with_name("reel_compose.py")),
           "--audio", str(audio), "--out", str(out),
           "--images", ",".join(images),
           "--durations", ",".join(f"{d:.3f}" for d in durations),
           "--subtitles"]
    rc = subprocess.run(cmd, cwd=str(root)).returncode
    if rc != 0 or not out.exists():
        raise SystemExit(f"Fallo componiendo el reel (rc={rc}).")

    db.update_reel(args.reel, {"video_path": str(out.relative_to(root))})
    print(f"✅ Reel del partido listo: {out}", flush=True)


if __name__ == "__main__":
    main()
