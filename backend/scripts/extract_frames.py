#!/usr/bin/env python3
import cv2
import argparse
from pathlib import Path

def extract_frames(video_path: Path, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print("No se puede abrir el vídeo.")
        return

    idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        out_path = out_dir / f"frame_{idx:06d}.jpg"
        cv2.imwrite(str(out_path), frame)
        idx += 1

    cap.release()
    print(f"Frames extraídos: {idx}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True, help="Ruta del vídeo")
    ap.add_argument("--output", required=True, help="Carpeta de salida")
    args = ap.parse_args()

    extract_frames(Path(args.video), Path(args.output))

if __name__ == "__main__":
    main()
