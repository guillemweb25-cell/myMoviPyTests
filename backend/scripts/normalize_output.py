#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
from pathlib import Path
from datetime import datetime

BASE_DIR = Path("output")


def clean_title(title: str) -> str:
    # Elimina emojis
    title = re.sub(r"[\U00010000-\U0010ffff]", "", title)
    # Elimina caràcters no desitjats
    title = re.sub(r"[^a-zA-Z0-9ñÑáéíóúÁÉÍÓÚüÜ_-]+", "-", title)
    title = re.sub(r"-+", "-", title)
    return title.strip("-").lower()


def is_already_normalized(name: str) -> bool:
    # Comprova si comença per YYYY-MM-DD-
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}-", name))


def normalize_folder(folder: Path):
    if not folder.is_dir():
        return
    if is_already_normalized(folder.name):
        return

    mp3s = list(folder.glob("*.mp3"))
    if not mp3s:
        print(f"⚠️ Sense MP3, salto: {folder}")
        return

    mp3 = mp3s[0]
    stem = mp3.stem

    # Data segons mtime del MP3
    dt = datetime.fromtimestamp(mp3.stat().st_mtime)
    date_str = dt.strftime("%Y-%m-%d")

    clean = clean_title(stem)
    new_name = f"{date_str}-{clean}"
    new_folder = folder.parent / new_name

    # Evita col·lisions
    i = 2
    while new_folder.exists() and new_folder != folder:
        new_folder = folder.parent / f"{new_name}-{i}"
        i += 1

    print(f"📁 {folder.name}  ->  {new_folder.name}")
    folder.rename(new_folder)

    # Després de renombrar, actualitza referència
    folder = new_folder

    # Renombrar transcripcions
    old_txt = folder / "transcription.txt"
    if old_txt.exists():
        new_txt = folder / f"{stem}.txt"
        if not new_txt.exists():
            old_txt.rename(new_txt)
            print(f"  📝 transcription.txt -> {new_txt.name}")

    old_lang = folder / "transcription.lang"
    if old_lang.exists():
        new_lang = folder / f"{stem}.lang"
        if not new_lang.exists():
            old_lang.rename(new_lang)
            print(f"  🌐 transcription.lang -> {new_lang.name}")


def main():
    if not BASE_DIR.exists():
        print(f"❌ No existeix la carpeta {BASE_DIR}")
        return

    for folder in BASE_DIR.iterdir():
        normalize_folder(folder)


if __name__ == "__main__":
    main()
