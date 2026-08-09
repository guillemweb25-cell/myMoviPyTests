#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Renderiza un clip vertical completo: corte + pantalla partida + (opcional)
subtitulos karaoke incrustados.

Encadena make_vertical_clip (composicion vertical) y subtitle_engine
(transcripcion por palabra -> ASS karaoke -> quemado con ffmpeg).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import textwrap
from pathlib import Path

from make_vertical_clip import CANVAS_H, CANVAS_W, default_output, make_clip, parse_timecode
from subtitle_engine import SubtitleEngine


def _ass_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


def burn_overlay(video_path: Path, text: str, duration: float, ffmpeg: str = "ffmpeg") -> Path:
    """Quema un texto fijo (persistente) con caja semitransparente, encima de los subtitulos."""
    font_size = int(CANVAS_W * 0.042)          # ~45px, mas pequeno que el karaoke
    outline = 2
    wrapped = "\\N".join(textwrap.wrap(text.strip(), width=26)) or text.strip()
    n_lines = wrapped.count("\\N") + 1

    # Posicion fija por ENCIMA del karaoke. El karaoke se ancla a 22% del fondo y su
    # texto sube hasta ~0.71*H; ponemos el overlay a 0.63*H para que la barra (que baja
    # ~0.05*H) termine sobre el karaoke sin taparlo.
    center_y = int(CANVAS_H * 0.63)
    bar_half = int(font_size * 0.75 * n_lines) + 22
    y1, y2 = center_y - bar_half, center_y + bar_half
    end = _ass_time(duration)
    # Barra: rectangulo a todo el ancho relleno con el color (semitransparente) del estilo Bar.
    bar = f"{{\\pos(0,0)\\p1}}m 0 {y1} l {CANVAS_W} {y1} {CANVAS_W} {y2} 0 {y2}{{\\p0}}"

    ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {CANVAS_W}
