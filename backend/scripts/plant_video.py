#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JOB: vídeo de crecimiento de planta en time-lapse (estilo plant_growth) con WAN 2.2.

Plan (LLM) → primera imagen (maceta vacía, ComfyUI/SDXL) → 3 clips WAN i2v
encadenados por el ÚLTIMO FOTOGRAMA (clip N empieza donde acabó N-1) → montaje
vertical continuo. Usa la GPU del Windows (ComfyUI). Sin música (ASMR/diegético).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app import db  # noqa: E402
from app.services import comfy_client, wan_client  # noqa: E402
from app.services.plant_engine import plant_plan  # noqa: E402


def _last_frame(video: Path, out: Path, ffmpeg: str = "ffmpeg") -> bool:
    """Extrae el último fotograma del vídeo (para encadenar el siguiente clip)."""
    subprocess.run([ffmpeg, "-y", "-sseof", "-0.2", "-i", str(video), "-update", "1",
                    "-frames:v", "1", "-q:v", "2", str(out)], capture_output=True, text=True)
    return out.exists()


MUSIC_DIR = Path(__file__).resolve().parents[1] / "assets" / "music"


def _pick_music(explicit: str = "") -> "Path | None":
    """Música concreta (por nombre de fichero) o una aleatoria del banco."""
    if explicit:
        p = MUSIC_DIR / Path(explicit).name
        if p.exists():
            return p
    if MUSIC_DIR.exists():
        import random
        tracks = sorted(MUSIC_DIR.glob("*.mp3"))
        if tracks:
            return random.choice(tracks)
    return None


def _has_audio(media: Path, ffmpeg: str = "ffmpeg") -> bool:
    r = subprocess.run([ffmpeg, "-i", str(media)], capture_output=True, text=True)
    return "Audio:" in r.stderr


