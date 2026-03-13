#!/usr/bin/env python3
import subprocess
import argparse
import os
import sys

def convert_avi_to_mp4(input_file: str, output_file: str = None):
    if not os.path.isfile(input_file):
        print(f"❌ Error: No se encontró el fichero '{input_file}'")
        sys.exit(1)

    if not input_file.lower().endswith(".avi"):
        print("❌ Error: El fichero de entrada debe ser .avi")
        sys.exit(1)

    if output_file is None:
        base = os.path.splitext(input_file)[0]
        output_file = f"{base}.mp4"

    print(f"🎬 Convirtiendo: {input_file} → {output_file}")

    cmd = [
        "ffmpeg",
        "-i", input_file,
        "-c:v", "copy",       # Copia el video sin re-encodear (rápido)
        "-c:a", "aac",        # Audio a AAC (compatible con MP4)
        "-b:a", "192k",
        "-y",                 # Sobreescribir sin preguntar
        output_file
    ]

    result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)

    if result.returncode == 0:
        size = os.path.getsize(output_file) / (1024 * 1024)
        print(f"✅ Conversión completada: {output_file} ({size:.1f} MB)")
    else:
        print(f"❌ Error durante la conversión:\n{result.stderr[-500:]}")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convierte AVI a MP4")
    parser.add_argument("--file", required=True, help="Fichero de entrada (.avi)")
    parser.add_argument("--output", help="Fichero de salida (opcional)")
    args = parser.parse_args()

    convert_avi_to_mp4(args.file, args.output)