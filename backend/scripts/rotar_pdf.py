#!/usr/bin/env python3
import argparse
import os
import sys

def rotate_pdf(input_pdf: str, output_pdf: str) -> None:
    # Funciona con pypdf y con PyPDF2 (3.x)
    try:
        from pypdf import PdfReader, PdfWriter
    except Exception:
        from PyPDF2 import PdfReader, PdfWriter  # type: ignore

    reader = PdfReader(input_pdf)
    writer = PdfWriter()

    for i, page in enumerate(reader.pages):
        page_num = i + 1  # 1-based
        # impares: -90 -> 270
        angle = 90 if (page_num % 2 == 1) else 270
        page.rotate(angle)
        writer.add_page(page)

    with open(output_pdf, "wb") as f:
        writer.write(f)

def main():
    ap = argparse.ArgumentParser(description="Impares -90º y pares +90º")
    ap.add_argument("--pdf", required=True, help="PDF de entrada")
    ap.add_argument("--out", default=None, help="PDF de salida")
    args = ap.parse_args()

    in_path = args.pdf
    if not os.path.isfile(in_path):
        print(f"ERROR: No existe el archivo: {in_path}", file=sys.stderr)
        sys.exit(1)

    out_path = args.out or (os.path.splitext(in_path)[0] + "_horizontal.pdf")
    rotate_pdf(in_path, out_path)
    print(f"OK: guardado en {out_path}")

if __name__ == "__main__":
    main()