def _normalize(clip: Path, out: Path, w: int, h: int, ffmpeg: str = "ffmpeg") -> None:
    """Clip → mp4 normalizado a WxH (cover), 30 fps, MUDO (para WAN encadenado)."""
    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps=30"
    subprocess.run([ffmpeg, "-y", "-i", str(clip), "-vf", vf, "-an",
                    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-r", "30", str(out)], capture_output=True, text=True)


def _norm_keep_audio(src: Path, out: Path, w: int, h: int, ffmpeg: str = "ffmpeg") -> None:
    """Normaliza a WxH CONSERVANDO el audio del clip (para encadenar clips con audio)."""
    vf = f"[0:v:0]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps=30[v]"
    subprocess.run([ffmpeg, "-y", "-i", str(src), "-filter_complex", vf,
                    "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "ultrafast",
                    "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "160k",
                    str(out)], capture_output=True, text=True)


def _grok_growth_prompts(scene: str, plant: str, n_clips: int) -> list:
    """Prompts para n clips encadenados. n==1: crecimiento puro sin manos. n>=2: modo
    'manos' (clip 1 planta la semilla, último clip madura el fruto y lo cosecha)."""
    if n_clips == 1:
        return [(
            f"{scene} Slow continuous satisfying time-lapse of a {plant} growing in this exact pot: "
            f"begins on bare soil, a sprout pushes up and grows GRADUALLY the whole clip — leaves "
            f"unfurl, stem thickens, branches spread, then buds, flowers and ripe fruit by the end. "
            f"The day-night cycle passes ~twice (day, sunset, starry night, dawn), shadows sweeping. "
            f"Locked static camera, no zoom or pan. NO hands, nothing enters the frame.")]
    prompts = []
    prompts.append(
        f"{scene} A human hand enters from the side holding a single seed/pit of a {plant}, gently "
        f"presses it into the centre of the bare soil and covers it, then the hand leaves. Then a "
        f"smooth continuous time-lapse begins and grows FAST into a small young {plant} sapling with "
        f"several branches by the end. Day-night cycle passes ~once (day, sunset, starry night, dawn). "
        f"Locked camera, no zoom/pan. Only the hand at the very start; then nothing else enters.")
    for _ in range(n_clips - 2):  # clips intermedios (solo si n>2): crecimiento puro
        prompts.append(
            f"{scene} Pure continuous time-lapse of a {plant} growing FAST: the tree fills out, "
            f"branches spread, leaves multiply. Day-night cycle passes ~once. Locked camera, no hands.")
    prompts.append(
        f"{scene} Pure continuous time-lapse of a {plant} growing FAST: it fills out, blossoms bloom "
        f"and petals fall, then fruit forms and ripens QUICKLY into plump, glossy, FULLY RIPE fruit — "
        f"the fruit must be completely ripe and richly coloured well before the end. In the final 2-3 "
        f"seconds a human hand enters from the side, grips one fully ripe fruit and picks it cleanly "
        f"from the tree, then holds it still. Day-night cycle passes ~once. Locked camera, no hands "
        f"until the harvest at the end.")
    return prompts


def _egg_prompts(scene: str, animal: str, n_clips: int) -> list:
    """Prompts para un huevo que eclosiona un animal gracioso. n==1: eclosión completa
    en un clip. n>=2: clip 1 empieza a romperse, último clip sale del todo y hace algo
    gracioso."""
    funny = (f"a cute, funny, adorable baby {animal}, charming Pixar-like style, big expressive eyes")
    if n_clips == 1:
        return [(
            f"{scene} The egg starts to wobble and rock, then cracks spread across the shell, pieces "
            f"pop off and {funny} hatches out, climbs out of the shell, shakes itself off and does "
            f"something funny and cute — looks around, chirps, wobbles, tiny happy dance. Locked static "
            f"camera, no zoom or pan. Warm cozy lighting.")]
    prompts = []
    prompts.append(
        f"{scene} The intact egg starts to wobble and rock gently, small cracks appear and slowly "
        f"spread across the shell, a little piece pops off and the tip of a tiny beak or snout of "
        f"{funny} peeks out through a hole — it is only just starting to hatch, still mostly inside "
        f"the egg by the end. Locked static camera, no zoom or pan. Warm cozy lighting, no hands.")
    for _ in range(n_clips - 2):
        prompts.append(
            f"{scene} The egg keeps cracking open more and more as {funny} pushes its way out. "
            f"Locked static camera, no zoom or pan. Warm cozy lighting.")
    prompts.append(
        f"{scene} The shell finally breaks apart and {funny} fully hatches and climbs out of the "
        f"broken shell, shakes itself off, and does something funny and cute — looks around, chirps, "
        f"wobbles, trips adorably or does a tiny happy dance, then looks at the camera. It ends on the "
        f"adorable baby {animal} out of the egg. Locked static camera, no zoom or pan. Warm cozy lighting.")
    return prompts


def _duration(media: Path, ffmpeg: str = "ffmpeg") -> float:
    import re as _re
    r = subprocess.run([ffmpeg, "-i", str(media)], capture_output=True, text=True)
    m = _re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", r.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def _finalize(src: Path, out: Path, w: int, h: int, ffmpeg: str = "ffmpeg",
              music_volume: float = 0.5, src_audio_volume: float = 0.55, music_name: str = "") -> None:
    """Normaliza `src` a vertical WxH y le añade MÚSICA de fondo (la elegida o aleatoria),
    mezclada con el audio original del clip (ambiente de Grok) si lo hay. Si no hay
    música, deja el audio original (o mudo)."""
    music = _pick_music(music_name)
    dur = _duration(src, ffmpeg)  # las pistas duran minutos → sin -stream_loop (evita colgar ffmpeg)
    tbound = ["-t", f"{dur:.3f}"] if dur > 0 else []
    vscale = f"[0:v:0]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps=30[v]"
    if music:
        has_src = _has_audio(src, ffmpeg)
        inputs = ["-i", str(src), "-i", str(music)]
        if has_src:
            afc = (f"[0:a]volume={src_audio_volume},aformat=sample_rates=44100:channel_layouts=stereo[a0];"
                   f"[1:a]volume={music_volume},aformat=sample_rates=44100:channel_layouts=stereo[m];"
                   f"[a0][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]")
        else:
            afc = f"[1:a]volume={music_volume},aformat=sample_rates=44100:channel_layouts=stereo[a]"
        cmd = [ffmpeg, "-y", *inputs, "-filter_complex", f"{vscale};{afc}",
               "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
               "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "160k",
               *tbound, "-movflags", "+faststart", str(out)]
    else:  # sin banco de música: conserva el audio original tal cual
        cmd = [ffmpeg, "-y", "-i", str(src), "-filter_complex", vscale,
               "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "20",
               "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "160k",
               *tbound, "-movflags", "+faststart", str(out)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not out.exists():
        sys.stderr.write(r.stderr[-1200:])
        raise SystemExit("Falló el montaje final (música/normalizado).")
    print(f"   música de fondo: {music.name if music else '—'}", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Vídeo de maceta (time-lapse)")
    ap.add_argument("--plant", required=True, help="id del registro en la BD")
    ap.add_argument("--provider", default="grok", choices=["grok", "veo", "wan"],
                    help="grok/veo=1 clip continuo (de pago); wan=3 clips locales (GPU)")
    ap.add_argument("--duration", type=int, default=15, help="segundos del clip (solo grok; máx 15)")
    ap.add_argument("--length", type=int, default=97, help="frames por clip (solo wan)")
    ap.add_argument("--kind", default="plant", choices=["plant", "egg"], help="planta o huevo eclosionando")
    ap.add_argument("--music", default="", help="nombre de la pista de música (vacío = aleatoria)")
    ap.add_argument("--ffmpeg", default="ffmpeg")
    args = ap.parse_args()

    root = Path.cwd()
    db.init(root / "backend" / "runs" / "jobs.db")
    rec = db.get_plant(args.plant)
    if not rec:
        raise SystemExit(f"Registro {args.plant} no encontrado.")

    # WAN necesita ComfyUI (imagen SDXL + vídeo). Grok NO usa ComfyUI: hace también
    # la primera imagen (grok-imagine-image), que sí sale con la maceta vacía.
    if args.provider == "wan" and not comfy_client.is_up():
        raise SystemExit("ComfyUI no responde (¿encendido en el Windows y la GPU libre?).")

    aspect = rec.get("aspect") or "9:16"
    wan_w, wan_h = (480, 832) if aspect == "9:16" else (832, 480)
    out_w, out_h = (1080, 1920) if aspect == "9:16" else (1920, 1080)

    out_dir = root / "output" / "plants" / args.plant
    out_dir.mkdir(parents=True, exist_ok=True)

    subject = rec.get("plant") or ("chick" if args.kind == "egg" else "lemon")

    # 1) Plan (escena bloqueada + prompt de imagen).
    print("1/5 Generando el plan (escena + prompts)...", flush=True)
    if args.kind == "egg":
        from app.services.plant_engine import egg_plan  # noqa: E402
        plan = egg_plan(subject, aspect)
        img_prompt = plan["image_prompt"]
    else:
        plan = plant_plan(subject, aspect)
        ar = "vertical portrait 9:16" if aspect == "9:16" else "horizontal 16:9"
        img_prompt = (f"photorealistic, {plan.get('locked_scene', '')}, the pot is filled to the brim with "
                      f"fresh dark brown bare soil, smooth flat empty soil surface, absolutely nothing "
                      f"growing, no plant, no sprout, {ar}, soft daylight, sharp focus, ultra detailed, no text")
    db.update_plant(args.plant, {"image_prompt": plan["image_prompt"], "clips": plan.get("clips", [])})

    # 2) Primera imagen (maceta vacía / huevo intacto).
    print("2/5 Generando la primera imagen...", flush=True)
    first = out_dir / "frame_start.jpg"
    if first.exists() and first.stat().st_size > 10000:
        print("   (reuso la maceta vacía ya generada)", flush=True)
    elif args.provider in ("grok", "veo"):
        # grok-imagine-image es el que sí hace la maceta VACÍA (SDXL no).
        from app.services import grok_video as _gv  # noqa: E402
        _gv.generate_image(img_prompt, first)
    else:
        empty_neg = ("(plant:1.6), (sprout:1.6), (seedling:1.6), (leaves:1.6), (foliage:1.6), (green:1.4), "
                     "(stem:1.5), (branch:1.4), (tree:1.5), (sapling:1.5), (flower:1.5), (bud:1.4), (grass:1.4), "
                     "(weeds:1.4), (moss:1.4), (vegetation:1.5), (succulent:1.5), (aloe:1.5), (cactus:1.4), "
                     "(greenery:1.5), growing plant, green shoots, watermark, text, logo, low quality, blurry")
        comfy_client.generate_image(img_prompt, first, width=wan_w, height=wan_h, negative=empty_neg)

    out = out_dir / "video.mp4"

    if args.provider in ("grok", "veo"):
        # 3) 1 o más clips continuos encadenados por el último fotograma. ≤15s = 1 clip
        # (crecimiento sin manos). 30s = 2 clips (mano planta la semilla → … → cosecha).
        from app.services import grok_video, veo_video  # noqa: E402
        scene = plan.get("locked_scene", "")
        n_clips = max(1, min(4, round(args.duration / 15)))
        per = 15 if n_clips > 1 else max(4, min(15, args.duration))
        prompts = (_egg_prompts(scene, subject, n_clips) if args.kind == "egg"
                   else _grok_growth_prompts(scene, subject, n_clips))

        start_img = first
        norm_clips = []
        for i, prompt in enumerate(prompts):
            raw = out_dir / f"{args.provider}_raw{i}.mp4"
            if raw.exists() and raw.stat().st_size > 100000:
                print(f"3/4 Reuso el clip crudo {i + 1}/{n_clips}.", flush=True)
            elif args.provider == "grok":
                print(f"3/4 Clip {i + 1}/{n_clips} con grok ({per}s)...", flush=True)
                grok_video.generate_video(start_img, raw, prompt, duration=per)
            else:
                print(f"3/4 Clip {i + 1}/{n_clips} con veo...", flush=True)
                veo_video.generate_video(start_img, raw, prompt, aspect=aspect)
            if n_clips == 1:
                norm_clips.append(raw)
                break
            n = out_dir / f"{args.provider}_n{i}.mp4"
            _norm_keep_audio(raw, n, out_w, out_h, args.ffmpeg)
            norm_clips.append(n)
            nxt = out_dir / f"frame_mid{i}.jpg"  # último fotograma → inicio del siguiente
            subprocess.run([args.ffmpeg, "-y", "-sseof", "-0.15", "-i", str(n), "-update", "1",
                            "-frames:v", "1", "-q:v", "2", str(nxt)], capture_output=True, text=True)
            if nxt.exists():
                start_img = nxt

        print("4/4 Uniendo + música de fondo...", flush=True)
        if len(norm_clips) == 1:
            _finalize(norm_clips[0], out, out_w, out_h, args.ffmpeg, music_name=args.music)
        else:
            listf = out_dir / "concat.txt"
            listf.write_text("\n".join(f"file '{c.resolve()}'" for c in norm_clips), encoding="utf-8")
            joined = out_dir / "joined.mp4"
            subprocess.run([args.ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(listf),
                            "-c", "copy", "-movflags", "+faststart", str(joined)], capture_output=True, text=True)
            listf.unlink(missing_ok=True)
            _finalize(joined, out, out_w, out_h, args.ffmpeg, music_name=args.music)
            joined.unlink(missing_ok=True)
        if not out.exists():
            raise SystemExit(f"Falló el montaje ({args.provider}).")
    else:
        # 3) 3 clips WAN encadenados por el último fotograma (local, GPU).
        start_img = first
        norm_clips = []
        for i, prompt in enumerate(plan.get("clips", [])):
            print(f"3/5 Clip {i + 1}/3 con WAN (puede tardar)...", flush=True)
            raw = out_dir / f"clip_{i}_raw.mp4"
            wan_client.generate_video(start_img, raw, prompt, width=wan_w, height=wan_h, length=args.length)
            norm = out_dir / f"clip_{i}.mp4"
            _normalize(raw, norm, out_w, out_h, args.ffmpeg)
            if not norm.exists():
                raise SystemExit(f"Falló normalizando el clip {i + 1}.")
            norm_clips.append(norm)
            nxt = out_dir / f"frame_{i}.jpg"
            if _last_frame(norm, nxt, args.ffmpeg):
                start_img = nxt
        print("4/5 Uniendo los clips + música de fondo...", flush=True)
        listfile = out_dir / "concat.txt"
        listfile.write_text("\n".join(f"file '{c.resolve()}'" for c in norm_clips), encoding="utf-8")
        joined = out_dir / "joined.mp4"
        rc = subprocess.run([args.ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
                             "-c", "copy", "-movflags", "+faststart", str(joined)],
                            capture_output=True, text=True)
        if rc.returncode != 0 or not joined.exists():
            sys.stderr.write(rc.stderr[-1200:])
            raise SystemExit("Falló uniendo los clips.")
        listfile.unlink(missing_ok=True)
        _finalize(joined, out, out_w, out_h, args.ffmpeg, music_name=args.music)  # WAN es mudo → música de fondo sola
        joined.unlink(missing_ok=True)

    # 5) Persistir.
    db.update_plant(args.plant, {"image_path": str(first.relative_to(root)),
                                 "video_path": str(out.relative_to(root))})
    print(f"5/5 ✅ Vídeo de maceta listo: {out}", flush=True)


if __name__ == "__main__":
    main()
