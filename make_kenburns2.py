#!/usr/bin/env python3

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
    (una entrada per imatge) seguint l'ordre dels items/prompts.
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


# velocitat base: al test t'ha agradat 6s amb zoom 1.0 -> 1.08
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


def ken_burns_clip(img_path, duration, out_w, out_h, z0, z1):
    # carregam imatge base
    base = Image.open(img_path).convert("RGB")
    W0, H0 = base.size

    # escala mínima per cobrir el canvas
    scale_base = max(out_w / W0, out_h / H0)

    def make_frame(t):
        # zoom lineal
        z = z0 + (z1 - z0) * (t / duration)
        scale = scale_base * z

        # mida escalada
        new_w = int(W0 * scale)
        new_h = int(H0 * scale)

        # reescalar amb Pillow
        img_resized = base.resize((new_w, new_h), Image.LANCZOS)
        arr = np.array(img_resized)

        # crop centrat
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
    ap.add_argument("--folder", required=True)
    ap.add_argument("--out", default="kenburns.mp4")
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--duration", type=float, default=6,
                    help="durada per imatge si NO es passa JSON")
    ap.add_argument("--json-durations", type=str,
                    help="path a image_prompts_all.json")
    args = ap.parse_args()

    folder = Path(args.folder)
    imgs = sorted([p for p in folder.iterdir() if p.suffix.lower() in EXTS])

    # durades
    if args.json_durations:
        durs = load_durations_from_json(Path(args.json_durations))
    else:
        durs = [args.duration] * len(imgs)

    if len(durs) < len(imgs):
        print(f"[WARN] hi ha més imatges ({len(imgs)}) que durades ({len(durs)}). "
              f"Les sobrants usaran {args.duration}s.")
    clips = []
    for i, img in enumerate(imgs):
        dur = durs[i] if i < len(durs) else args.duration

        z_in_0, z_in_1 = zoom_for_duration(dur)  # zoom “normal” (in)

        if i % 2 == 0:
            z0, z1 = z_in_0, z_in_1          # zoom IN
        else:
            z0, z1 = z_in_1, z_in_0          # zoom OUT

        clips.append(
            ken_burns_clip(
                img,
                duration=dur,
                out_w=args.width,
                out_h=args.height,
                z0=z0,
                z1=z1,
            )
        )

    final = concatenate_videoclips(clips)
    final.write_videofile(args.out, fps=args.fps, codec="libx264", audio=False)


if __name__ == "__main__":
    main()
