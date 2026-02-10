#!/usr/bin/env python3
import argparse
import subprocess
from pathlib import Path

def convert_folder(folder: Path):
    if not folder.is_dir():
        print("La carpeta no existe")
        return

    webms = list(folder.glob("*.webm"))
    if not webms:
        print("No hay archivos .webm")
        return

    for webm in webms:
        mp4 = webm.with_suffix(".mp4")
        if mp4.exists():
            print(f"Saltando (ya existe): {mp4.name}")
            continue

        cmd = [
            "ffmpeg", "-y",
            "-i", str(webm),
            "-c:v", "libx264",
            "-c:a", "aac",
            str(mp4)
        ]
        subprocess.run(cmd, check=True)
        print(f"Convertido: {webm.name} → {mp4.name}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", required=True, help="Carpeta con archivos .webm")
    args = parser.parse_args()

    convert_folder(Path(args.folder))