PlayResY: {CANVAS_H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Bar,Liberation Sans,{font_size},&H80000000,&H000000FF,&H80000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1
Style: Overlay,Liberation Sans,{font_size},&H0000FFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,{outline},0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,{end},Bar,,0,0,0,,{bar}
Dialogue: 1,0:00:00.00,{end},Overlay,,0,0,0,,{{\\an5\\pos({CANVAS_W // 2},{center_y})}}{wrapped}
"""
    ass_path = video_path.with_suffix(".overlay.ass")
    ass_path.write_text(ass_content, encoding="utf-8")
    out_path = video_path.with_name(f"{video_path.stem}_ovl.mp4")
    try:
        SubtitleEngine().burn_subtitles(video_path, ass_path, out_path)
    finally:
        ass_path.unlink(missing_ok=True)
    out_path.replace(video_path)
    return video_path


def _probe_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 0.0


def _endcard_ass(caption: str, seconds: float) -> str:
    """ASS para la tarjeta final: caption grande centrado sobre barra que tapa la zona de subtitulos."""
    font_size = int(CANVAS_W * 0.06)
    wrapped = "\\N".join(textwrap.wrap(caption.strip(), width=18)) or caption.strip()
    n_lines = wrapped.count("\\N") + 1
    center_y = int(CANVAS_H * 0.60)
    bar_half = int(font_size * 0.85 * n_lines) + 40
    y1, y2 = center_y - bar_half, center_y + bar_half
    end = _ass_time(seconds)
    bar = f"{{\\pos(0,0)\\p1}}m 0 {y1} l {CANVAS_W} {y1} {CANVAS_W} {y2} 0 {y2}{{\\p0}}"
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {CANVAS_W}
PlayResY: {CANVAS_H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Bar,Liberation Sans,{font_size},&H90000000,&H000000FF,&H90000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1
Style: EC,Liberation Sans,{font_size},&H0000FFFF,&H000000FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,3,0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,{end},Bar,,0,0,0,,{bar}
Dialogue: 1,0:00:00.00,{end},EC,,0,0,0,,{{\\an5\\pos({CANVAS_W // 2},{center_y})}}{wrapped}
"""


def add_fade_and_endcard(video_path: Path, caption: str, percent: int,
                         fade_secs: float = 1.2, hold_secs: float = 1.3,
                         ffmpeg: str = "ffmpeg", clean_frame: Path | None = None) -> Path:
    """Sin fundido a negro: corta a un fotograma final (al `percent` % del clip) con el
    caption grande y, mientras se muestra ese fotograma, el audio hace fade out. Tras el
    fadeout el fotograma se mantiene unos segundos (para usarlo de miniatura).

    `clean_frame`: fotograma pre-extraido SIN karaoke/overlay (para una miniatura limpia).
    Si no se pasa, se saca del propio video (arrastrara los subtitulos quemados).
    Devuelve video_path (sobrescrito)."""
    duration = _probe_duration(video_path)
    if duration <= 0:
        return video_path
    base = video_path.with_suffix("")
    frame = base.with_name(base.name + "_ecframe.png")
    body = base.with_name(base.name + "_body.mp4")
    endcard = base.with_name(base.name + "_endcard.mp4")
    ass_path = base.with_name(base.name + "_endcard.ass")
    tmp_out = base.with_name(base.name + "_final.mp4")

    still_dur = fade_secs + hold_secs
    if clean_frame and Path(clean_frame).exists():
        frame = Path(clean_frame)
    else:
        frame_t = max(0.0, duration * max(1, min(99, percent)) / 100)
        subprocess.run([ffmpeg, "-y", "-ss", f"{frame_t:.2f}", "-i", str(video_path), "-frames:v", "1", str(frame)],
                       check=True, capture_output=True)

    # Cuerpo del clip: hasta `fade_secs` antes del final (esos ultimos segundos de video
    # se sustituyen por el fotograma; su audio suena bajo el fotograma haciendo fadeout).
    body_dur = max(0.1, duration - fade_secs)
    subprocess.run([
        ffmpeg, "-y", "-i", str(video_path), "-t", f"{body_dur:.2f}",
        "-vf", "setsar=1", "-r", "30",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(body),
    ], check=True, capture_output=True)

    # Tarjeta final: fotograma fijo con el caption; audio = la cola del clip (los ultimos
    # `fade_secs`) haciendo fade out, y silencio durante el `hold` restante.
    ass_path.write_text(_endcard_ass(caption, still_dur), encoding="utf-8")
    subprocess.run([
        ffmpeg, "-y",
        "-loop", "1", "-t", f"{still_dur}", "-i", str(frame),
        "-ss", f"{body_dur:.2f}", "-i", str(video_path),
        "-filter_complex",
        f"[0:v]ass={ass_path},fade=t=in:st=0:d=0.25,setsar=1[v];"
        f"[1:a]atrim=0:{fade_secs},afade=t=out:st=0:d={fade_secs},apad=whole_dur={still_dur}[a]",
        "-map", "[v]", "-map", "[a]", "-t", f"{still_dur}", "-r", "30",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(endcard),
    ], check=True, capture_output=True)

    subprocess.run([
        ffmpeg, "-y", "-i", str(body), "-i", str(endcard),
        "-filter_complex", "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[v][a]",
        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(tmp_out),
    ], check=True, capture_output=True)

    tmp_out.replace(video_path)
    for extra in (frame, body, endcard, ass_path):
        extra.unlink(missing_ok=True)
    return video_path


def extract_audio(video_path: Path, ffmpeg: str = "ffmpeg") -> Path:
    audio_path = video_path.with_suffix(".clip_audio.wav")
    cmd = [ffmpeg, "-y", "-i", str(video_path), "-vn", "-ac", "1", "-ar", "16000", str(audio_path)]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.stderr.write(result.stderr[-800:])
        raise SystemExit("No se pudo extraer el audio del clip para subtitular.")
    return audio_path


def add_subtitles(vertical_path: Path, ffmpeg: str = "ffmpeg", language: str = "es") -> Path:
    engine = SubtitleEngine()
    audio_path = extract_audio(vertical_path, ffmpeg)
    try:
        words = engine.transcribe_words(audio_path, language_code=language)
    finally:
        audio_path.unlink(missing_ok=True)

    if not words:
        print("Sin palabras en la transcripcion; se omiten subtitulos.", flush=True)
        return vertical_path

    ass_path = vertical_path.with_suffix(".karaoke.ass")
    engine.generate_ass(words, (CANVAS_W, CANVAS_H), ass_path)
    subtitled_path = vertical_path.with_name(f"{vertical_path.stem}_sub.mp4")
    engine.burn_subtitles(vertical_path, ass_path, subtitled_path)
    ass_path.unlink(missing_ok=True)
    vertical_path.unlink(missing_ok=True)
    return subtitled_path


def get_follow_segments(video: Path, start: float, end: float, out_path: Path, ffmpeg: str):
    """Para el encuadre 'follow': analiza SOLO el tramo del clip con el worker de ASD y
    devuelve [(t0, t1, center_x_norm), ...] en tiempo LOCAL del clip. None si no se puede
    (el render cae entonces a encuadre centro).

    Se analiza por clip (no el vídeo entero) a propósito: el coste queda ACOTADO por
    nº de clips × duración (~30s), independiente de si la fuente son 15 min o 3 horas.
    Cacheado por clip+tramo, así que re-renderizar es instantáneo. El worker tiene la
    visualización desactivada, así que el pase es solo detección + ASD."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/
    try:
        from app.services import asd_client  # noqa: E402
    except Exception:
        return None

    duration = round(end - start, 3)
    tmp = out_path.parent / f"_asd_{out_path.stem}.mp4"
    cache = out_path.parent / f"asd_{out_path.stem}_{int(start)}_{int(end)}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not cache.exists():
        # Corta el tramo CON audio (TalkNet es audio-visual) para el análisis.
        subprocess.run([
            ffmpeg, "-y", "-ss", f"{start:.3f}", "-i", str(video), "-t", f"{duration:.3f}",
            "-r", "25", "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-c:a", "aac", str(tmp),
        ], capture_output=True)
    data = asd_client.fetch_segments(tmp if tmp.exists() else out_path, cache_path=cache)
    tmp.unlink(missing_ok=True)
    if not data:
        return None

    spk = {s["id"]: s["center_norm"][0] for s in data.get("speakers", [])}
    segs = []
    for seg in data.get("segments", []):  # ya en tiempo local (analizamos el tramo cortado)
        cx = spk.get(seg.get("speaker"))
        if cx is not None:
            segs.append((float(seg["start"]), float(seg["end"]), float(cx)))
    return segs or None


def person_focus_segments(persons_json: Path, person_id: int, duration: float, fps: float = 25.0):
    """Construye los tramos (t0,t1,cx) que siguen a la persona `person_id` (de la
    detección), para que el recorte superior la centre. Rellena huecos manteniendo la
    última posición y agrupa en ventanas de ~0.4s (expresión ffmpeg manejable)."""
    import json as _json
    try:
        det = _json.loads(persons_json.read_text(encoding="utf-8"))
    except Exception:
        return None
    person = next((p for p in det.get("persons", []) if p.get("id") == person_id), None)
    if not person or not person.get("boxes"):
        return None

    total = max(1, int(round(duration * fps)))
    by_frame = {}
    for f, x, y, w, h in person["boxes"]:
        by_frame[int(f)] = x + w / 2.0  # centro x normalizado
    cx = [None] * total
    last = None
    for i in range(total):
        if i in by_frame:
            last = by_frame[i]
        cx[i] = last
    # rellena el principio (si empezó sin detección) con el primer valor conocido
    first = next((v for v in cx if v is not None), 0.5)
    cx = [v if v is not None else first for v in cx]

    win = max(1, int(round(0.4 * fps)))
    raw = []
    for s in range(0, total, win):
        e = min(s + win, total)
        seg = sorted(cx[s:e])
        raw.append([s / fps, e / fps, float(seg[len(seg) // 2])])
    # Fusiona ventanas consecutivas con posición similar → expresión ffmpeg corta.
    merged: list[list[float]] = []
    for s, e, c in raw:
        if merged and abs(merged[-1][2] - c) < 0.03:
            merged[-1][1] = e
        else:
            merged.append([s, e, c])
    return [(round(s, 3), round(e, 3), round(c, 4)) for s, e, c in merged] or None


def apply_person_blur(video: Path, start: float, end: float, out_path: Path,
                      blur_ids: list[int], persons_json: Path, ffmpeg: str) -> Path | None:
    """Difumina las personas `blur_ids` en el tramo [start,end] y devuelve un segmento
    difuminado CON audio (para componer encima). None si falla (se sigue sin blur)."""
    import json as _json
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/
    try:
        from app.services import person_client  # noqa: E402
        detection = _json.loads(persons_json.read_text(encoding="utf-8"))
    except Exception:
        return None

    dur = round(end - start, 3)
    base = out_path.with_suffix("")
    seg = base.with_name(base.name + "_blurseg.mp4")     # tramo con audio
    blurred = base.with_name(base.name + "_blurvid.mp4")  # difuminado (sin audio)
    final = base.with_name(base.name + "_blurfinal.mp4")  # difuminado + audio
    out_path.parent.mkdir(parents=True, exist_ok=True)

    subprocess.run([ffmpeg, "-y", "-ss", f"{start:.3f}", "-i", str(video), "-t", f"{dur:.3f}",
                    "-r", "25", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-c:a", "aac", str(seg)], capture_output=True)
    if not seg.exists():
        return None

    print(f"Blur de personas {blur_ids} (siguiéndolas frame a frame)...", flush=True)
    ok = person_client.blur(seg, detection, blur_ids, blurred)
    if not ok:
        print("Worker de personas no disponible o sin cajas; se sigue SIN blur.", flush=True)
        seg.unlink(missing_ok=True)
        blurred.unlink(missing_ok=True)
        return None

    # remuxea el audio original sobre el vídeo difuminado.
    subprocess.run([ffmpeg, "-y", "-i", str(blurred), "-i", str(seg),
                    "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "20", "-c:a", "aac", "-shortest", str(final)], capture_output=True)
    seg.unlink(missing_ok=True)
    blurred.unlink(missing_ok=True)
    return final if final.exists() else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Render de clip vertical con subtitulos opcionales")
    parser.add_argument("--video", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--out", default=None)
    parser.add_argument("--top-ratio", type=float, default=0.5)
    parser.add_argument("--focus", default="center", choices=["left", "center", "right", "follow"])
    parser.add_argument("--zoom", type=float, default=1.0)
    parser.add_argument("--subtitles", action="store_true", help="Quemar subtitulos karaoke")
    parser.add_argument("--lang", default="es", help="Idioma del audio para los subtitulos (es, en...)")
    parser.add_argument("--overlay", default="", help="Texto fijo visible todo el clip (encima de los subs)")
    parser.add_argument("--endcard", type=int, default=0, help="%% del clip para el fotograma de cierre/miniatura (0 = sin tarjeta)")
    parser.add_argument("--blur-persons", default="", help="ids de personas a difuminar, separados por comas")
    parser.add_argument("--persons-json", default="", help="ruta al JSON de detección (cajas por persona)")
    parser.add_argument("--focus-person", type=int, default=-1, help="id de persona a la que centra el recorte de arriba (-1 = no)")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    args = parser.parse_args()

    video = Path(args.video)
    if not video.exists():
        raise SystemExit(f"No existe el video: {video}")

    start = parse_timecode(args.start)
    end = parse_timecode(args.end)
    out_path = Path(args.out) if args.out else default_output(video, start, end)

    # Blur de personas: difumina el tramo ANTES de componer. A partir de aquí todo
    # opera sobre el segmento difuminado (video local [0, dur]).
    blur_ids = [int(x) for x in args.blur_persons.split(",") if x.strip().isdigit()]
    if blur_ids and args.persons_json and Path(args.persons_json).exists():
        blurred = apply_person_blur(video, start, end, out_path, blur_ids,
                                    Path(args.persons_json), args.ffmpeg)
        if blurred:
            video, start, end = blurred, 0.0, round(end - start, 3)

    follow_segments = None
    focus = args.focus
    if args.focus_person >= 0 and args.persons_json and Path(args.persons_json).exists():
        # Enfoque manual: el recorte de arriba centra en la persona elegida (Fase 3).
        follow_segments = person_focus_segments(Path(args.persons_json), args.focus_person,
                                                round(end - start, 3))
        if follow_segments:
            print(f"Enfoque manual en persona {args.focus_person} ({len(follow_segments)} tramos).", flush=True)
            focus = "follow"
        else:
            print("No hay cajas para esa persona; uso el encuadre normal.", flush=True)
    elif focus == "follow":
        print("Encuadre 'Seguir al hablante': analizando quién habla (ASD)...", flush=True)
        follow_segments = get_follow_segments(video, start, end, out_path, args.ffmpeg)
        if follow_segments:
            print(f"ASD: {len(follow_segments)} tramos de hablante detectados.", flush=True)
        else:
            print("ASD no disponible (worker apagado o sin caras); uso encuadre centro.", flush=True)
            focus = "center"

    make_clip(
        video, start, end, out_path,
        top_ratio=args.top_ratio, focus=focus, zoom=args.zoom, ffmpeg=args.ffmpeg,
        follow_segments=follow_segments,
    )

    # Fotograma de cierre limpio: se saca AHORA (vertical sin karaoke ni overlay) para que
    # la miniatura no arrastre subtitulos quemados. La duracion no cambia con los pasos
    # siguientes, asi que el % apunta al mismo instante.
    clean_frame: Path | None = None
    if args.endcard > 0:
        clean_frame = out_path.with_suffix("").with_name(out_path.stem + "_ecclean.png")
        dur = _probe_duration(out_path)
        frame_t = max(0.0, dur * max(1, min(99, args.endcard)) / 100)
        subprocess.run([args.ffmpeg, "-y", "-ss", f"{frame_t:.2f}", "-i", str(out_path),
                        "-frames:v", "1", str(clean_frame)], check=True, capture_output=True)

    if args.subtitles:
        print("Anadiendo subtitulos karaoke...", flush=True)
        final = add_subtitles(out_path, ffmpeg=args.ffmpeg, language=args.lang)
        if final != out_path:
            final.replace(out_path)

    if args.overlay.strip():
        print("Anadiendo texto fijo (overlay)...", flush=True)
        burn_overlay(out_path, args.overlay, round(end - start, 3), ffmpeg=args.ffmpeg)

    if args.endcard > 0:
        print(f"Anadiendo fotograma final con fadeout de audio (al {args.endcard}%)...", flush=True)
        add_fade_and_endcard(out_path, args.overlay or "", args.endcard, ffmpeg=args.ffmpeg, clean_frame=clean_frame)

    print(f"Clip final: {out_path}", flush=True)


if __name__ == "__main__":
    main()
