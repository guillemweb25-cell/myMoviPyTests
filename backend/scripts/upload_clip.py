#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sube un clip renderizado a YouTube generando SEO con las reglas del canal.

Se ejecuta como job. Lee el clip y su canal de la BD, genera titulo/descripcion/
tags con SEOEngine y sube el MP4 con YouTubeService. Guarda la URL en la BD.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app import db  # noqa: E402
from app.services.seo_engine import SEOEngine  # noqa: E402
from app.services.youtube_service import YouTubeService  # noqa: E402

LANG_HINT = {"es": "es (Spanish)", "en": "en (English)"}


def strip_markdown(text: str) -> str:
    """Convierte a texto plano: quita negritas, cabeceras, codigo y enlaces md."""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # [texto](url) -> texto
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)  # **negrita**
    text = re.sub(r"__(.*?)__", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)  # *cursiva*
    text = re.sub(r"`([^`]*)`", r"\1", text)  # `codigo`
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)  # # cabeceras
    text = re.sub(r"^\s{0,3}[-*]\s+", "- ", text, flags=re.MULTILINE)  # vinetas
    return text.strip()


def read_source_info(video_folder: Path) -> tuple[str, str]:
    """Devuelve (titulo_original, url_original) leyendo source.json / source_url.txt."""
    title, url = "", ""
    source_json = video_folder / "source.json"
    if source_json.exists():
        try:
            data = json.loads(source_json.read_text(encoding="utf-8"))
            title = data.get("title", "") or ""
            url = data.get("url", "") or ""
        except Exception:
            pass
    if not url:
        source_url = video_folder / "source_url.txt"
        if source_url.exists():
            url = source_url.read_text(encoding="utf-8").strip()
    return title, url


def main() -> None:
    parser = argparse.ArgumentParser(description="Sube un clip a YouTube con SEO")
    parser.add_argument("--clip", required=True)
    parser.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    args = parser.parse_args()

    root = Path.cwd()
    db.init(root / "backend" / "runs" / "jobs.db")

    clip = db.get_clip(args.clip)
    if not clip:
        raise SystemExit(f"Clip no encontrado: {args.clip}")
    if not clip.get("channelId"):
        raise SystemExit("El clip no tiene canal asociado.")

    channel = db.get_channel(clip["channelId"])
    if not channel:
        raise SystemExit("Canal no encontrado.")

    rendered = clip.get("renderedPath") or ""
    rendered_path = root / rendered
    if not rendered or not rendered_path.exists():
        raise SystemExit("El clip no esta renderizado todavia.")

    lang = LANG_HINT.get(channel["language"], None)
    rules = channel.get("seoRules") or None
    snippet = clip.get("transcript") or clip.get("title") or ""

    print("Generando SEO (titulo, descripcion, tags)...", flush=True)
    engine = SEOEngine()
    title = strip_markdown(engine.generate_video_title(snippet, lang=lang, custom_rules=rules))
    description = strip_markdown(engine.generate_description(snippet, lang=lang, custom_rules=rules))
    tags = engine.generate_video_questions_tags(snippet, lang=lang, custom_rules=rules)

    # Anade el titulo original y el enlace al video de origen en la descripcion.
    orig_title, orig_url = read_source_info(rendered_path.parent.parent)
    footer_lines = []
    if orig_title:
        footer_lines.append(orig_title)
    if orig_url:
        footer_lines.append(orig_url)
    if footer_lines:
        description = f"{description}\n\n---\n{chr(10).join(footer_lines)}"

    print(f"Titulo: {title}", flush=True)

    print("Subiendo a YouTube...", flush=True)
    service = YouTubeService(channel["id"], root / "youtube_creds")
    response = service.upload_video(
        rendered_path,
        {
            "title": title,
            "description": description,
            "tags": tags,
            "privacy_status": args.privacy,
        },
    )
    video_id = response["id"]
    url = f"https://www.youtube.com/watch?v={video_id}"
    db.update_clip(args.clip, {"youtube_url": url})
    print(f"YOUTUBE_URL: {url}", flush=True)
    print("Subida completada.", flush=True)


if __name__ == "__main__":
    main()
