#!/usr/bin/env python3
from PIL import Image
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Flip horizontal a una imatge")
    parser.add_argument("--file", required=True, help="Ruta de la imatge")
    args = parser.parse_args()

    ruta = Path(args.file)

    if not ruta.exists():
        raise SystemExit(f"❌ No existeix el fitxer: {ruta}")

    img = Image.open(ruta)
    img_flip = img.transpose(Image.FLIP_LEFT_RIGHT)

    sortida = ruta.with_name(ruta.stem + "_flip" + ruta.suffix)
    img_flip.save(sortida)

    print(f"✅ Imatge guardada: {sortida}")

if __name__ == "__main__":
    main()
