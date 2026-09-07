#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PRUEBA one-off: escena de 30s = 2 clips Grok de 15s encadenados por el último
fotograma. Clip 1: mano planta la semilla → brota → crece. Clip 2 (empieza donde
acabó el 1): sigue creciendo → florece/fructifica → una mano recoge un fruto.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/
from app.services import grok_video  # noqa: E402
sys.path.insert(0, str(Path(__file__).parent))
from plant_video import _finalize  # noqa: E402  (reusa el montaje con música)

W, H = 1080, 1920
OUT = Path("output/plants/scratch30")
OUT.mkdir(parents=True, exist_ok=True)

SCENE = ("A single terracotta plant pot on a rustic wooden table outdoors, softly blurred green "
         "garden background, soft natural daylight, locked static camera, vertical 9:16 framing, "
         "photorealistic.")

IMG_PROMPT = (f"{SCENE} The pot is filled to the brim with fresh dark bare soil, smooth flat empty "
              "soil surface, absolutely nothing growing, no plant, no sprout, no hands. Ultra detailed.")

CLIP1 = (f"{SCENE} A human hand enters from the side holding a single cherry pit, gently presses it "
         "into the centre of the bare soil and lightly covers it, then the hand leaves the frame. Then "
         "a smooth continuous time-lapse begins and grows FAST: a green sprout pushes up, unfurls its "
         "leaves and grows steadily into a small young cherry tree sapling with several branches by the "
         "end. The day-night cycle passes about once: daylight, warm sunset, deep starry night, then "
         "dawn. Camera locked, no zoom or pan. Only the hand at the very start; then nothing else enters.")

CLIP2 = (f"{SCENE} Pure continuous time-lapse of a cherry tree, growing FAST: the young cherry sapling "
         "quickly fills out, branches spread, white-pink cherry blossoms bloom and their petals fall, "
         "then small green cherries form and ripen QUICKLY into plump, glossy, fully ripe deep-red "
         "cherries — the cherries must be completely ripe and bright red well before the end. In the "
         "final 2-3 seconds a human hand enters from the side, grips one fully ripe red cherry and picks "
         "it cleanly from the tree, then holds it still. The day-night cycle passes about once. Camera "
         "locked, no zoom or pan. No hands until the harvest at the end.")


def _norm_keep_audio(src: Path, out: Path):
    vf = f"[0:v:0]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,fps=30[v]"
    subprocess.run(["ffmpeg", "-y", "-i", str(src), "-filter_complex", vf,
                    "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "ultrafast",
                    "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "160k",
                    str(out)], capture_output=True, text=True)


def main():
    first = OUT / "frame_start.jpg"
    if not first.exists():
        print("Imagen inicial (maceta vacía)...", flush=True)
        grok_video.generate_image(IMG_PROMPT, first)

    raw1 = OUT / "clip1_raw.mp4"
    if not raw1.exists():
        print("Clip 1/2 (mano planta la semilla → crece)...", flush=True)
        grok_video.generate_video(first, raw1, CLIP1, duration=15)

    # Último fotograma del clip 1 = imagen inicial del clip 2 (continuo).
    midframe = OUT / "frame_mid.jpg"
    subprocess.run(["ffmpeg", "-y", "-sseof", "-0.15", "-i", str(raw1), "-update", "1",
                    "-frames:v", "1", "-q:v", "2", str(midframe)], capture_output=True, text=True)

    raw2 = OUT / "clip2_raw.mp4"
    if not raw2.exists():
        print("Clip 2/2 (crece → fructifica → la mano recoge un fruto)...", flush=True)
        grok_video.generate_video(midframe, raw2, CLIP2, duration=15)

    print("Normalizando y uniendo los 2 clips...", flush=True)
    n1, n2 = OUT / "n1.mp4", OUT / "n2.mp4"
    _norm_keep_audio(raw1, n1)
    _norm_keep_audio(raw2, n2)
    listf = OUT / "concat.txt"
    listf.write_text(f"file '{n1.resolve()}'\nfile '{n2.resolve()}'\n", encoding="utf-8")
    joined = OUT / "joined.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listf),
                    "-c", "copy", "-movflags", "+faststart", str(joined)], capture_output=True, text=True)

    print("Añadiendo música...", flush=True)
    _finalize(joined, OUT / "video.mp4", W, H, music_name="moonlit_koi_glide.mp3")
    print(f"✅ Listo: {OUT / 'video.mp4'}", flush=True)


if __name__ == "__main__":
    main()
