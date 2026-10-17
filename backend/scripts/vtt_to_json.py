#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Convierte un .vtt/.srt ya existente al JSON de subtitulos (mismo formato que
genera la transcripcion). Sin coste: no vuelve a transcribir, asi que el JSON sale
con los tramos del VTT pero SIN tiempos por palabra (`words` vacio).

Uso:
    python scripts/vtt_to_json.py "../output/<carpeta>/<nombre>.vtt"
    python scripts/vtt_to_json.py ../output/<carpeta>      # todos los .vtt de la carpeta
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.transcription import parse_vtt, subtitles_json  # noqa: E402


def convert(vtt: Path, force: bool) -> None:
    out = vtt.with_suffix(".json")
    if out.exists() and not force:
        print(f"Ya existe, lo dejo (usa --force para sobrescribir): {out}")
        return
    lang_file = vtt.with_suffix(".lang")
    language = lang_file.read_text(encoding="utf-8").strip() if lang_file.exists() else None
    segments = parse_vtt(vtt.read_text(encoding="utf-8"))
    out.write_text(subtitles_json(segments, language=language), encoding="utf-8")
    print(f"{len(segments)} tramos -> {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description="VTT/SRT -> JSON de subtitulos")
    parser.add_argument("path", help="fichero .vtt/.srt o carpeta")
    parser.add_argument("--force", action="store_true", help="sobrescribir el .json si ya existe")
    args = parser.parse_args()

    path = Path(args.path)
    if path.is_dir():
        files = sorted(list(path.glob("*.vtt")) + list(path.glob("*.srt")))
        if not files:
            raise SystemExit(f"No hay .vtt ni .srt en {path}")
    elif path.exists():
        files = [path]
    else:
        raise SystemExit(f"No existe: {path}")
    for f in files:
        convert(f, args.force)


if __name__ == "__main__":
    main()
