#!/usr/bin/env python3
import argparse
from pathlib import Path

from PIL import Image


def convert_image_to_png(file_path: str) -> Path:
    source = Path(file_path)
    if not source.exists() or not source.is_file():
        raise SystemExit(f"No existe el fichero: {source}")

    destination = source.with_suffix(".png")

    with Image.open(source) as image:
        # Keep transparency when present and normalize incompatible modes.
        if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
            image = image.convert("RGBA")
        elif image.mode != "RGB":
            image = image.convert("RGB")
        image.save(destination, format="PNG")

    print(f"PNG generado en: {destination}")
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description="Convierte una imagen a PNG")
    parser.add_argument("--file", required=True, help="Ruta de imagen origen")
    args = parser.parse_args()
    convert_image_to_png(args.file)


if __name__ == "__main__":
    main()
