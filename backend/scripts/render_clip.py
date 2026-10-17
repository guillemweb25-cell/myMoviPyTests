#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Renderiza un clip vertical completo: corte + pantalla partida + (opcional)
subtitulos karaoke incrustados.

Encadena make_vertical_clip (composicion vertical) y subtitle_engine
(transcripcion por palabra -> ASS karaoke -> quemado con ffmpeg).
"""
from __future__ import annotations

import argparse
import json
import shutil
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


def focus_plan_segments(persons_json: Path | None, plan: list, fps: float = 25.0):
    """Enfoque POR TRAMO. `plan` = [(t0, t1, person_id, cx_manual|None), ...]
    (person_id=-1 => centro). Si `cx_manual` viene dado (el usuario clicó un punto
    en el frame), se usa directamente; si no, se centra en la posición MEDIANA de esa
    persona durante el tramo. Devuelve los (t0,t1,cx) para el render 'follow'.
    No necesita detección si todos los tramos traen cx manual."""
    import json as _json
    det = {}
    if persons_json and Path(persons_json).exists():
        try:
            det = _json.loads(Path(persons_json).read_text(encoding="utf-8"))
        except Exception:
            det = {}
    persons = {p["id"]: p for p in det.get("persons", [])}
    segs = []
    for entry in plan:
        t0, t1, pid = entry[0], entry[1], entry[2]
        cx_manual = entry[3] if len(entry) > 3 else None
        if cx_manual is not None:
            cx = float(cx_manual)
        else:
            cx = 0.5
            p = persons.get(pid)
            if p:
                cxs = sorted(b[1] + b[3] / 2.0 for b in p["boxes"] if t0 <= b[0] / fps < t1)
                if cxs:
                    cx = cxs[len(cxs) // 2]
        segs.append((round(t0, 3), round(t1, 3), round(float(cx), 4)))
    return segs or None


def apply_person_blur(video: Path, start: float, end: float, out_path: Path,
                      blur_ids: list[int], persons_json: Path | None, ffmpeg: str,
                      manual_regions: list | None = None) -> Path | None:
    """Difumina las personas `blur_ids` (siguiéndolas frame a frame) más las
    `manual_regions` manuales fijas en el tramo [start,end]. Devuelve un segmento
    difuminado CON audio (para componer encima). None si falla (se sigue sin blur)."""
    import json as _json
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/
    try:
        from app.services import person_client  # noqa: E402
    except Exception:
        return None
    detection = {}
    if persons_json and Path(persons_json).exists():
        try:
            detection = _json.loads(Path(persons_json).read_text(encoding="utf-8"))
        except Exception:
            detection = {}
    manual_regions = manual_regions or []
    if not blur_ids and not manual_regions:
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

    print(f"Blur de personas {blur_ids} + {len(manual_regions)} región(es) manual(es)...", flush=True)
    ok = person_client.blur(seg, detection, blur_ids, blurred, static_regions=manual_regions)
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


def add_watermark(video: Path, watermark: Path, ffmpeg: str = "ffmpeg",
                  width_frac: float = 0.42, top_frac: float = 0.03) -> None:
    """Superpone el PNG `watermark` ARRIBA CENTRADO en el clip vertical (requisito
    de algunas campañas: 'watermark clearly visible'). Escala a `width_frac` del
    ancho del canvas, margen superior `top_frac` de la altura, respeta la
    transparencia. Si se pidió pero falla, LEVANTA error (no subir sin watermark)."""
    if not watermark.exists():
        raise SystemExit(f"ERROR: watermark no encontrado ({watermark}). No se genera el clip.")
    wm_w = int(CANVAS_W * width_frac)
    top = int(CANVAS_H * top_frac)
    tmp = video.with_name(video.stem + "_wm.mp4")
    fc = f"[1:v]scale={wm_w}:-1[wm];[0:v][wm]overlay=(W-w)/2:{top}"
    r = subprocess.run([ffmpeg, "-y", "-i", str(video), "-i", str(watermark),
                        "-filter_complex", fc, "-c:a", "copy", str(tmp)], capture_output=True)
    if tmp.exists() and tmp.stat().st_size > 0:
        tmp.replace(video)
    else:
        tmp.unlink(missing_ok=True)
        raise SystemExit("ERROR: no se pudo aplicar el watermark de la campaña. "
                         "No se genera el clip SIN watermark (sería no conforme). "
                         f"ffmpeg: {(r.stderr.decode()[-300:] if r.stderr else '')}")


def transcribe_words(vertical_path: Path, ffmpeg: str = "ffmpeg",
                     language: str = "es") -> list[dict]:
    """Palabras con tiempos del clip (AssemblyAI), SIN generar ASS ni quemar nada.
    Es la misma transcripcion que usa el karaoke; aqui se exporta para el worker
    de FX, que pinta los subtitulos el."""
    engine = SubtitleEngine()
    audio_path = extract_audio(vertical_path, ffmpeg)
    try:
        return engine.transcribe_words(audio_path, language_code=language) or []
    finally:
        audio_path.unlink(missing_ok=True)


def stamp_watermark_on_frame(frame: Path, watermark: Path, ffmpeg: str = "ffmpeg",
                             width_frac: float = 0.42, top_frac: float = 0.03) -> bool:
    """Pega el watermark sobre un PNG suelto, con la misma geometria que
    `add_watermark`. En el camino FX el vertical va SIN watermark (lo pinta
    Remotion como capa fija), asi que el fotograma de cierre hay que marcarlo
    aparte o la miniatura saldria sin marca: no conforme."""
    if not watermark.exists():
        return False
    wm_w = int(CANVAS_W * width_frac)
    top = int(CANVAS_H * top_frac)
    tmp = frame.with_name(frame.stem + "_wm.png")
    fc = f"[1:v]scale={wm_w}:-1[wm];[0:v][wm]overlay=(W-w)/2:{top}"
    subprocess.run([ffmpeg, "-y", "-i", str(frame), "-i", str(watermark),
                    "-filter_complex", fc, str(tmp)], capture_output=True)
    if tmp.exists() and tmp.stat().st_size > 0:
        tmp.replace(frame)
        return True
    tmp.unlink(missing_ok=True)
    return False


# Palabras vacias (castellano): articulos, preposiciones, conjunciones, pronombres
# y verbos auxiliares. Un punch zoom sobre "la" o "una" no significa nada.
_STOPWORDS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "lo", "al", "del",
    "de", "a", "en", "con", "por", "para", "sin", "sobre", "entre", "hasta",
    "desde", "hacia", "segun", "tras", "ante", "bajo", "contra", "durante",
    "y", "e", "o", "u", "ni", "que", "si", "no", "pero", "sino", "como",
    "cuando", "donde", "porque", "aunque", "pues", "mas", "muy", "ya", "mismo",
    "me", "te", "se", "le", "nos", "os", "les", "mi", "tu", "su", "sus", "mis",
    "yo", "el", "ella", "ellos", "ellas", "usted", "ustedes", "nosotros",
    "es", "son", "era", "eran", "fue", "fueron", "ser", "estar", "esta",
    "estan", "hay", "ha", "han", "he", "has", "habia", "este", "esta", "esto",
    "ese", "esa", "eso", "aquel", "todo", "toda", "todos", "todas", "otro",
    "otra", "cada", "tan", "tanto", "bien", "aqui", "alli", "ahi", "asi",
}

_ACCENTS = str.maketrans("áéíóúüñ", "aeiouun")


def _content_word(text: str) -> str:
    """Normaliza una palabra; devuelve "" si es vacia de significado."""
    w = text.strip(" .,!?¿¡:;\"'«»—-").lower().translate(_ACCENTS)
    if len(w) < 4 or w in _STOPWORDS or not w.isalpha():
        return ""
    return w


def derive_emphasis(words: list[dict], min_gap: float = 3.5,
                    window: float = 1.2) -> list[dict]:
    """Elige en que palabras cae un punch zoom.

    Mientras no sea un modelo quien marque las palabras fuertes (eso es lo que
    pide el documento para 13C), se eligen por peso: se deja pasar `min_gap`
    segundos y, de las palabras de la siguiente ventana de `window` segundos, se
    coge la mas larga que NO sea vacia.

    Repartirlos solo por ritmo, como se hacia antes, ponia el golpe en "la",
    "una" o "sin", que es justo donde no significa nada.
    """
    marks: list[dict] = []
    last = -min_gap
    i = 0
    while i < len(words):
        start = float(words[i].get("start", 0))
        if start - last < min_gap:
            i += 1
            continue
        best, best_len = -1, 0
        for j in range(i, len(words)):
            if float(words[j].get("start", 0)) - start > window:
                break
            weight = len(_content_word(words[j].get("text", "")))
            if weight > best_len:
                best, best_len = j, weight
        if best < 0:
            # Ninguna palabra con peso en la ventana: mejor saltarse el zoom que
            # ponerlo en un "que".
            i += 1
            continue
        marks.append({"word_index": best, "effect": "punch_zoom"})
        last = float(words[best].get("start", 0))
        i = best + 1
    return marks


def render_fx(out_path: Path, args, duration: float,
              facecam) -> tuple[bool, Path | None]:
    """Camino FX: manda el vertical al worker de Remotion para que pinte
    subtitulos, overlay y watermark.

    Devuelve (ok, clean_frame). Si ok es False hay que seguir por el camino ASS
    de siempre: el worker no esta, rechazo el payload o fallo. Nunca deja el
    clip a medias.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/
    try:
        from app.services import fx_client  # noqa: E402
    except Exception as exc:
        print(f"[fx] no se pudo importar el cliente ({exc}); uso el camino ASS.", flush=True)
        return False, None

    if not fx_client.available():
        print("[fx] worker no disponible; uso el camino ASS.", flush=True)
        return False, None

    watermark = Path(args.watermark) if args.watermark else None
    if watermark and not watermark.exists():
        # Mismo criterio que add_watermark: si se pidio watermark y no esta, no
        # se genera el clip. Caer al camino ASS solo escondería el problema.
        raise SystemExit(f"ERROR: watermark no encontrado ({watermark}). No se genera el clip.")

    # Fotograma de cierre: se saca del vertical LIMPIO (sin subtitulos) y se le
    # pega el watermark aparte, porque aqui el vertical aun no lo lleva.
    clean_frame: Path | None = None
    if args.endcard > 0:
        clean_frame = out_path.with_suffix("").with_name(out_path.stem + "_ecclean.png")
        frame_t = max(0.0, _probe_duration(out_path) * max(1, min(99, args.endcard)) / 100)
        subprocess.run([args.ffmpeg, "-y", "-ss", f"{frame_t:.2f}", "-i", str(out_path),
                        "-frames:v", "1", str(clean_frame)], check=True, capture_output=True)
        if watermark and not stamp_watermark_on_frame(clean_frame, watermark, args.ffmpeg):
            raise SystemExit("ERROR: no se pudo marcar el fotograma de cierre con el "
                             "watermark de la campana. No se genera el clip.")

    words: list[dict] = []
    if args.subtitles:
        print("[fx] transcribiendo palabras para los subtitulos animados...", flush=True)
        words = fx_client.words_from_assemblyai(transcribe_words(out_path, args.ffmpeg, args.lang))
        if not words:
            print("[fx] sin palabras en la transcripcion; el clip saldra sin subtitulos.", flush=True)

    overlay_text = args.overlay.strip()
    # Zonas que ninguna capa puede tapar. El worker sube los subtitulos si hace
    # falta para respetarlas.
    safe_zones = [{"name": "yt_ui", "y0": 0.85, "y1": 1.00}]
    if watermark:
        safe_zones.insert(0, {"name": "watermark", "y0": 0.00, "y1": 0.14})
    if overlay_text:
        safe_zones.append({"name": "overlay", "y0": 0.58, "y1": 0.68})

    payload = {
        "fps": 30,
        "duration": duration,
        "preset": args.fx_preset,
        "layout": {
            "mode": "facecam" if facecam is not None else "split",
            "top_ratio": args.top_ratio,
        },
        "words": words,
        "safe_zones": safe_zones,
        "emphasis": derive_emphasis(words),
        # Whoosh en cada zoom. El preset manda: si no hace zooms, tampoco suena.
        "sfx": True,
        # Con watermark la barra NUNCA va arriba: se le montaria encima.
        "progress_bar": "split_line" if watermark else "top",
    }
    if args.fx_hook.strip():
        payload["hook"] = {"text": args.fx_hook.strip(), "duration": 2.0}
    if args.fx_music:
        # file=None -> el worker elige una del banco montado.
        payload["music"] = {"file": None, "volume": args.fx_music_volume, "duck": True}
    if overlay_text:
        payload["overlay"] = {"text": overlay_text, "center_y": 0.63}
    if watermark:
        payload["watermark"] = {"required": True, "width_frac": 0.42, "top_frac": 0.03}
    # OJO: `endcard` NO va en el payload. El worker aun no lo pinta (fase 13C) y
    # rechazaria la peticion entera; aqui se anade despues con ffmpeg, igual que
    # en el camino ASS.

    fx_out = out_path.with_name(out_path.stem + "_fx.mp4")
    print(f"[fx] renderizando con preset '{args.fx_preset}'...", flush=True)
    result = fx_client.render(out_path, payload, fx_out, watermark=watermark)
    if result is None:
        if clean_frame:
            clean_frame.unlink(missing_ok=True)
        print("[fx] el worker no devolvio el clip; uso el camino ASS.", flush=True)
        return False, None

    fx_out.replace(out_path)
    print("[fx] clip con motion graphics listo.", flush=True)
    return True, clean_frame


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
    parser.add_argument("--manual-blur", default="", help="regiones manuales fijas a difuminar: JSON [[x,y,w,h],...] normalizado")
    parser.add_argument("--persons-json", default="", help="ruta al JSON de detección (cajas por persona)")
    parser.add_argument("--focus-person", type=int, default=-1, help="id de persona a la que centra el recorte de arriba (-1 = no)")
    parser.add_argument("--focus-plan", default="", help="enfoque por tramo: 't0:t1:personId,...' (personId=-1=centro)")
    parser.add_argument("--watermark", default="", help="ruta a un PNG a superponer arriba centrado (watermark de campaña)")
    parser.add_argument("--facecam", default="", help="modo facecam: rect de la webcam 'x,y,w,h' normalizado (arriba la cara, abajo la pantalla)")
    parser.add_argument("--screen-zoom", type=float, default=1.4, help="zoom de la pantalla abajo en modo facecam (1.0 = completa)")
    parser.add_argument("--fx-preset", default="none",
                        help="preset de motion graphics del worker de FX ('none' = camino ASS de siempre)")
    parser.add_argument("--fx-hook", default="",
                        help="titulo gancho de los primeros 2s (solo con --fx-preset)")
    parser.add_argument("--fx-music", action="store_true",
                        help="musica de fondo del banco, bajando bajo la voz (solo con --fx-preset)")
    parser.add_argument("--fx-music-volume", type=float, default=0.10,
                        help="volumen de la musica de fondo (0-1)")
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
    manual_regions = []
    if args.manual_blur:
        try:
            manual_regions = [[float(v) for v in r] for r in json.loads(args.manual_blur) if len(r) == 4]
        except Exception:
            manual_regions = []
    persons_json = Path(args.persons_json) if args.persons_json and Path(args.persons_json).exists() else None
    if blur_ids or manual_regions:
        blurred = apply_person_blur(video, start, end, out_path, blur_ids,
                                    persons_json, args.ffmpeg, manual_regions=manual_regions)
        if blurred:
            video, start, end = blurred, 0.0, round(end - start, 3)
        else:
            # Se pidió blur pero no se pudo aplicar (worker caído/sin respuesta).
            # NO se genera el clip SIN blur: en campañas que exigen difuminar,
            # subir el clip sin blur sería contenido no conforme. Falla el render.
            raise SystemExit(
                "ERROR: se pidió blur de personas pero el worker no lo aplicó "
                "(caído o sin respuesta). No se genera el clip SIN blur para no "
                "subir contenido no conforme. Reintenta con el worker disponible."
            )

    # Modo FACECAM: arriba el recuadro de la webcam, abajo la pantalla (zoom ligero).
    # Anula el resto de encuadres (no hay "hablante" que seguir en una pantalla).
    facecam = None
    if args.facecam:
        try:
            parts = [float(x) for x in args.facecam.split(",")]
            if len(parts) == 4 and parts[2] > 0.02 and parts[3] > 0.02:
                facecam = tuple(parts)
        except Exception:
            facecam = None

    follow_segments = None
    focus = args.focus
    if facecam is not None:
        print(f"Encuadre facecam: cara={facecam}, zoom pantalla={args.screen_zoom}", flush=True)
    elif args.focus_plan:
        # Enfoque POR TRAMO: 't0:t1:pid[:cx],...' (cx opcional = punto manual clicado).
        plan = []
        for chunk in args.focus_plan.split(","):
            parts = chunk.split(":")
            if len(parts) >= 3:
                cx = float(parts[3]) if len(parts) >= 4 and parts[3] != "" else None
                plan.append((float(parts[0]), float(parts[1]), int(parts[2]), cx))
        pj = Path(args.persons_json) if args.persons_json and Path(args.persons_json).exists() else None
        follow_segments = focus_plan_segments(pj, plan) if plan else None
        if follow_segments:
            print(f"Enfoque por tramo: {len(follow_segments)} tramos.", flush=True)
            focus = "follow"
    elif args.focus_person >= 0 and args.persons_json and Path(args.persons_json).exists():
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
        follow_segments=follow_segments, facecam=facecam, screen_zoom=args.screen_zoom,
    )

    duration = round(end - start, 3)

    # Copia "raw" del vertical recien compuesto (encuadre y blur, pero sin
    # subtitulos, overlay, watermark, FX ni cierre), para descargarla y hacer
    # pruebas. El API la expone como `rawPath` si existe.
    raw_path = out_path.with_name(out_path.stem + "_raw.mp4")
    shutil.copyfile(out_path, raw_path)
    print(f"Vertical sin subtitulos: {raw_path}", flush=True)

    # Camino FX (motion graphics con Remotion). Pinta subtitulos, overlay y
    # watermark en una sola pasada, con el watermark como capa fija que los
    # zooms no escalan. Si no se puede, `fx_ok` es False y seguimos por el
    # camino de siempre: NUNCA se queda un clip a medias.
    fx_ok = False
    clean_frame: Path | None = None
    if args.fx_preset and args.fx_preset != "none":
        fx_ok, clean_frame = render_fx(out_path, args, duration, facecam)

    if not fx_ok:
        # Watermark de la campaña (arriba centrado). Se aplica ANTES de sacar el
        # fotograma de cierre para que también aparezca en la miniatura.
        if args.watermark:
            print("Anadiendo watermark de la campana (arriba centrado)...", flush=True)
            add_watermark(out_path, Path(args.watermark), ffmpeg=args.ffmpeg)

        # Fotograma de cierre limpio: se saca AHORA (vertical sin karaoke ni overlay) para que
        # la miniatura no arrastre subtitulos quemados. La duracion no cambia con los pasos
        # siguientes, asi que el % apunta al mismo instante.
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
            burn_overlay(out_path, args.overlay, duration, ffmpeg=args.ffmpeg)

    # El fotograma de cierre se anade igual por los dos caminos: el worker aun no
    # lo pinta (fase 13C), asi que lo monta ffmpeg sobre el clip ya terminado.
    if args.endcard > 0:
        print(f"Anadiendo fotograma final con fadeout de audio (al {args.endcard}%)...", flush=True)
        add_fade_and_endcard(out_path, args.overlay or "", args.endcard, ffmpeg=args.ffmpeg, clean_frame=clean_frame)

    print(f"Clip final: {out_path}", flush=True)


if __name__ == "__main__":
    main()
