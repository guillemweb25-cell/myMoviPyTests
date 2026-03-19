#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import cv2


FRAME_PREFIXES = [
    ("f01", 0.0),
    ("f25", 0.25),
    ("f50", 0.50),
    ("f75", 0.75),
    ("f100", 1.0),
]


def frame_indices(total_frames: int) -> list[tuple[str, int]]:
    last_index = max(total_frames - 1, 0)
    items: list[tuple[str, int]] = []
    for prefix, ratio in FRAME_PREFIXES:
        index = 0 if ratio == 0.0 else round(last_index * ratio)
        items.append((prefix, min(index, last_index)))
    return items


def extract_quartile_frames(video_path: Path) -> list[Path]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError("No se puede abrir el video.")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        cap.release()
        raise RuntimeError("No se pudo determinar el numero de frames del video.")

    outputs: list[Path] = []
    stem = video_path.stem

    for prefix, index in frame_indices(total_frames):
        cap.set(cv2.CAP_PROP_POS_FRAMES, index)
        ok, frame = cap.read()
        if not ok:
            continue

        output_path = video_path.parent / f"{prefix}_{stem}.jpg"
        cv2.imwrite(str(output_path), frame)
        outputs.append(output_path)

    cap.release()
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Extrae primer frame, quartiles y ultimo frame")
    parser.add_argument("--video", required=True, help="Ruta del video")
    args = parser.parse_args()

    outputs = extract_quartile_frames(Path(args.video))
    print(f"Frames guardados: {len(outputs)}")
    for item in outputs:
        print(item)


if __name__ == "__main__":
    main()
