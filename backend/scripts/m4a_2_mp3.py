#!/usr/bin/env python3
import subprocess
import argparse
import os
import sys

def convert_m4a_to_mp3(input_file: str):
    if not os.path.isfile(input_file):
        print(f"❌ El archivo '{input_file}' no existe.")
        sys.exit(1)

    if not input_file.lower().endswith(".m4a"):
        print("❌ El archivo debe tener extensión .m4a")
        sys.exit(1)

    output_file = os.path.splitext(input_file)[0] + ".mp3"

    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", input_file, "-codec:a", "libmp3lame", "-q:a", "2", output_file],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT
        )
        print(f"✅ Conversión completada: {output_file}")
    except subprocess.CalledProcessError:
        print("❌ Error al convertir el archivo con ffmpeg.")
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convierte un archivo .m4a a .mp3")
    parser.add_argument("--file", required=True, help="Ruta del archivo .m4a a convertir")
    args = parser.parse_args()
    convert_m4a_to_mp3(args.file)
