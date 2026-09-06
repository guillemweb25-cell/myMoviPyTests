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


_VF_VERTICAL = ("split[a][b];"
                f"[a]scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=increase,"
                f"crop={CANVAS_W}:{CANVAS_H},boxblur=40[bg];"
                f"[b]scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=decrease[fg];"
                "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1")


def _vertical_clip(video: Path, start: float, dur: float, src_dur: float, out: Path,
                   ffmpeg: str = "ffmpeg") -> bool:
    """Extrae un FRAGMENTO [start, start+dur] del vídeo y lo lleva a 1080x1920 vertical
    (acción completa sobre fondo desenfocado), sin audio, a 30 fps. Movimiento real."""
    dur = max(0.6, dur)
    start = max(0.0, min(start, max(0.0, src_dur - dur - 0.05)))
    r = subprocess.run([ffmpeg, "-y", "-ss", f"{start:.2f}", "-t", f"{dur:.3f}", "-i", str(video),
                        "-vf", _VF_VERTICAL + ",fps=30", "-an",
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                        "-pix_fmt", "yuv420p", "-r", "30", str(out)],
                       capture_output=True, text=True)
    return out.exists() and r.returncode == 0


def _build_bgvideo(video: Path, starts: list, holds: list, src_dur: float, out_dir: Path,
                   ffmpeg: str = "ffmpeg") -> "Path | None":
    """Monta el vídeo de fondo: un fragmento vertical por tramo hablado, concatenados.
    Devuelve el mp4 concatenado o None si no se pudo extraer ningún fragmento."""
    out_dir.mkdir(parents=True, exist_ok=True)
    clips = []
    for i, (s, h) in enumerate(zip(starts, holds)):
        cp = out_dir / f"clip_{i:02d}.mp4"
        if _vertical_clip(video, float(s), float(h), src_dur, cp, ffmpeg):
            clips.append(cp)
    if not clips:
        return None
    listfile = out_dir / "bg.concat.txt"
    lines = ["ffconcat version 1.0"] + [f"file '{c.resolve()}'" for c in clips]
    listfile.write_text("\n".join(lines), encoding="utf-8")
    bg = out_dir / "bg.mp4"
    r = subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
                        "-c", "copy", str(bg)], capture_output=True, text=True)
    if r.returncode != 0 or not bg.exists():  # reencodea si el copy falla
        subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
                        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                        "-pix_fmt", "yuv420p", "-r", "30", str(bg)], capture_output=True, text=True)
    return bg if bg.exists() else None


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


