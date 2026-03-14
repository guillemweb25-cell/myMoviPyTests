#!/usr/bin/env python3
# make_kenburns2.py

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image
from moviepy import VideoClip, concatenate_videoclips

EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def load_durations_from_json(json_path: Path) -> list[float]:
    """
    Llegeix image_prompts_all.json i genera una llista de durades
    (una entrada per imatge) seguint l'ordre items[prompts].
    """
    data = json.loads(json_path.read_text(encoding="utf-8"))
    durations: list[float] = []

    for item in data.get("items", []):
        secs = float(item.get("seconds") or 0.0)
        spi = item.get("seconds_per_image")
        if spi is None:
            img_count = int(item.get("images_count") or len(item.get("prompts") or []))
            spi = secs / img_count if img_count else secs
        spi = float(spi)

        for _ in item.get("prompts") or []:
            durations.append(spi)

    return durations


# paràmetres de “ritme” de zoom: al test t’agradava 6 s amb delta 0.08
BASE_DURATION = 6.0
BASE_DELTA_Z = 0.08
ZOOM_SPEED = BASE_DELTA_Z / BASE_DURATION  # increment de zoom per segon


def zoom_for_duration(duration: float,
                      zmin: float = 1.08,
                      zmax: float = 1.35) -> tuple[float, float]:
    """
    Manté una velocitat de zoom semblant al test:
    z1 = 1.0 + ZOOM_SPEED * duration (clamp entre zmin i zmax)
    """
    ideal = 1.0 + ZOOM_SPEED * duration
    z1 = max(zmin, min(zmax, ideal))
    return 1.0, z1


def ken_burns_clip(
    img_path,
    duration: float,
    out_w: int,
    out_h: int,
    z0: float,
    z1: float,
    mode: str = "linear",   # "linear" o "pingpong"
) -> VideoClip:
    base = Image.open(img_path).convert("RGB")
    W0, H0 = base.size

    # escala mínima per cobrir el canvas
    scale_base = max(out_w / W0, out_h / H0)

    def zoom_factor(t: float) -> float:
        u = t / max(duration, 0.0001)  # 0..1

        if mode == "pingpong":
            # 0..0.5 → zoom in ; 0.5..1 → zoom out
            if u <= 0.5:
                v = u / 0.5
                z = z0 + (z1 - z0) * v
            else:
                v = (u - 0.5) / 0.5
                z = z1 - (z1 - z0) * v
        else:
            # linear (només in o només out)
            z = z0 + (z1 - z0) * u

        return z

    def make_frame(t: float):
        z = zoom_factor(t)
        scale = scale_base * z

        new_w = int(W0 * scale)
        new_h = int(H0 * scale)

        img_resized = base.resize((new_w, new_h), Image.LANCZOS)
        arr = np.array(img_resized)

        x_center = new_w // 2
        y_center = new_h // 2

        x1 = x_center - out_w // 2
        y1 = y_center - out_h // 2
        x2 = x1 + out_w
        y2 = y1 + out_h

        frame = arr[y1:y2, x1:x2].copy()
        return frame

    return VideoClip(make_frame, duration=duration)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", required=True, help="Carpeta amb les imatges")
    ap.add_argument("--out", default="kenburns.mp4")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--duration", type=float, default=6.0,
                    help="Durada per imatge si NO hi ha JSON")
    ap.add_argument("--json-durations", type=str,
                    help="Path a image_prompts_all.json (durades reals)")
    ap.add_argument(
        "--mode",
        choices=["linear", "pingpong"],
        default="linear",
        help="Tipus de moviment: linear o pingpong (in+out)",
    )
    args = ap.parse_args()

    folder = Path(args.folder)
    imgs = sorted([p for p in folder.iterdir() if p.suffix.lower() in EXTS])

    if not imgs:
        raise SystemExit(f"No s'han trobat imatges a {folder}")

    # durades per imatge
    if args.json_durations:
        durations = load_durations_from_json(Path(args.json_durations))
    else:
        durations = [args.duration] * len(imgs)

    if len(durations) < len(imgs):
        print(
            f"[WARN] hi ha més imatges ({len(imgs)}) que durades ({len(durations)}); "
            f"les sobrants usaran {args.duration}s."
        )

    clips = []
    for i, img in enumerate(imgs):
        dur = durations[i] if i < len(durations) else args.duration

        z_in_0, z_in_1 = zoom_for_duration(dur)  # amplitud segons durada

        # alterna IN / OUT entre imatges (en mode linear)
        if args.mode == "linear":
            if i % 2 == 0:
                z0, z1 = z_in_0, z_in_1      # zoom IN
            else:
                z0, z1 = z_in_1, z_in_0      # zoom OUT
        else:
            # en pingpong sempre fem in+out a la mateixa imatge
            z0, z1 = z_in_0, z_in_1

        clips.append(
            ken_burns_clip(
                img_path=img,
                duration=dur,
                out_w=args.width,
                out_h=args.height,
                z0=z0,
                z1=z1,
                mode=args.mode,
            )
        )

    final = concatenate_videoclips(clips)
    final.write_videofile(args.out, fps=args.fps, codec="libx264", audio=False)


if __name__ == "__main__":
    main()
