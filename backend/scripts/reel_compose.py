#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compone un reel vertical 1080x1920 a partir del AUDIO (voz clonada):
fondo + subtítulos karaoke (del propio audio, AssemblyAI) + título opcional.

Sin GPU: todo es ffmpeg (CPU) + AssemblyAI (nube). El hueco del avatar (abajo) y
el b-roll generado llegan en fases siguientes; por ahora el fondo es un color/
imagen y las subtítulos mandan visualmente.
"""
from __future__ import annotations

import argparse
import random
import re
import subprocess
import sys
from pathlib import Path

CANVAS_W, CANVAS_H = 1080, 1920
MUSIC_DIR = Path(__file__).resolve().parents[1] / "assets" / "music"


def pick_music(explicit: str = "") -> Path | None:
    """Devuelve una pista de música de fondo: la indicada o una aleatoria del banco
    (backend/assets/music). None si no hay ninguna."""
    if explicit:
        p = Path(explicit)
        return p if p.exists() else None
    if MUSIC_DIR.exists():
        tracks = sorted(MUSIC_DIR.glob("*.mp3"))
        if tracks:
            return random.choice(tracks)
    return None


def add_background_music(video: Path, music: Path, dur: float, ffmpeg: str,
                         volume: float = 0.10) -> None:
    """Mezcla `music` (en bucle, a bajo volumen y con fade-out) por debajo del audio
    del vídeo. Re-encoda solo el audio (el vídeo se copia). Si algo falla, deja el
    vídeo tal cual (la música es opcional)."""
    tmp = video.with_name(video.stem + "_bgm.mp4")
    fade = max(0.0, dur - 2.0)
    fc = (f"[1:a]volume={volume},afade=t=out:st={fade:.2f}:d=2,"
          f"aformat=sample_rates=44100:channel_layouts=stereo[m];"
          f"[0:a][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]")
    cmd = [ffmpeg, "-y", "-i", str(video), "-stream_loop", "-1", "-i", str(music),
           "-filter_complex", fc, "-map", "0:v", "-map", "[a]",
           "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", str(tmp)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode == 0 and tmp.exists():
        tmp.replace(video)
    else:
        sys.stderr.write(r.stderr[-800:])
        tmp.unlink(missing_ok=True)
        print("No se pudo añadir la música de fondo; se deja el reel sin ella.", flush=True)


def audio_duration(audio: Path, ffmpeg: str = "ffmpeg") -> float:
    proc = subprocess.run([ffmpeg, "-i", str(audio)], capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", proc.stderr)
    if not m:
        return 0.0
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


def build_base(audio: Path, out: Path, dur: float, background: Path | None,
               title: str, ffmpeg: str) -> None:
    """Vídeo base: fondo (imagen/color) a tamaño canvas + audio, con título opcional."""
    if background and background.exists():
        bg_in = ["-loop", "1", "-i", str(background)]
        vf = (f"scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=increase,"
              f"crop={CANVAS_W}:{CANVAS_H}")
    else:
        bg_in = ["-f", "lavfi", "-i", f"color=c=0x0b1120:s={CANVAS_W}x{CANVAS_H}"]
        vf = "null"
    if title.strip():
        safe = title.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’")
        vf += (f",drawtext=text='{safe}':fontcolor=white:fontsize=54:"
               f"box=1:boxcolor=black@0.45:boxborderw=18:"
               f"x=(w-text_w)/2:y=140:line_spacing=8")
    cmd = [ffmpeg, "-y", *bg_in, "-i", str(audio),
           "-t", f"{dur:.3f}", "-vf", vf,
           "-map", "0:v", "-map", "1:a",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20",
           "-pix_fmt", "yuv420p", "-r", "30", "-movflags", "+faststart",
           "-c:a", "aac", "-b:a", "160k", "-shortest", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.stderr.write(r.stderr[-1500:])
        raise SystemExit(f"ffmpeg falló al componer el base (código {r.returncode})")


def build_slideshow(audio: Path, out: Path, dur: float, images: list[Path],
                    title: str, ffmpeg: str, durations: list[float] | None = None) -> None:
    """Vídeo base con un SLIDESHOW de imágenes (b-roll) a pantalla completa: cada
    imagen su `durations[i]` s (o dur/N por defecto), cover del canvas + audio +
    título. Usa el CONCAT DEMUXER (no inputs -loop, que salen con código 255)."""
    n = len(images)
    if not durations or len(durations) != n:
        durations = [max(0.8, dur / n)] * n
    # Lista para el concat demuxer (rutas absolutas). Se repite la última imagen
    # porque el demuxer ignora la 'duration' del último fichero.
    listfile = out.with_suffix(".concat.txt")
    lines = ["ffconcat version 1.0"]
    for img, d in zip(images, durations):
        lines.append(f"file '{img.resolve()}'")
        lines.append(f"duration {max(0.5, d):.3f}")
    lines.append(f"file '{images[-1].resolve()}'")
    listfile.write_text("\n".join(lines), encoding="utf-8")

    vf = (f"scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=increase,"
          f"crop={CANVAS_W}:{CANVAS_H},setsar=1,fps=30")
    if title.strip():
        safe = title.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’")
        vf += (f",drawtext=text='{safe}':fontcolor=white:fontsize=54:box=1:"
               f"boxcolor=black@0.45:boxborderw=18:x=(w-text_w)/2:y=140")
    cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
           "-i", str(audio), "-vf", vf, "-map", "0:v", "-map", "1:a",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-r", "30", "-movflags", "+faststart", "-c:a", "aac", "-b:a", "160k",
           "-t", f"{dur:.3f}", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    listfile.unlink(missing_ok=True)
    if r.returncode != 0 or not out.exists():
        sys.stderr.write(r.stderr[-1500:])
        raise SystemExit(f"ffmpeg falló al componer el slideshow (código {r.returncode})")


def build_from_bgvideo(audio: Path, out: Path, dur: float, bgvideo: Path,
                       title: str, ffmpeg: str) -> None:
    """Usa un vídeo de fondo ya vertical (p. ej. fragmentos del partido concatenados)
    como imagen del reel: su vídeo + el audio (voz), recortado a la duración del audio."""
    vf = (f"scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=increase,"
          f"crop={CANVAS_W}:{CANVAS_H},setsar=1,fps=30")
    if title.strip():
        safe = title.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’")
        vf += (f",drawtext=text='{safe}':fontcolor=white:fontsize=54:box=1:"
               f"boxcolor=black@0.45:boxborderw=18:x=(w-text_w)/2:y=140")
    cmd = [ffmpeg, "-y", "-stream_loop", "-1", "-i", str(bgvideo), "-i", str(audio),
           "-vf", vf, "-map", "0:v", "-map", "1:a",
           "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
           "-r", "30", "-movflags", "+faststart", "-c:a", "aac", "-b:a", "160k",
           "-t", f"{dur:.3f}", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not out.exists():
        sys.stderr.write(r.stderr[-1500:])
        raise SystemExit(f"ffmpeg falló al componer con vídeo de fondo (código {r.returncode})")


def main() -> None:
    ap = argparse.ArgumentParser(description="Compone un reel vertical desde el audio")
    ap.add_argument("--audio", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--background", default="", help="imagen de fondo opcional")
    ap.add_argument("--bg-video", default="", help="vídeo de fondo ya vertical (fragmentos del partido)")
    ap.add_argument("--images", default="", help="imágenes b-roll (slideshow), separadas por comas")
    ap.add_argument("--durations", default="", help="duración (s) de cada imagen, separadas por comas")
    ap.add_argument("--title", default="")
    ap.add_argument("--subtitles", action="store_true")
    ap.add_argument("--lang", default="es")
    ap.add_argument("--music", default="", help="pista de música concreta; por defecto una aleatoria del banco")
    ap.add_argument("--no-music", action="store_true", help="no añadir música de fondo")
    ap.add_argument("--music-volume", type=float, default=0.10)
    ap.add_argument("--ffmpeg", default="ffmpeg")
    args = ap.parse_args()

    audio = Path(args.audio)
    if not audio.exists():
        raise SystemExit(f"No existe el audio: {audio}")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    dur = audio_duration(audio, args.ffmpeg)
    if dur <= 0:
        raise SystemExit("No se pudo leer la duración del audio.")

    print(f"Componiendo reel ({dur:.1f}s)...", flush=True)
    images = [Path(p) for p in args.images.split(",") if p.strip() and Path(p).exists()]
    bgvideo = Path(args.bg_video) if args.bg_video and Path(args.bg_video).exists() else None
    if bgvideo:
        print("Vídeo de fondo (fragmentos del partido).", flush=True)
        build_from_bgvideo(audio, out, dur, bgvideo, args.title, args.ffmpeg)
    elif images:
        durs = [float(x) for x in args.durations.split(",") if x.strip()] if args.durations else None
        print(f"Slideshow de {len(images)} imágenes b-roll.", flush=True)
        build_slideshow(audio, out, dur, images, args.title, args.ffmpeg, durations=durs)
    else:
        bg = Path(args.background) if args.background else None
        build_base(audio, out, dur, bg, args.title, args.ffmpeg)

    if args.subtitles:
        print("Añadiendo subtítulos karaoke (AssemblyAI)...", flush=True)
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from subtitle_engine import SubtitleEngine  # noqa: E402
        # Caché de transcripción PROPIA de este reel: si no, el motor reutiliza el
        # subtitle_words.json de otro reel de la misma carpeta (subtítulos cruzados).
        cache_dir = out.parent / f".sub_{out.stem}"
        cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            SubtitleEngine().add_subtitles_to_video(out, audio, (CANVAS_W, CANVAS_H), cache_dir=cache_dir)
        except Exception as exc:  # noqa: BLE001
            print(f"No se pudieron añadir subtítulos ({exc}); se deja el reel sin ellos.", flush=True)

    # Música de fondo (aleatoria del banco) por debajo de la voz, salvo --no-music.
    if not args.no_music:
        music = pick_music(args.music)
        if music:
            print(f"Añadiendo música de fondo: {music.name}", flush=True)
            add_background_music(out, music, dur, args.ffmpeg, volume=args.music_volume)
        else:
            print("Sin banco de música (backend/assets/music); reel sin música.", flush=True)

    print(f"Reel final: {out}", flush=True)


if __name__ == "__main__":
    main()