def _compose_from_source(reel_id: str, source_video: Path, audio: Path, root: Path,
                         moments: list, ffmpeg: str) -> Path:
    """Monta el reel con FRAGMENTOS de vídeo reales del partido (uno por tramo hablado,
    con movimiento), sincronizados a la voz + karaoke + música. `moments` = instantes
    (s) del vídeo fuente; si va vacío, se reparten uniformemente. Si no se pueden
    extraer fragmentos, cae a fotogramas estáticos."""
    from subtitle_engine import SubtitleEngine  # noqa: E402
    words = SubtitleEngine().transcribe_words(audio)
    dur = _duration(audio, ffmpeg)
    src_dur = _duration(source_video, ffmpeg)
    n = len(moments) if moments else max(4, min(10, round(dur / 6)))
    segs = _segments(words, n, dur)
    if not moments:  # reparte por el vídeo fuente
        moments = [src_dur * (i + 0.5) / n for i in range(n)]
    holds = [segs[i]["hold"] if i < len(segs) else round(dur / n, 3) for i in range(n)]
    # Los fragmentos empiezan un poco antes del instante clave para "entrar" a la jugada.
    starts = [max(0.0, float(moments[i]) - min(1.0, holds[i] * 0.3)) for i in range(n)]

    out = audio.with_name(audio.stem + "_video.mp4")
    cache_dir = out.parent / f".sub_{out.stem}"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "subtitle_words.json").write_text(json.dumps(words), encoding="utf-8")

    cmd = [sys.executable, str(Path(__file__).with_name("reel_compose.py")),
           "--audio", str(audio), "--out", str(out), "--subtitles"]

    print("Extrayendo fragmentos de vídeo del partido...", flush=True)
    bg = _build_bgvideo(source_video, starts, holds, src_dur, audio.parent / (audio.stem + "_frag"), ffmpeg)
    if bg:
        cmd += ["--bg-video", str(bg)]
    else:  # fallback: fotogramas estáticos
        print("No se pudieron extraer fragmentos; uso fotogramas estáticos.", flush=True)
        frames_dir = audio.parent / (audio.stem + "_frames")
        frames_dir.mkdir(parents=True, exist_ok=True)
        images, durations = [], []
        for i, t in enumerate(moments):
            fp = frames_dir / f"f_{i:02d}.jpg"
            if _vertical_frame(source_video, float(t), fp, ffmpeg):
                images.append(str(fp)); durations.append(holds[i])
        if not images:
            raise SystemExit("No se pudieron extraer imágenes del vídeo del partido.")
        cmd += ["--images", ",".join(images), "--durations", ",".join(f"{d:.3f}" for d in durations)]

    print("Componiendo (voz + karaoke + música)...", flush=True)
    rc = subprocess.run(cmd, cwd=str(root)).returncode
    if rc != 0 or not out.exists():
        raise SystemExit(f"Fallo componiendo el reel (rc={rc}).")
    db.update_reel(reel_id, {"video_path": str(out.relative_to(root))})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Reel explicativo desde el resumen de un partido")
    ap.add_argument("--reel", required=True)
    ap.add_argument("--url", default="")
    ap.add_argument("--voice", default="")
    ap.add_argument("--lang", default="auto")
    ap.add_argument("--moments", type=int, default=6)
    ap.add_argument("--seconds", type=int, default=45)
    ap.add_argument("--render-only", action="store_true",
                    help="reusa guion+voz+vídeo fuente ya existentes; solo re-monta el vídeo")
    ap.add_argument("--ffmpeg", default="ffmpeg")
    args = ap.parse_args()

    root = Path.cwd()
    db.init(root / "backend" / "runs" / "jobs.db")
    reel = db.get_reel(args.reel)
    if not reel:
        raise SystemExit(f"Reel {args.reel} no encontrado.")

    # RENDER-ONLY: ya hay voz y vídeo fuente → solo re-monta (fotogramas + composición).
    if args.render_only:
        audio = root / (reel.get("audio") or "")
        source = root / (reel.get("sourceVideo") or "")
        if not reel.get("audio") or not audio.exists():
            raise SystemExit("El reel no tiene voz generada.")
        if not reel.get("sourceVideo") or not source.exists():
            raise SystemExit("No hay vídeo del partido guardado; usa 'Crear reel del partido'.")
        print("Re-montando el reel con los fotogramas del partido...", flush=True)
        out = _compose_from_source(args.reel, source, audio, root, [], args.ffmpeg)
        print(f"✅ Reel re-montado: {out}", flush=True)
        return

    if not args.url or not args.voice:
        raise SystemExit("Faltan --url y --voice para crear el reel del partido.")

    # 1) Descargar el resumen del partido.
    print("1/6 Descargando el resumen del partido...", flush=True)
    from download_video import download_video  # noqa: E402
    # ffmpeg_path=None → yt-dlp usa el ffmpeg del PATH (lo necesita para fusionar
    # vídeo+audio). Pasar "ffmpeg" lo trata como ruta de fichero y falla al mergear.
    res = download_video(args.url, None, outbase="output/reels/matches")
    if not res or not res[0]:
        raise SystemExit("No se pudo descargar el vídeo del partido.")
    match_video = Path(res[0])
    try:
        db.update_reel(args.reel, {"source_video": str(match_video.relative_to(root))})
    except ValueError:
        pass  # fuera del root: no lo guardamos, seguimos igual

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

    # 6) Un fotograma real del partido por momento clave + composición + karaoke.
    print("6/6 Recortando fotogramas del partido y componiendo...", flush=True)
    moments = [(c.start + c.end) / 2.0 for c in top]
    out = _compose_from_source(args.reel, match_video, audio, root, moments, args.ffmpeg)
    print(f"✅ Reel del partido listo: {out}", flush=True)


if __name__ == "__main__":
    main()
